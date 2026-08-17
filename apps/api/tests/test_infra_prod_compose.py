"""docs/15 §2 — properties of the production compose file that nothing else can check.

Both PROD-1 and PROD-2 were *deployment* bugs: every line of application code was correct, the
whole test suite was green, and the feature was broken for any real client. Neither could fail a
test, because no test looked at how the thing is deployed. These do.

The two checks below are deliberately general rather than assertions that specific lines exist:

* **PROD-1** — any service that runs the API image and touches uploaded files must mount the same
  volume at the same path. A test naming `api` and `worker` would pass a future `q=media` worker
  (docs/14 K3-4) straight into the same bug.
* **PROD-2** — every internal hostname the containers are pointed at must be a service declared
  in the same file. `OLLAMA_BASE_URL: http://ollama:11434` with no `ollama` service was PROD-2
  exactly, and it is the shape of the bug, not the hostname, that is worth pinning.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

from app.core.config import Settings

COMPOSE = Path(__file__).resolve().parents[3] / "infra" / "docker-compose.prod.yml"

#: Hostnames that are deliberately NOT services in this file, with the reason each is safe.
#:
#: `n8n` — CLAUDE.md §6 requires supporting an already-running instance, so `N8N_BASE_URL` is
#: expected to point outside the compose project. It also degrades honestly: with n8n absent,
#: workflow discovery returns a typed error and bound tools keep working from the stored
#: `webhook_url`. That is the difference from `ollama`, whose absence silently failed every
#: single document ingest with nothing in the configuration looking wrong.
_EXTERNAL_HOSTS = {"n8n"}

#: Services built from `apps/api/Dockerfile`. They share `x-api-env`, so they share `UPLOAD_DIR`.
_API_IMAGE_SERVICES = {"api", "worker", "beat", "migrate"}

#: Of those, the ones that read or write an uploaded document: the api writes it on upload and
#: serves it back, the worker ingests it. `beat` only schedules and `migrate` only runs alembic.
_UPLOAD_SERVICES = {"api", "worker"}


@pytest.fixture(scope="module")
def compose() -> dict[str, Any]:
    assert COMPOSE.exists(), f"missing {COMPOSE}"
    return dict(yaml.safe_load(COMPOSE.read_text(encoding="utf-8")))


def _services(compose: dict[str, Any]) -> dict[str, Any]:
    return dict(compose.get("services") or {})


def _hostname(url: str) -> str:
    """Host out of a URL that may contain compose interpolation.

    `urlsplit` is not usable here: `DATABASE_URL` embeds
    `${POSTGRES_PASSWORD:?set POSTGRES_PASSWORD}` in its userinfo, and the space inside that
    placeholder makes `urlsplit().hostname` return the start of the placeholder instead of the
    host. Parsed by hand so the check reads the same host Docker will.
    """
    rest = url.split("://", 1)[1]
    netloc = rest.split("/", 1)[0]
    if "@" in netloc:  # strip user:password, which is where the placeholders live
        netloc = netloc.rsplit("@", 1)[1]
    host = netloc.split(":", 1)[0].strip()
    return "" if "$" in host else host


def _mounts(service: dict[str, Any]) -> dict[str, str]:
    """`{target: source}` for the short `source:target[:mode]` volume syntax used in this file."""
    out: dict[str, str] = {}
    for entry in service.get("volumes") or []:
        if isinstance(entry, str):
            source, target, *_ = entry.split(":")
            out[target] = source
    return out


# ── PROD-1: the api and the worker must see the same files ───────────────────────────────────

def test_every_service_that_touches_uploads_shares_one_volume(compose: dict[str, Any]) -> None:
    """The bug: api and worker are separate containers with separate filesystems.

    The api wrote `<upload_dir>/<id>.pdf` and the worker read it back in a different container,
    got "Stored file is missing", and marked the document `failed`. Invisible in dev, where both
    run from one directory on the host (CLAUDE.md §12), and invisible to a smoke test, because URL
    and pasted-text ingest never touch the filesystem.
    """
    services = _services(compose)
    upload_dir = str(services["api"]["environment"]["UPLOAD_DIR"])

    sources = {}
    for name in sorted(_UPLOAD_SERVICES):
        mounts = _mounts(services[name])
        assert upload_dir in mounts, (
            f"service '{name}' has no volume at {upload_dir}: it cannot see uploaded files"
        )
        sources[name] = mounts[upload_dir]

    assert len(set(sources.values())) == 1, (
        f"upload services mount DIFFERENT volumes at {upload_dir}: {sources}. "
        "Separate volumes reproduce PROD-1 while looking fixed."
    )
    # A named volume, not a host bind: a bind path that does not exist on the host is created
    # root-owned and the non-root app user cannot write to it.
    assert sources["api"] in (compose.get("volumes") or {}), (
        f"'{sources['api']}' is mounted but not declared under top-level volumes:"
    )


def test_the_upload_dir_is_absolute_so_the_mount_cannot_miss_it(compose: dict[str, Any]) -> None:
    """`./var/uploads` resolves via WORKDIR and happens to be right; a mount target cannot.

    If `UPLOAD_DIR` is ever set to a relative path that does not resolve under the mount point,
    the volume is mounted somewhere the app never writes and PROD-1 returns silently.
    """
    upload_dir = str(_services(compose)["api"]["environment"]["UPLOAD_DIR"])
    assert upload_dir.startswith("/"), upload_dir


# ── PROD-2: every hostname pointed at must exist ─────────────────────────────────────────────

def test_every_internal_hostname_resolves_to_a_declared_service(compose: dict[str, Any]) -> None:
    """The bug: `OLLAMA_BASE_URL: http://ollama:11434` with no `ollama` service in the file.

    A knowledge base created with default settings in production pointed at a hostname that does
    not resolve, so every embed call failed and every document failed to ingest — with nothing in
    the configuration looking wrong. Same family as ADR-044's `.env` comment being read as an API
    key: correct in dev, silently wrong in production.
    """
    services = _services(compose)
    declared = set(services)
    env = dict(services["api"]["environment"])

    for key, value in env.items():
        if not isinstance(value, str) or "://" not in value:
            continue
        host = _hostname(value)
        if not host or "." in host or host in ("localhost", "127.0.0.1"):
            # Dotted names are external (or an operator-supplied override); localhost is a
            # deliberate opt-out and is caught at runtime by the startup probe instead.
            continue
        if host in _EXTERNAL_HOSTS:
            continue
        assert host in declared, (
            f"{key}={value} points at '{host}', which is not a service in {COMPOSE.name}. "
            f"Declared: {sorted(declared)}. If '{host}' is deliberately an external dependency, "
            f"add it to _EXTERNAL_HOSTS with the reason it degrades safely."
        )


def test_the_embedding_service_pulls_the_model_the_app_asks_for(compose: dict[str, Any]) -> None:
    """Declaring the service is only half the fix, and this is the half that drifts.

    `ollama/ollama` starts EMPTY — it serves an API with no models, and embedding against a model
    it has not pulled is an error rather than a download. The model name is hardcoded in the
    compose command because compose interpolates from `infra/.env` and the shell, NOT from the
    `../.env` the containers get via `env_file`, so a `${EMBEDDING_MODEL}` there would silently
    keep pulling the old default after someone changed the app's model. This test is the seam
    that makes that drift fail in CI instead of at a client's first upload.
    """
    ollama = _services(compose)["ollama"]
    command = " ".join(ollama["command"]) if isinstance(ollama["command"], list) else str(ollama["command"])
    model = Settings().embedding_model

    assert f"ollama pull {model}" in command, (
        f"the ollama service does not pull '{model}' (the app's configured embedding model)"
    )
    # The healthcheck must prove the MODEL is there, not that the port answers — a healthy but
    # empty Ollama is the exact state that produced PROD-2.
    healthcheck = " ".join(str(x) for x in ollama["healthcheck"]["test"])
    assert model in healthcheck, healthcheck


def test_the_embedding_service_is_not_published(compose: dict[str, Any]) -> None:
    """Ollama has no authentication of any kind, so a published port is open inference.

    Same rule as docling-serve (docs/14 §9). `expose` keeps it on the compose network only.
    """
    ollama = _services(compose)["ollama"]
    assert not ollama.get("ports"), f"ollama publishes {ollama.get('ports')} — it has no auth"
    assert ollama.get("expose"), "ollama should `expose` its port for in-network callers"


def test_the_platform_does_not_hard_depend_on_embeddings(compose: dict[str, Any]) -> None:
    """A worker that will not start takes every background job down, not just ingest.

    Embeddings are required by the knowledge base, not by the platform. Waiting on
    `service_healthy` here would mean a failed model download also stops webhooks, email and
    campaigns; a queued ingest task waits in Redis instead, which is a delay, not a failure.
    """
    for name in ("api", "worker"):
        depends = _services(compose)[name].get("depends_on") or {}
        condition = depends.get("ollama", {}).get("condition") if isinstance(depends, dict) else None
        assert condition in (None, "service_started"), (
            f"'{name}' waits on ollama with condition={condition!r}; embeddings must not gate startup"
        )


# ── the image the mount depends on ───────────────────────────────────────────────────────────

def test_the_dockerfile_creates_the_upload_dir_before_dropping_privileges() -> None:
    """Docker seeds an empty named volume from the image path — including its ownership.

    If the path does not exist in the image, Docker creates the mountpoint as root:root and the
    non-root app user cannot write to its own upload directory. That surfaces as a permissions
    error at the first client upload, i.e. after deploy: PROD-1 traded for a different bug.
    """
    dockerfile = (Path(__file__).resolve().parents[1] / "Dockerfile").read_text(encoding="utf-8")
    mkdir_at = dockerfile.find("mkdir -p /app/var/uploads")
    chown_at = dockerfile.find("chown -R appuser:appuser /app")
    user_at = dockerfile.find("USER appuser")
    assert mkdir_at != -1, "the image never creates /app/var/uploads"
    assert mkdir_at < chown_at < user_at, "the upload dir must be created and chowned before USER"
