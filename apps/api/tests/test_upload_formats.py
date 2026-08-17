"""Upload validation and the email gate (docs/14 K3-1, K3-2).

docs/14 §3.5 is unambiguous: *"Do not enable email ingest for clients until that workflow
exists"*, meaning docs/11 §6's review-and-clean pass over flagged documents. K3-2 schedules that
gate as future work, on the assumption email arrives with Docling's `format-email`.

**It had already arrived.** An `.eml` is RFC-822 text, `upload_document` validated nothing but
"non-empty", and `load_bytes` decodes anything it does not recognise as UTF-8. So the highest
PII-density format there is went in whole — headers, signature blocks, direct dials, and every
other customer copied on the thread. `test_an_eml_would_have_ingested_whole` pins the extractor
behaviour that made it possible, so the gate can never be removed on the belief that the
underlying path is harmless.
"""

from __future__ import annotations

import pytest

from app.rag import formats
from app.rag.loaders import load_bytes

_EML = b"""From: Priya <priya@example.com>
To: support@shop.example
Subject: refund for order AZ-4471

Hi, my order hasn't turned up. You can reach me on +91 98840 12345 any time.

--
Priya Raman | Head of Ops | Example Pvt Ltd | +91 98840 12345
"""


# ── the gate ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("name", ["thread.eml", "THREAD.EML", "archive.msg"])
def test_email_uploads_are_refused(name: str) -> None:
    decision = formats.classify(name)
    assert decision.allowed is False
    assert decision.outcome == "gated"
    assert decision.kind == "email"
    # The message has to say *why*, or the operator reads it as a bug and files a ticket.
    assert "not enabled yet" in decision.reason


def test_an_email_is_caught_by_mime_type_when_the_extension_lies() -> None:
    """Saving a thread out of a mail client easily yields `thread.txt`; the browser still
    sends `message/rfc822`. A gate keyed only on the extension would miss exactly that."""
    decision = formats.classify("thread.txt", "message/rfc822")
    assert decision.allowed is False
    assert decision.kind == "email"


def test_an_eml_would_have_ingested_whole() -> None:
    """The reason the gate exists, pinned as behaviour rather than described in a comment.

    This asserts what the *extractor* does, not what the API does. If someone later removes the
    upload gate believing the pipeline cannot read email anyway, this test still shows the
    signature block and the direct dial arriving intact.
    """
    text = load_bytes(_EML, filename="thread.eml", mime_type="message/rfc822")
    assert "priya@example.com" in text
    assert "+91 98840 12345" in text
    assert "Head of Ops" in text


def test_media_is_refused_and_says_so_differently_from_email() -> None:
    """Two gates, two prerequisites (docs/11 §6 vs docs/14 K3-4). One message would hide that."""
    audio = formats.classify("webinar.mp4")
    email = formats.classify("thread.eml")
    assert audio.outcome == email.outcome == "gated"
    assert audio.kind == "media"
    assert audio.reason != email.reason


# ── deny by default ──────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize(
    "name", ["policy.pdf", "notes.txt", "faq.md", "data.csv", "manual.docx", "page.html"]
)
def test_the_formats_the_pipeline_actually_handles_are_accepted(name: str) -> None:
    assert formats.classify(name).allowed is True


@pytest.mark.parametrize("name", ["payload.exe", "archive.zip", "sheet.xlsx", "book.epub"])
def test_everything_else_is_refused_rather_than_decoded_to_mojibake(name: str) -> None:
    decision = formats.classify(name)
    assert decision.allowed is False
    assert decision.outcome == "unknown"
    # Refusing without saying what *would* work turns a fixable mistake into a support ticket.
    assert ".pdf" in decision.reason


def test_a_file_with_no_extension_is_refused() -> None:
    decision = formats.classify("README")
    assert decision.allowed is False
    assert decision.outcome == "unknown"


def test_epub_and_odf_are_unknown_not_accepted() -> None:
    """docs/14 K3-1 lists these as formats to enable. They need Docling, which is off pending
    K1-5 — so listing them now would accept a file the pipeline turns into mojibake."""
    for name in ["book.epub", "notes.odt", "paper.tex"]:
        assert formats.classify(name).outcome == "unknown", name
