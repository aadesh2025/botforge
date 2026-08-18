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
    """A second round trip would re-run the entire ML pipeline for something already computed.

    ⚠️ This used to assert only that the substrings "to_formats"/"md"/"json" appeared *somewhere*
    in the raw multipart body — which stayed true even while the real bug shipped: the previous
    code nested everything inside one `options` JSON string field, a shape `docling-serve`
    silently accepts and silently ignores (falling back to its own schema default
    `to_formats=["md"]`). That meant `json_content` came back `None` on **every real conversion**
    (docs/14 K1-5, verified live against v2.119.0) while this test stayed green throughout. Fixed
    by actually parsing the multipart body and asserting on the **field structure**, which is the
    only check that can tell "nested under `options`" apart from "real top-level fields".
    """
    seen: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        parts = _parse_multipart(request)
        seen["field_names"] = sorted(parts.keys())
        seen["to_formats"] = parts.get("to_formats")
        seen["do_ocr"] = parts.get("do_ocr")
        return httpx.Response(200, json={"document": {"md_content": "text", "json_content": {}}})

    converter = DoclingServiceConverter("http://docling:5001", transport=httpx.MockTransport(handler))
    await converter.convert(b"x", filename="a.pdf", mime_type="application/pdf")
    assert seen["url"] == "http://docling:5001/v1/convert/file"
    # docling-serve's Body_process_file_v1_convert_file_post schema wants these as top-level
    # multipart fields — never nested under a single "options" field.
    assert "options" not in seen["field_names"]  # type: ignore[operator]
    assert seen["to_formats"] == ["md", "json"]
    assert seen["do_ocr"] == ["true"]  # stringified — see `_options()`'s docstring for why


def _parse_multipart(request: httpx.Request) -> dict[str, list[str]]:
    """Decode a multipart/form-data body into `{field_name: [values...]}`.

    Repeated fields (docling-serve's `to_formats` is `list[str]`) arrive as one part per value
    with the same name — collected here rather than overwritten, so a list-valued field is
    distinguishable from a scalar one.
    """
    content_type = request.headers["content-type"]
    boundary = content_type.split("boundary=")[1].encode()
    body = request.content
    fields: dict[str, list[str]] = {}
    for part in body.split(b"--" + boundary):
        if b'name="' not in part or b"filename=" in part:
            continue
        name = part.split(b'name="', 1)[1].split(b'"', 1)[0].decode()
        value = part.split(b"\r\n\r\n", 1)[1].rsplit(b"\r\n", 1)[0].decode()
        fields.setdefault(name, []).append(value)
    return fields


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


# ── the startup warm-up probe (docs/14 K1-5 follow-up) ───────────────────────────────────


async def test_warmup_makes_no_network_call_when_docling_is_off() -> None:
    """`docling_enabled` gates the probe exactly like it gates real conversion."""
    called = False

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal called
        called = True
        return httpx.Response(200, json={"document": {"md_content": "x"}})

    # Docling disabled is the default in every test via conftest.py — assert it explicitly here
    # rather than relying on ambient state, since this test is the one that would catch a
    # regression in that default.
    assert not settings.docling_enabled
    ok, reason = await converters.probe_reachable(transport=httpx.MockTransport(handler))
    assert ok is True
    assert reason is None
    assert called is False


async def test_warmup_never_raises_when_the_service_is_unreachable() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    with _enabled():
        ok, reason = await converters.probe_reachable(transport=httpx.MockTransport(handler))
    assert ok is False
    assert reason is not None and "ConnectError" in reason


async def test_a_slow_docling_does_not_hang_the_probe() -> None:
    """The probe must give up within its own short window, not `DOCLING_TIMEOUT_SECONDS` (120s)
    — a startup diagnostic that can hold the process hostage on a slow service is worse than the
    cold start it exists to avoid."""

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("still loading the layout model", request=request)

    with _enabled():
        ok, reason = await converters.probe_reachable(transport=httpx.MockTransport(handler))
    # A timeout is treated as "kicked off, not a failure" — the server-side job worker keeps
    # processing after the client gives up (verified live, docs/14 K1-5 follow-up).
    assert ok is True
    assert reason is None


async def test_warmup_sends_a_real_pdf_with_matching_options() -> None:
    """The whole point is hitting the same options-hash pipeline cache `DoclingServiceConverter`
    uses for real conversions — mismatched `do_ocr`/`do_table_structure` warms the wrong one
    (measured: cut a cold conversion from 124.6s to only 86.5s instead of 6.1s)."""
    seen: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        parts = _parse_multipart(request)
        seen["do_ocr"] = parts.get("do_ocr")
        seen["do_table_structure"] = parts.get("do_table_structure")
        seen["filename"] = "warmup.pdf" in request.content.decode("utf-8", errors="replace")
        return httpx.Response(200, json={"document": {"md_content": "x"}})

    with _enabled():
        await converters.probe_reachable(transport=httpx.MockTransport(handler))
    assert seen["do_ocr"] == ["true" if settings.docling_do_ocr else "false"]
    assert seen["do_table_structure"] == ["true" if settings.docling_do_table_structure else "false"]
    assert seen["filename"] is True
