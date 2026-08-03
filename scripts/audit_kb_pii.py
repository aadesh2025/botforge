#!/usr/bin/env python
"""Audit every knowledge base for contact details and secrets (docs/11 Phase B, B4).

    cd apps/api && ./.venv/Scripts/python.exe ../../scripts/audit_kb_pii.py
    cd apps/api && ./.venv/Scripts/python.exe ../../scripts/audit_kb_pii.py --apply
    make audit-kb-pii

**Python, not `.mjs` like the other scripts, on purpose.** The existing scripts drive the HTTP
API; this one needs the PII detector itself, and reimplementing "what a phone number looks
like" in Node would give the audit and the runtime two different answers — exactly the drift
the shared `_SECRET_PATTERNS` reuse exists to avoid.

**It scans chunks, not source files.** Chunks are what retrieval can actually return, they are
what the model quoted in the live incident, and they are still there when the original upload
has been rotated away or the URL has changed.

Read-only by default. `--apply` backfills `documents.pii_flags` for documents ingested before
migration 0015 — idempotent, re-runnable, and it never edits document text: removing PII from a
client's knowledge base is the operator's decision (ADR-054, docs/11 §6).

Exits **1** when anything is found, so it can be wired into CI later. Never prints a detected
value — kind and count only, the same rule the API and the logs follow.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "apps" / "api"))

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.chat.pii import scan_document_text
from app.core.config import settings
from app.models import Chunk, Document, KnowledgeBase, Organization

KIND_ORDER = ["secret", "email", "phone", "address"]


def _fmt(flags: dict[str, int]) -> str:
    parts = [f"{k}={flags[k]}" for k in KIND_ORDER if flags.get(k)]
    parts += [f"{k}={v}" for k, v in sorted(flags.items()) if k not in KIND_ORDER and v]
    return ", ".join(parts) or "-"


async def audit(apply: bool) -> int:
    engine = create_async_engine(settings.database_url)
    findings: dict[str, list[tuple[str, str, dict[str, int]]]] = defaultdict(list)
    scanned = 0
    backfilled = 0

    async with AsyncSession(engine) as session:
        orgs = (
            (await session.execute(select(Organization).where(Organization.deleted_at.is_(None))))
            .scalars()
            .all()
        )
        for org in orgs:
            kbs = (
                (
                    await session.execute(
                        select(KnowledgeBase).where(KnowledgeBase.organization_id == org.id)
                    )
                )
                .scalars()
                .all()
            )
            for kb in kbs:
                docs = (
                    (
                        await session.execute(
                            select(Document).where(Document.knowledge_base_id == kb.id)
                        )
                    )
                    .scalars()
                    .all()
                )
                for doc in docs:
                    rows = (
                        (
                            await session.execute(
                                select(Chunk.content)
                                .where(Chunk.document_id == doc.id)
                                .order_by(Chunk.ordinal)
                            )
                        )
                        .scalars()
                        .all()
                    )
                    if not rows:
                        continue
                    scanned += 1
                    flags = scan_document_text("\n".join(rows))
                    if apply and doc.pii_flags != flags:
                        doc.pii_flags = flags
                        backfilled += 1
                    if flags:
                        name = doc.filename or doc.source_url or str(doc.id)
                        findings[org.name].append((kb.name, name, flags))
        if apply and backfilled:
            await session.commit()

    print(f"\nScanned {scanned} ingested document(s) across {len(orgs)} organization(s).")
    if apply:
        print(f"Backfilled pii_flags on {backfilled} document(s).")

    if not findings:
        print("No contact details or secrets found.\n")
        return 0

    total = sum(len(v) for v in findings.values())
    print(f"\n{'ORGANIZATION':<28} {'KNOWLEDGE BASE':<22} {'DOCUMENT':<34} FINDINGS")
    print("-" * 110)
    for org_name in sorted(findings):
        for kb_name, doc_name, flags in findings[org_name]:
            print(f"{org_name[:27]:<28} {kb_name[:21]:<22} {doc_name[:33]:<34} {_fmt(flags)}")
    print(
        f"\n{total} document(s) carry contact details or secrets that this agent can retrieve "
        f"and quote.\nReplies are filtered as a backstop (ADR-053), but the reliable fix is "
        # ASCII only: a Windows console defaults to cp1252 and an em dash raises
        # UnicodeEncodeError partway through the report, which loses the findings.
        f"removing it from the source document.\nValues are deliberately not printed - open "
        f"the document in the Knowledge UI to see them in context.\n"
    )
    return 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument(
        "--apply",
        action="store_true",
        help="backfill documents.pii_flags (never edits document text)",
    )
    args = parser.parse_args()
    return asyncio.run(audit(apply=args.apply))


if __name__ == "__main__":
    raise SystemExit(main())
