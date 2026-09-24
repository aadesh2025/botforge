"""S-03: a tenant-supplied provider `base_url` must not point the API host at internal services.

Two boundaries are tested, each on its own:

* save time (`credentials.service._check_base_url`): what an editor is allowed to store;
* request time (`OpenAICompatibleProvider._check_destination`): what the API host will actually
  connect to, which also covers rows saved before the check existed and DNS that changes later.

The operator opts private hosts in with `PROVIDER_PRIVATE_HOSTS` (environment config, not a
tenant setting). The platform's own `OLLAMA_BASE_URL` and the catalog's vendor URLs are trusted
and are not guarded.
"""

from __future__ import annotations

import socket
import uuid

import httpx
import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.crypto import encrypt
from app.llm import openai_compatible
from app.llm.base import ProviderError
from app.llm.openai_compatible import CustomProvider, OllamaProvider
from app.llm.registry import build_chat_provider
from app.llm.types import ChatRequest, Message
from app.models import ProviderCredential, User

BLOCKED_URLS = [
    "http://127.0.0.1:8080/v1",
    "http://localhost:8080/v1",
    "http://[::1]:8080/v1",
    "http://10.0.0.5/v1",
    "http://192.168.1.10/v1",
    "http://172.16.0.9/v1",
    "http://169.254.169.254/latest/meta-data",
    "http://[fd00::1]/v1",
]
PUBLIC_URL = "http://8.8.8.8/v1"  # a public literal: no DNS needed, so the test runs offline


@pytest.fixture(autouse=True)
def _no_operator_allowlist(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "provider_private_hosts", "")


async def _org(client: AsyncClient, email: str = "s03@example.com") -> dict[str, str]:
    signup = await client.post("/v1/auth/signup", json={"email": email, "password": "password123"})
    token = signup.json()["access_token"]
    org = await client.post("/v1/orgs", json={"name": "Acme"}, headers={"Authorization": f"Bearer {token}"})
    return {"Authorization": f"Bearer {token}", "X-Org-Id": org.json()["id"]}


def _requests_recorded() -> tuple[list[httpx.Request], httpx.MockTransport]:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if request.url.path.endswith("/models"):
            return httpx.Response(200, json={"data": [{"id": "m1"}]})
        return httpx.Response(200, json={"choices": [{"message": {"content": "ok"}}]})

    return seen, httpx.MockTransport(handler)


REQ = ChatRequest(model="m", messages=[Message(role="user", content="hi")])


# ── save time ───────────────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("url", BLOCKED_URLS)
async def test_saving_a_private_endpoint_is_refused(client: AsyncClient, url: str) -> None:
    headers = await _org(client)
    r = await client.put(
        "/v1/credentials/providers/custom", json={"api_key": "k", "base_url": url}, headers=headers
    )
    assert r.status_code == 422, r.text
    assert r.json()["error"]["code"] == "credentials.base_url_blocked"


async def test_all_three_write_paths_enforce_the_policy(client: AsyncClient) -> None:
    headers = await _org(client)
    bad = "http://10.0.0.5/v1"

    post = await client.post(
        "/v1/credentials", json={"provider": "custom", "api_key": "k", "base_url": bad}, headers=headers
    )
    assert post.status_code == 422 and post.json()["error"]["code"] == "credentials.base_url_blocked"

    ok = await client.post(
        "/v1/credentials",
        json={"provider": "custom", "api_key": "k", "base_url": PUBLIC_URL},
        headers=headers,
    )
    assert ok.status_code == 201, ok.text
    patch = await client.patch(f"/v1/credentials/{ok.json()['id']}", json={"base_url": bad}, headers=headers)
    assert patch.status_code == 422 and patch.json()["error"]["code"] == "credentials.base_url_blocked"
    after = await client.get("/v1/credentials", headers=headers)
    assert after.json()[0]["base_url"] == PUBLIC_URL  # the refused PATCH stored nothing


async def test_ollama_override_is_checked_too(client: AsyncClient) -> None:
    headers = await _org(client)
    r = await client.put(
        "/v1/credentials/providers/ollama", json={"base_url": "http://10.0.0.5:11434"}, headers=headers
    )
    assert r.status_code == 422 and r.json()["error"]["code"] == "credentials.base_url_blocked"


async def test_a_public_endpoint_is_accepted(client: AsyncClient) -> None:
    headers = await _org(client)
    r = await client.put(
        "/v1/credentials/providers/custom", json={"api_key": "k", "base_url": PUBLIC_URL}, headers=headers
    )
    assert r.status_code == 200, r.text
    assert r.json()["base_url"] == PUBLIC_URL


