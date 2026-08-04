"""Scoped web access (docs/11 §L7, Phase G).

A **tool** inside the existing tool-calling loop, not a new pipeline — the loop already
neutralizes tool output, logs every call to `tool_runs`, and caps iterations, so a search that
rides it inherits all three.

**Off by default, and the allowlist starts empty.** Both are deliberate:

- `features.web_search_enabled` is per-agent and defaults false. This is a capability that
  spends money and reaches the open internet on a customer's behalf; it is a per-client
  decision, never a platform default.
- The domain allowlist ships **empty rather than pre-populated**, and empty means *nothing is
  searchable*. Seeding it with guesses about "safe" domains would be this module deciding what
  a client's agent may cite, which is not a judgement code should make. An operator adds their
  own domain and whatever else they trust.

**Results are untrusted content.** A fetched page is the textbook indirect-injection vector,
and it goes through `wrap_untrusted()` exactly like a RAG chunk — the same code path Phase 16
built for precisely this case.

> Not enabled for any agent as part of this work. Turning it on is a per-client decision.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import urlparse

import httpx

from app.chat.guardrails import wrap_untrusted
from app.core.config import settings
from app.core.logging import get_logger

log = get_logger("tools.web_search")

_MAX_RESULTS = 5
_SNIPPET_CHARS = 400


@dataclass(frozen=True)
class WebResult:
    title: str
    url: str
    snippet: str


class WebSearchError(RuntimeError):
    """Raised for a configuration problem the operator can act on."""


def _normalize_domain(value: str) -> str:
    v = (value or "").strip().lower()
    v = re.sub(r"^https?://", "", v)
    v = v.split("/")[0]
    return v[4:] if v.startswith("www.") else v


def parse_domains(raw: str | list[str] | None) -> set[str]:
    """Read a domain policy from agent config or env. Empty stays empty."""
    if not raw:
        return set()
    items = raw if isinstance(raw, list) else re.split(r"[,\s]+", raw)
    return {d for d in (_normalize_domain(i) for i in items) if d}


def domain_allowed(url: str, *, allowlist: set[str], blocklist: set[str]) -> bool:
    """Whether `url` may be fetched or cited.

    **An empty allowlist denies everything.** That is the safe reading and the one that matches
    how this ships: an operator who enables web search without naming a domain gets no results,
    rather than an agent quoting whatever the open web returned. A support agent that can search
    the whole internet will confidently answer with a competitor's pricing.
    """
    host = _normalize_domain(urlparse(url if "://" in url else f"https://{url}").netloc)
    if not host:
        return False
    if any(host == b or host.endswith(f".{b}") for b in blocklist):
        return False
    if not allowlist:
        return False
    return any(host == a or host.endswith(f".{a}") for a in allowlist)


def agent_policy(features: dict[str, object] | None) -> tuple[bool, set[str], set[str]]:
    """`(enabled, allowlist, blocklist)` for an agent. Defaults to off and empty."""
    features = features or {}
    enabled = bool(features.get("web_search_enabled"))
    allow = parse_domains(features.get("web_search_allowed_domains"))  # type: ignore[arg-type]
    block = parse_domains(features.get("web_search_blocked_domains"))  # type: ignore[arg-type]
    return enabled, allow, block


async def search(
    query: str,
    *,
    allowlist: set[str],
    blocklist: set[str],
    transport: httpx.AsyncBaseTransport | None = None,
) -> list[WebResult]:
    """Run a search and drop anything outside the domain policy.

    Filtering happens **after** the provider returns and **before** anything reaches the model,
    so an off-policy result is never quoted even if the provider ranked it first.
    """
    if not settings.web_search_enabled:
        raise WebSearchError("web search is disabled platform-wide (WEB_SEARCH_ENABLED=false)")
    key = (settings.web_search_api_key or "").strip()
    if not key:
        raise WebSearchError("no WEB_SEARCH_API_KEY configured")
    if not allowlist:
        # Not an error the model should retry — it is a configuration gap, and saying so
        # plainly is what stops an operator concluding "the web is down".
        raise WebSearchError("no allowed domains configured for this agent")

    timeout = httpx.Timeout(settings.web_search_timeout_seconds)
    async with httpx.AsyncClient(timeout=timeout, transport=transport) as client:
        resp = await client.post(
            settings.web_search_endpoint,
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            json={"query": query[:400], "max_results": _MAX_RESULTS * 3},
        )
        resp.raise_for_status()
        body = resp.json()

    results: list[WebResult] = []
    for row in (body.get("results") or [])[: _MAX_RESULTS * 3]:
        url = str(row.get("url") or "")
        if not domain_allowed(url, allowlist=allowlist, blocklist=blocklist):
            continue
        results.append(
            WebResult(
                title=str(row.get("title") or url)[:200],
                url=url,
                snippet=str(row.get("content") or row.get("snippet") or "")[:_SNIPPET_CHARS],
            )
        )
        if len(results) >= _MAX_RESULTS:
            break
    return results


def as_tool_output(results: list[WebResult]) -> dict[str, object]:
    """Shape results for the model — wrapped as untrusted data, with citable URLs.

    Every snippet goes through `wrap_untrusted()`: a fetched page is the classic indirect
    injection vector, and this is the exact case that wrapper was written for.
    """
    return {
        "results": [
            {
                "title": r.title,
                "url": r.url,
                "content": wrap_untrusted(r.snippet, kind="web-result"),
            }
            for r in results
        ],
        "count": len(results),
        # The model is told to cite, and the URLs ride the existing citation channel.
        "note": "Cite the source URL for any claim taken from these results.",
    }
