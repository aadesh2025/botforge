"""Docling conversion and, more importantly, its fallback (docs/14 K1, §11).

docs/14 §11 is explicit about what to test here, and it is not the happy path:

> **Test the fallback, not just the happy path.** Simulate a docling-serve outage and assert the
> document still ingests via `LegacyConverter`. The 2026-08-04 lesson: when a feature has an
> allow path and a deny path, testing one proves nothing.

That lesson was expensive. Phase B's PII allowlist tests passed for weeks while the feature was
inverted in production, because they only ever asserted the direction that passes when it is
broken. So every case below that asserts Docling working has a sibling asserting the legacy path
still produces a document.

**No test may call a real docling-serve.** `conftest.py` leaves `docling_enabled` off for the
whole suite; these turn it on with a mock transport, the same shape `test_guard_models.py` uses
for L2 and `test_rerank.py` for stage 4.
"""

from __future__ import annotations

import json

import httpx
import pytest

from app.core.config import settings
from app.rag import converters
from app.rag.converters import (
    BACKEND_DOCLING,
    BACKEND_LEGACY,
    DoclingServiceConverter,
    LegacyConverter,
)

_MARKDOWN = "# Returns Policy\n\n## International Orders\n\nRefunds within 30 days."
_DOCLING_JSON = {"schema_name": "DoclingDocument", "texts": [{"text": "Refunds within 30 days."}]}


def _ok(md: str = _MARKDOWN, structured: object = _DOCLING_JSON) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, json={"document": {"md_content": md, "json_content": structured}}
        )

    return httpx.MockTransport(handler)


def _enabled(endpoint: str = "http://docling:5001"):  # type: ignore[no-untyped-def]
    """Turn Docling on for one test and put it back afterwards."""

    class _Ctx:
        def __enter__(self) -> None:
            self._prev = (settings.docling_enabled, settings.docling_endpoint)
            settings.docling_enabled = True
            settings.docling_endpoint = endpoint

        def __exit__(self, *exc: object) -> None:
            settings.docling_enabled, settings.docling_endpoint = self._prev

    return _Ctx()


# ── the legacy converter is the permanent default ────────────────────────────────────────

async def test_legacy_converter_is_the_default() -> None:
    assert isinstance(converters.build_converter(), LegacyConverter)


async def test_legacy_converter_still_reads_what_it_always_did() -> None:
    """The interface must not change what four formats already produce."""
    result = await LegacyConverter().convert(
        b"plain text body", filename="notes.txt", mime_type="text/plain"
    )
    assert result.text == "plain text body"
    assert result.backend == BACKEND_LEGACY
    assert result.document is None
    assert result.has_structure is False


async def test_enabled_with_no_endpoint_is_still_the_legacy_path() -> None:
    """The dangerous half-configured state degrades safely, and says so."""
    with _enabled(endpoint=""):
        assert isinstance(converters.build_converter(), LegacyConverter)
        assert "DOCLING_ENDPOINT is empty" in (converters.unavailable_reason() or "")


# ── the service converter ────────────────────────────────────────────────────────────────

async def test_it_returns_markdown_and_the_structured_document() -> None:
    with _enabled():
        result = await converters.convert_with_fallback(
            b"%PDF-1.4", filename="policy.pdf", mime_type="application/pdf", transport=_ok()
        )
    assert result.backend == BACKEND_DOCLING
    assert result.text == _MARKDOWN
    assert result.document == _DOCLING_JSON
    assert result.has_structure is True


async def test_it_asks_for_markdown_and_json_in_one_call() -> None:
    """A second round trip would re-run the entire ML pipeline for something already computed."""
    seen: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        body = request.content.decode("utf-8", errors="replace")
        seen["has_options"] = "to_formats" in body
        seen["formats"] = [f for f in ("md", "json") if f'"{f}"' in body]
        return httpx.Response(200, json={"document": {"md_content": "text", "json_content": {}}})

    converter = DoclingServiceConverter("http://docling:5001", transport=httpx.MockTransport(handler))
    await converter.convert(b"x", filename="a.pdf", mime_type="application/pdf")
    assert seen["url"] == "http://docling:5001/v1/convert/file"
    assert seen["has_options"] is True
    assert seen["formats"] == ["md", "json"]


async def test_json_content_returned_as_a_string_is_still_parsed() -> None:
    with _enabled():
        result = await converters.convert_with_fallback(
            b"x", filename="a.pdf", mime_type="application/pdf",
            transport=_ok(structured=json.dumps(_DOCLING_JSON)),
        )
    assert result.document == _DOCLING_JSON


# ── failing over, which is the case that matters ─────────────────────────────────────────

@pytest.mark.parametrize(
    "handler",
    [
        pytest.param(lambda r: httpx.Response(503, text="unavailable"), id="service_down"),
        pytest.param(lambda r: httpx.Response(500, text="boom"), id="server_error"),
        pytest.param(lambda r: httpx.Response(200, json={"nope": 1}), id="no_document_key"),
        pytest.param(lambda r: httpx.Response(200, text="not json"), id="not_json"),
        pytest.param(
            lambda r: httpx.Response(200, json={"document": {"md_content": "   "}}),
            id="empty_extraction",
        ),
    ],
)
async def test_every_docling_failure_still_produces_a_document(handler) -> None:  # type: ignore[no-untyped-def]
    """A client must never be told their upload is broken because an internal service was down.

    An empty extraction counts as a failure, not as an empty document (docs/14 §8): the legacy
    parser gets its go before anything is marked `failed`.
    """
    with _enabled():
        result = await converters.convert_with_fallback(
            b"fallback body text",
            filename="notes.txt",
            mime_type="text/plain",
            transport=httpx.MockTransport(handler),
        )
    assert result.backend == BACKEND_LEGACY
    assert result.text == "fallback body text"
    assert result.document is None


async def test_a_timeout_falls_back_rather_than_failing_the_upload() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("500-page pdf", request=request)

    with _enabled():
        result = await converters.convert_with_fallback(
            b"body", filename="huge.txt", mime_type="text/plain",
            transport=httpx.MockTransport(handler),
        )
    assert result.backend == BACKEND_LEGACY
    assert result.text == "body"


async def test_the_backend_is_recorded_so_a_regression_is_attributable() -> None:
    """Both directions with the same input — the 2026-08-04 rule.

    A test that only asserts `backend == "docling"` passes just as happily when the fallback is
    broken in the other direction.
    """
    payload, name, mime = b"same bytes", "same.txt", "text/plain"
    with _enabled():
        via_docling = await converters.convert_with_fallback(
            payload, filename=name, mime_type=mime, transport=_ok(md="from docling")
        )
    via_legacy = await converters.convert_with_fallback(payload, filename=name, mime_type=mime)

    assert via_docling.backend == BACKEND_DOCLING
    assert via_legacy.backend == BACKEND_LEGACY
    assert via_docling.text != via_legacy.text