async def test_a_hostname_that_resolves_to_a_private_address_is_refused(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fake_getaddrinfo(host: str, *a: object, **k: object) -> list[tuple]:
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.0.0.9", 0))]

    monkeypatch.setattr("app.core.ssrf.socket.getaddrinfo", fake_getaddrinfo)
    headers = await _org(client)
    r = await client.put(
        "/v1/credentials/providers/custom",
        json={"api_key": "k", "base_url": "https://llm.attacker.example/v1"},
        headers=headers,
    )
    assert r.status_code == 422 and r.json()["error"]["code"] == "credentials.base_url_blocked"


@pytest.mark.parametrize("suffix", ["?", "?x=1", "#frag"])
async def test_query_or_fragment_is_refused_because_it_neutralises_the_path_suffix(
    client: AsyncClient, suffix: str
) -> None:
    """`http://host/a/?` + `/models` reaches `/a/?/models`: the caller would control the path."""
    headers = await _org(client)
    r = await client.put(
        "/v1/credentials/providers/custom",
        json={"api_key": "k", "base_url": PUBLIC_URL + suffix},
        headers=headers,
    )
    assert r.status_code == 422 and r.json()["error"]["code"] == "credentials.base_url_invalid"


async def test_a_non_http_scheme_is_refused(client: AsyncClient) -> None:
    headers = await _org(client)
    r = await client.put(
        "/v1/credentials/providers/custom",
        json={"api_key": "k", "base_url": "file:///etc/passwd"},
        headers=headers,
    )
    assert r.status_code == 422 and r.json()["error"]["code"] == "credentials.base_url_invalid"


async def test_operator_allowlist_permits_a_named_private_host(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "provider_private_hosts", " Host.Docker.Internal , 10.0.0.5 ")
    headers = await _org(client)
    named = await client.put(
        "/v1/credentials/providers/custom",
        json={"api_key": "k", "base_url": "http://10.0.0.5:8000/v1"},
        headers=headers,
    )
    assert named.status_code == 200, named.text
    # Only what is named: a different private host is still refused.
    other = await client.put(
        "/v1/credentials/providers/custom",
        json={"api_key": "k", "base_url": "http://10.0.0.6:8000/v1"},
        headers=headers,
    )
    assert other.status_code == 422


async def test_platform_staff_are_not_exempt(client: AsyncClient, db_session: AsyncSession) -> None:
    """The trust is the operator's allowlist, not the actor: an editor can re-PATCH a staff-made row."""
    headers = await _org(client, "staff-s03@example.com")
    user = (await db_session.execute(select(User).where(User.email == "staff-s03@example.com"))).scalar_one()
    user.is_staff = True
    await db_session.flush()
    r = await client.put(
        "/v1/credentials/providers/custom", json={"api_key": "k", "base_url": "http://10.0.0.5/v1"}, headers=headers
    )
    assert r.status_code == 422


# ── request time ────────────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("url", BLOCKED_URLS)
async def test_the_provider_never_connects_to_a_private_endpoint(url: str) -> None:
    seen, transport = _requests_recorded()
    provider = CustomProvider(url, "k", transport=transport)
    with pytest.raises(ProviderError, match="refusing"):
        await provider.list_models()
    with pytest.raises(ProviderError, match="refusing"):
        await provider.chat(REQ)
    with pytest.raises(ProviderError, match="refusing"):
        async for _ in provider.stream(REQ):
            pass
    assert seen == []  # not one request left the process


async def test_a_legacy_row_saved_before_the_check_cannot_be_used(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Rows written without validation (older builds, direct DB edits) hit the request-time guard."""
    headers = await _org(client, "legacy-s03@example.com")
    org_id = headers["X-Org-Id"]
    row = ProviderCredential(
        organization_id=uuid.UUID(org_id), provider="custom", api_key_enc=encrypt("k"),
        base_url="http://127.0.0.1:9/v1", is_default=True,
    )
    db_session.add(row)
    await db_session.flush()

    r = await client.post(f"/v1/credentials/{row.id}/test", headers=headers)
    assert r.status_code == 200
    assert r.json()["ok"] is False
    assert "refusing" in r.json()["error"]


async def test_a_public_endpoint_is_reached(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(openai_compatible, "is_blocked_destination", lambda host, allowed="": False)
    seen, transport = _requests_recorded()
    models = await build_chat_provider("custom", api_key="k", base_url=PUBLIC_URL, transport=transport).list_models()
    assert [m.id for m in models] == ["m1"]
    assert len(seen) == 1


async def test_an_allowlisted_private_host_is_reached(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "provider_private_hosts", "10.0.0.5")
    seen, transport = _requests_recorded()
    provider = build_chat_provider("custom", api_key="k", base_url="http://10.0.0.5:8000/v1", transport=transport)
    assert (await provider.chat(REQ)).content == "ok"
    assert [r.url.host for r in seen] == ["10.0.0.5"]


async def test_the_platforms_own_ollama_default_is_not_guarded() -> None:
    """`OLLAMA_BASE_URL` is operator config (loopback in dev): only a tenant *override* is checked."""
    seen, transport = _requests_recorded()
    models = await OllamaProvider(transport=transport).list_models()
    assert [m.id for m in models] == ["m1"]
    assert seen[0].url.host == "localhost"

    with pytest.raises(ProviderError, match="refusing"):
        await build_chat_provider("ollama", base_url="http://10.0.0.5:11434", transport=transport).list_models()


async def test_a_catalog_vendor_url_is_not_guarded_but_a_stored_override_is() -> None:
    seen, transport = _requests_recorded()
    # No override: the catalog's fixed, public vendor URL. Made without DNS (transport is a mock).
    default = build_chat_provider("mistral", api_key="k", transport=transport)
    assert default._guard_destination is False  # type: ignore[attr-defined]
    override = build_chat_provider("mistral", api_key="k", base_url="http://10.0.0.5/v1", transport=transport)
    with pytest.raises(ProviderError, match="refusing"):
        await override.list_models()
    assert seen == []


async def test_redirects_are_not_followed(monkeypatch: pytest.MonkeyPatch) -> None:
    """A public endpoint answering 302 -> an internal address must not be chased."""
    monkeypatch.setattr(openai_compatible, "is_blocked_destination", lambda host, allowed="": False)
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.url.host)
        return httpx.Response(302, headers={"location": "http://169.254.169.254/latest/meta-data/"})

    provider = CustomProvider(PUBLIC_URL, "k", transport=httpx.MockTransport(handler))
    with pytest.raises(Exception):  # noqa: B017 - the 302 has no JSON body; what matters is below
        await provider.list_models()
    assert seen == ["8.8.8.8"]
