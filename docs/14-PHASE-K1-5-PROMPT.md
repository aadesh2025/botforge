# K1-5 — implementation prompt for Claude Code

> Paste into Claude Code on a machine with Docker (this needs real `docling-serve`, which the
> analysis session could not run — no Docker in that sandbox, and the fallback of installing
> Docling's Python library directly didn't fit either: `torch` alone is 503 MB against 3.6 GB
> free disk there). Full context: `docs/14-KNOWLEDGE-PIPELINE-V2.md` §0a and Phase K1.

---

## What already exists — do not regenerate these

`apps/api/tests/fixtures/docling/` has three real (reportlab-generated, not hand-typed) PDFs and
a README documenting their provenance:

- `table-heavy-pricing.pdf` — two real tables via `reportlab.platypus.Table`
- `scanned-refund-policy.pdf` — text rendered to a raster PNG as the whole page; **verified zero
  characters extractable via `pypdf`**
- `pii-incident-contact-page.pdf` — approximates the 2026-08-03 PII incident. **Read the README's
  caveat before writing assertions against this file**: it reproduces the *functional* failure
  (irregular whitespace defeats `phonenumbers.PhoneNumberMatcher`) but not the original's exact
  bytes (`\x09`/`\x01` — this fixture uses spaces and `■` instead, because `reportlab`'s font
  layer substituted them). **Assert on the functional property, not on specific byte sequences.**

**These three files are currently untracked.** `git add` them as part of this work, alongside the
README.

## What K1-5 requires

Per `docs/14` §11: *"hand-written fixtures cannot tell you what real extracted text looks
like"* — the whole point of K1-5 is validating against **real Docling output**, not the mocked
transport `tests/test_converters.py` already uses (that pattern's own docstring says it
intentionally never calls a real `docling-serve`). This task must actually run the service.

## Steps

1. **Bring up `docling-serve`** from the existing dev compose entry
   (`infra/docker-compose.yml:142`, image `ghcr.io/docling-project/docling-serve:latest`, port
   5001 per `DOCLING_ENDPOINT: http://docling:5001`):
   ```bash
   cd infra && docker compose up -d docling
   ```
   Wait for it to report healthy before converting anything. **This is a large image (several
   GB) and has never been pulled on this machine** — expect the pull itself to take a while.

2. **Convert each of the three fixtures** against the running service, using the existing
   `DoclingServiceConverter` (ADR-064) if it's wired up, or the raw `docling.service_client` API
   directly if that's faster to script standalone. Capture the real output for each:
   - extracted markdown/text
   - table structure for `table-heavy-pricing.pdf`
   - confidence report if available (see note below)
   - whether OCR fired at all for `scanned-refund-policy.pdf`
   - the extracted phone-number line for `pii-incident-contact-page.pdf`

3. **Write the golden-file test** (this is K1-5's literal deliverable — it does not exist yet;
   `tests/test_converters.py` was grepped with zero hits on these fixture names). Assertions,
   derived from what step 2 actually returns, not from what the spec predicted:
   - `table-heavy-pricing.pdf` → table structure is present and rows/columns are not flattened
     into word soup
   - `scanned-refund-policy.pdf` → OCR fallback fired (legacy `pypdf` gets 0 chars here; Docling
     with OCR should get real text back) — **verify this diff explicitly**, don't just assert
     "some text came back"
   - `pii-incident-contact-page.pdf` → after Docling's extraction **and** the existing
     `app/chat/pii.py` cleanup pass, `classify_contact()` / `phonenumbers.PhoneNumberMatcher`
     **does** find the phone number. This is the regression test for the original incident's
     class of bug, run against real (if approximated) corrupted input.

4. **Mark the test to skip cleanly when `docling-serve` isn't reachable** — this must not become
   a hard CI dependency on a multi-GB service being up. Follow whatever skip/mark pattern
   `conftest.py` already uses for other live-service-dependent tests (the L2/L3 guard-model
   pattern is the closest precedent — those are disabled by default in `conftest.py` and only run
   when explicitly enabled).

5. **Do not flip `DOCLING_ENABLED` to `true` anywhere by default.** Closing K1-5 proves the
   converter works against real output — it does not authorize turning Docling on for real
   clients. That's `docs/14` §12's staged rollout (one internal org first), a separate decision.

6. **Tear the service back down when done**, or note in the PR if you're leaving it running for
   further K-phase work. Per `docs/15-DEPLOYMENT-CAPACITY.md`, this is a memory-heavy service and
   the dev compose may not have the same resource limits ADR-069 added to prod — watch for OOM if
   other services are running alongside it.

## Report back

- The real diff between legacy `pypdf` output and Docling output for the scanned PDF (should be
  0 chars → real text)
- Whether the PII fixture's approximated corruption actually gets cleaned up correctly by the
  existing detector, or whether it exposes a gap the README didn't anticipate
- Any real confidence-report values observed (useful groundwork for K6-A, not required by K1-5)
- Update `docs/14-KNOWLEDGE-PIPELINE-V2.md` §0a: K1-5 row from ❌ to ✅ once the test is green and
  committed, and correct anything in this prompt or the fixture README that turned out wrong —
  leave the mistake visible with a note, don't silently edit it away (see how §0 of docs/14
  itself is written for the pattern to follow)
