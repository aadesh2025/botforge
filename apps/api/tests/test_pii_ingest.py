"""Ingest-time PII scanning (docs/11 Phase B, B2).

The rule this file exists to pin: the scan **flags and never rewrites**. A business's own
support documentation legitimately contains its public contact details, and silently mangling
a client's knowledge base is a worse outcome than the leak it prevents. The operator decides
what comes out; the code only makes it visible.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.chat.pii import scan_document_text
from app.models import Document, KnowledgeBase, Organization
from app.rag.ingest import ingest_document

CONTACT_PAGE = """Contact Us

Our support team is available Monday to Saturday, 10am to 7pm IST.
Email us at support@acme.com or call +91 80 4000 1000.
For billing questions write to billing@acme.com.
"""

CLEAN_DOC = """Refund Policy

Refunds are issued within 14 days of delivery. Start a return from your account
dashboard and the credit appears on your original payment method.
"""


def test_scan_counts_kinds_without_returning_values() -> None:
    flags = scan_document_text(CONTACT_PAGE)
    assert flags.get("email") == 2
    assert flags.get("phone") == 1
    assert "support@acme.com" not in str(flags)
    assert "4000" not in str(flags)


def test_scan_of_a_clean_document_is_empty_not_none() -> None:
    """`{}` (scanned, clean) and `None` (never scanned) are different states."""
    assert scan_document_text(CLEAN_DOC) == {}


def test_scan_reuses_the_shared_secret_patterns() -> None:
    """One definition of "what a secret looks like" across input, output and ingest."""
    flags = scan_document_text("internal note: the key is sk-abcdefgh0123456789ZZZZ do not share")
    assert flags.get("secret") == 1


def test_scan_handles_empty_and_whitespace() -> None:
    assert scan_document_text("") == {}
    assert scan_document_text("   \n\t ") == {}


async def _document(session: AsyncSession, text: str) -> Document:
    org = Organization(name="PII Ingest Org", slug=f"pii-ingest-{uuid.uuid4().hex[:8]}")
    session.add(org)
    await session.flush()
    kb = KnowledgeBase(
        organization_id=org.id,
        name="KB",
        embedding_provider="fake",
        embedding_model="fake-embed",
    )
    session.add(kb)
    await session.flush()
    doc = Document(
        knowledge_base_id=kb.id,
        organization_id=org.id,
        source_type="text",
        filename="doc.txt",
        status="queued",
        storage_path=None,
    )
    session.add(doc)
    await session.flush()
    return doc


@pytest.mark.parametrize(
    ("text", "expect_flagged"),
    [(CONTACT_PAGE, True), (CLEAN_DOC, False)],
    ids=["contact-page", "clean-policy"],
)
async def test_ingest_flags_but_never_blocks_or_mangles(
    db_session: AsyncSession, tmp_path, text: str, expect_flagged: bool
) -> None:
    """A flagged document still ingests, still chunks, and keeps its text byte-for-byte."""
    doc = await _document(db_session, text)
    path = tmp_path / "doc.txt"
    path.write_text(text, encoding="utf-8")
    doc.storage_path = str(path)
    await db_session.flush()

    await ingest_document(db_session, doc.id)
    await db_session.refresh(doc)

    # Ingest succeeded regardless of what was found — flagging is not blocking.
    assert doc.status == "ready", doc.error_message
    assert doc.chunk_count > 0
    assert doc.pii_flags is not None  # scanned
    assert bool(doc.pii_flags) is expect_flagged

    # And the stored text is untouched: the contact details are still there to be retrieved.
    from sqlalchemy import select

    from app.models import Chunk

    rows = (await db_session.execute(select(Chunk).where(Chunk.document_id == doc.id))).scalars().all()
    combined = "\n".join(c.content for c in rows)
    if expect_flagged:
        assert "support@acme.com" in combined, "ingest must not redact the client's own document"
