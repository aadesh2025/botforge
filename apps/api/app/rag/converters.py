"""Document conversion behind an interface (docs/14 §4.1, K1-1/K1-2).

**What this replaces.** `loaders.load_bytes()` dispatches four formats to `pypdf`,
`python-docx`, `csv` and a UTF-8 decode. `pypdf` returns a flat text stream with no headings,
no reading order, no table structure and no OCR — and on 2026-08-03 that is what turned a
telephone glyph into `\\x01` and a phone number's internal spacing into tabs, so the PII
detector matched nothing in a document that visibly contained a number. Better extraction is a
**safety** improvement here, not only a quality one (docs/14 §3.2 W1).

**Three implementations, and the third is never deleted.**

* `DoclingServiceConverter` — HTTP to a `docling-serve` container. Layout analysis, reading
  order, table structure, OCR. The ML weight lives in Docling's image, so **BotForge's own
  images gain no dependency at all** (docs/14 §4.1 Option B).
* `LegacyConverter` — today's `load_bytes`, wrapped. **This is the fallback and it stays
  forever.** Every rollout step in docs/14 §12 is a flag flip precisely because it exists.
* `build_converter()` — returns the legacy one unless Docling is both enabled and configured.

**Failure means fall back, never fail the document.** A `docling-serve` outage, a timeout, an
unparseable response, a format Docling rejects — all of it degrades to the legacy path with a
loud log. A client uploading a file must never be told their document is broken because an
internal service was down. That is the same fail-open rule every docs/11 guard layer follows,
and here it is even less negotiable: the failure mode is a permanently `failed` document row
that nobody re-drives.

**`DoclingDocument` JSON is persisted** (docs/14 §3.4) so that re-chunking never re-runs the
ML pipeline. That is what turns chunk size, the tokenizer and the chunker itself into
parameters the eval harness can optimise, instead of a one-shot commitment paid for by
re-converting every document in every org.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

import httpx

from app.core.config import settings
from app.core.logging import get_logger
from app.rag import loaders

log = get_logger("rag.converters")

#: `documents.extraction_backend` values. Stored so a re-ingest campaign is targetable and a
#: quality regression is attributable to the backend that produced it (docs/14 §6).
BACKEND_LEGACY = "legacy"
BACKEND_DOCLING = "docling"


@dataclass(slots=True)
class ConvertedDocument:
    """The output of any converter.

    `text` is what the PII scanner and the chunker read. `document` is the structured
    `DoclingDocument` when there is one — `None` from the legacy path, which is exactly why
    every consumer of it has to tolerate its absence.
    """

    text: str
    backend: str
    document: dict[str, Any] | None = None
    #: Free-form, logged rather than stored: page count, whether OCR fired, and so on.
    info: dict[str, Any] = field(default_factory=dict)

    @property
    def has_structure(self) -> bool:
        return self.document is not None


@runtime_checkable
class DocumentConverter(Protocol):
    name: str

    async def convert(
        self, data: bytes, *, filename: str | None, mime_type: str | None
    ) -> ConvertedDocument: ...


class LegacyConverter:
    """Today's `loaders.load_bytes`, behind the interface. **Never delete this.**

    It is the fallback for every Docling failure and the rollback for every step of the docs/14
    §12 rollout. It is also what keeps the existing test suite meaningful: the same bytes
    through the same parsers, reached through one more function call.
    """

    name = BACKEND_LEGACY

    async def convert(
        self, data: bytes, *, filename: str | None, mime_type: str | None
    ) -> ConvertedDocument:
        text = loaders.load_bytes(data, filename=filename, mime_type=mime_type)
        return ConvertedDocument(text=text, backend=BACKEND_LEGACY)


class DoclingServiceConverter:
    """HTTP client for `docling-serve`.

    Asks for **both** markdown and the `DoclingDocument` JSON in one call, because a second
    round trip would re-run the whole ML pipeline to produce something the first call already
    computed. The markdown feeds the PII scan and the legacy chunker; the JSON is persisted for
    K2's structure-aware chunking and for free re-chunking afterwards.

    The response shape is read defensively. `docling-serve` nests its payload under
    `document`, with per-format keys (`md_content`, `json_content`, `text_content`), and a
    version bump that renames one of those must degrade to the legacy converter rather than
    raise on a client's upload.
    """

    name = BACKEND_DOCLING

    def __init__(
        self,
        endpoint: str,
        *,
        timeout_seconds: float = 120.0,
        do_ocr: bool = True,
        do_table_structure: bool = True,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.endpoint = endpoint.rstrip("/")
        self._timeout = timeout_seconds
        self._do_ocr = do_ocr
        self._do_table_structure = do_table_structure
        self._transport = transport

    def _options(self) -> dict[str, Any]:
        return {
            # Both markdown and JSON in one conversion. Ordering matters to nothing but the
            # response keys; asking for both is what makes re-chunking free later.
            "to_formats": ["md", "json"],
            "do_ocr": self._do_ocr,
            "do_table_structure": self._do_table_structure,
            # docs/14 §3.6: chart understanding is a vision-language model and the single
            # largest RAM contributor. Off here; K3-3 turns it on deliberately.
            "do_picture_description": False,
        }

    @staticmethod
    def _read(body: Any) -> tuple[str, dict[str, Any] | None]:
        """`(text, docling_json)` out of a conversion response."""
        if not isinstance(body, dict):
            raise ValueError(f"docling response was not an object: {type(body).__name__}")
        payload = body.get("document")
        if not isinstance(payload, dict):
            raise ValueError("docling response has no `document` object")
        text = payload.get("md_content") or payload.get("text_content") or ""
        structured = payload.get("json_content")
        if isinstance(structured, str):
            # Some versions hand the JSON back as a string rather than an object.
            structured = json.loads(structured)
        if not isinstance(structured, dict):
            structured = None
        if not str(text).strip():
            # An empty extraction is a failure, not an empty document — fall back and let the
            # legacy parser have a go before anything is marked `failed` (docs/14 §8).
            raise ValueError("docling returned no text")
        return str(text), structured

    async def convert(
        self, data: bytes, *, filename: str | None, mime_type: str | None
    ) -> ConvertedDocument:
        files = {"files": (filename or "document", data, mime_type or "application/octet-stream")}
        async with httpx.AsyncClient(timeout=self._timeout, transport=self._transport) as client:
            resp = await client.post(
                f"{self.endpoint}/v1/convert/file",
                files=files,
                data={"options": json.dumps(self._options())},
            )
            resp.raise_for_status()
            text, structured = self._read(resp.json())
        return ConvertedDocument(
            text=text,
            backend=BACKEND_DOCLING,
            document=structured,
            info={"structured": structured is not None},
        )


def is_enabled() -> bool:
    return bool(settings.docling_enabled and settings.docling_endpoint.strip())


def unavailable_reason() -> str | None:
    if not settings.docling_enabled:
        return "disabled by configuration (DOCLING_ENABLED=false)"
    if not settings.docling_endpoint.strip():
        return "DOCLING_ENABLED is on but DOCLING_ENDPOINT is empty - no service to call"
    return None


def warn_if_misconfigured() -> None:
    """Enabled-but-unreachable is the state that must not be quiet.

    Disabled is a decision and says nothing. Enabled with no endpoint means every upload
    silently takes the legacy path, which looks exactly like Docling running and producing the
    same output — the Phase C lesson, again.
    """
    if not settings.docling_enabled:
        return
    reason = unavailable_reason()
    if reason is None:
        return
    (log.error if settings.env == "prod" else log.warning)(
        "docling_misconfigured",
        reason=reason,
        impact="every document is being extracted by the legacy pypdf path",
    )


def build_converter(
    *, transport: httpx.AsyncBaseTransport | None = None
) -> DocumentConverter:
    """The configured converter, or the legacy one. Never raises."""
    if not is_enabled():
        return LegacyConverter()
    return DoclingServiceConverter(
        settings.docling_endpoint.strip(),
        timeout_seconds=settings.docling_timeout_seconds,
        do_ocr=settings.docling_do_ocr,
        do_table_structure=settings.docling_do_table_structure,
        transport=transport,
    )


async def convert_with_fallback(
    data: bytes, *, filename: str | None, mime_type: str | None,
    transport: httpx.AsyncBaseTransport | None = None,
) -> ConvertedDocument:
    """Convert, degrading to `LegacyConverter` on **any** Docling failure.

    Deliberately a blanket `except Exception`. The alternatives were enumerated and every one
    is worse: a docling-serve outage, a 90-second timeout on a 500-page PDF, a format its
    parser rejects, or a response shape a version bump renamed all end the same way — a client
    sees `status=failed` on a document that the code already in this repo can read perfectly
    well. There is no class of Docling error where failing the upload beats using `pypdf`.
    """
    converter = build_converter(transport=transport)
    if isinstance(converter, LegacyConverter):
        return await converter.convert(data, filename=filename, mime_type=mime_type)
    try:
        return await converter.convert(data, filename=filename, mime_type=mime_type)
    except Exception as exc:
        log.warning(
            "docling_unavailable",
            error=str(exc)[:200],
            filename=filename,
            endpoint=settings.docling_endpoint,
            impact="fell back to the legacy extractor; the document still ingests",
        )
    return await LegacyConverter().convert(data, filename=filename, mime_type=mime_type)
