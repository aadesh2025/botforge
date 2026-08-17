"""What a client may upload into a knowledge base (docs/14 K3-1, K3-2).

## The gap this closes is not the one docs/14 predicted

docs/14 K3-2 reads as future work — *"gate email ingest on the docs/11 §6 PII workflow"* — on
the assumption that email becomes ingestible when Docling's `format-email` is switched on. It is
already ingestible **today, with no Docling at all**. `upload_document` validated nothing beyond
"the file is non-empty", and `loaders.load_bytes` ends in::

    # txt, markdown, json, or anything else -> decode as text.
    return data.decode("utf-8", errors="replace").strip()

An `.eml` is RFC-822 *text*. It sails through that branch and lands in the knowledge base
whole — every `From:`, every signature block, every direct dial, every other customer copied on
the thread. docs/14 §3.5 calls email "the highest-PII-density format you will ever ingest" and
docs/11 §6's review-and-clean workflow does not exist yet, so this is not a hypothetical to
schedule; it is a door that was already open. Egress redaction is a backstop, not a fix — that
is docs/11's own wording.

So the gate lands here, at upload, and it is **deny-by-default**: a format has to be listed to
be accepted. The alternative reading — accept anything and let the extractor cope — is what
produced the situation above, and it is the same shape as the pre-fix n8n visibility default
(ADR-042): permissive looks fine until it is holding something that matters.

## Refused is not the same as unsupported

Three outcomes, and the client-facing message differs because the operator action differs:

* **accepted** — a format the pipeline handles today.
* **gated** — the pipeline *would* handle it, but a prerequisite has not shipped. Email
  (docs/11 §6) and media (docs/14 K3-4/K3-5, which need their own Celery queue first, or one
  tenant's two-hour webinar starves every other tenant's document ingest). The message says so.
* **unknown** — refused with the list of what is accepted, rather than being decoded to
  mojibake and stored as a "document" nobody can retrieve anything useful from.
"""

from __future__ import annotations

from dataclasses import dataclass

#: Formats the pipeline handles today. Extension -> human label.
#:
#: The legacy extractors cover pdf/docx/csv/text; everything else here is text-shaped and goes
#: through the decode branch, which is genuinely correct for it. The richer formats docs/14 K3-1
#: lists (EPUB, ODF, LaTeX, images, Box Notes) are **not** here: they need Docling, Docling is
#: off everywhere pending K1-5, and listing a format the pipeline would silently turn into
#: mojibake is worse than refusing it.
ACCEPTED: dict[str, str] = {
    ".pdf": "PDF",
    ".docx": "Word document",
    ".csv": "CSV",
    ".txt": "plain text",
    ".md": "Markdown",
    ".markdown": "Markdown",
    ".json": "JSON",
    ".html": "HTML",
    ".htm": "HTML",
    ".rst": "reStructuredText",
    ".log": "plain text",
    ".yaml": "YAML",
    ".yml": "YAML",
}

#: Formats deliberately refused until a named prerequisite ships. The value is what the client
#: is told — written for the person uploading, not for us.
GATED: dict[str, tuple[str, str]] = {
    ".eml": (
        "email",
        "Email import is not enabled yet. Email threads carry contact details for people who "
        "never agreed to be in this knowledge base, so it stays off until the review workflow "
        "for flagged documents is in place.",
    ),
    ".msg": (
        "email",
        "Email import is not enabled yet. Email threads carry contact details for people who "
        "never agreed to be in this knowledge base, so it stays off until the review workflow "
        "for flagged documents is in place.",
    ),
    ".mp3": ("media", "Audio and video import is not enabled yet."),
    ".m4a": ("media", "Audio and video import is not enabled yet."),
    ".wav": ("media", "Audio and video import is not enabled yet."),
    ".ogg": ("media", "Audio and video import is not enabled yet."),
    ".flac": ("media", "Audio and video import is not enabled yet."),
    ".mp4": ("media", "Audio and video import is not enabled yet."),
    ".mov": ("media", "Audio and video import is not enabled yet."),
    ".webm": ("media", "Audio and video import is not enabled yet."),
    ".mkv": ("media", "Audio and video import is not enabled yet."),
}

#: Mime types that identify a gated format even when the extension does not. A client saving a
#: thread out of Outlook can easily end up with `thread.txt`; the browser still sends
#: `message/rfc822`. Checked in addition to the extension, never instead of it.
GATED_MIMES: dict[str, str] = {
    "message/rfc822": ".eml",
    "application/vnd.ms-outlook": ".msg",
}


@dataclass(frozen=True)
class FormatDecision:
    allowed: bool
    #: `accepted` | `gated` | `unknown`. `gated` and `unknown` both refuse; they differ in what
    #: the operator has to do about it, so they are not collapsed into one.
    outcome: str
    reason: str = ""
    #: `email` | `media` for a gated format, so the refusal can be counted by kind without
    #: parsing the message.
    kind: str = ""


def _extension(filename: str) -> str:
    name = (filename or "").strip().lower()
    dot = name.rfind(".")
    return name[dot:] if dot > 0 else ""


def accepted_extensions() -> list[str]:
    return sorted(ACCEPTED)


def classify(filename: str, mime_type: str | None = None) -> FormatDecision:
    """Decide whether this upload may enter the pipeline.

    Extension first, then mime type — a mime type is supplied by the client and is trivially
    wrong or absent, but when it names a gated format it is believed, because the only cost of
    a false positive here is a clear refusal message.
    """
    extension = _extension(filename)
    mime = (mime_type or "").split(";")[0].strip().lower()

    gated_by_mime = GATED_MIMES.get(mime)
    if gated_by_mime and gated_by_mime in GATED:
        kind, reason = GATED[gated_by_mime]
        return FormatDecision(False, "gated", reason, kind)

    if extension in GATED:
        kind, reason = GATED[extension]
        return FormatDecision(False, "gated", reason, kind)

    if extension in ACCEPTED:
        return FormatDecision(True, "accepted")

    if not extension:
        return FormatDecision(
            False,
            "unknown",
            "This file has no extension, so there is no way to tell how to read it. "
            f"Accepted formats: {', '.join(accepted_extensions())}.",
        )
    return FormatDecision(
        False,
        "unknown",
        f"{extension} files are not supported. "
        f"Accepted formats: {', '.join(accepted_extensions())}.",
    )
