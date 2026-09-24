# Baseline (before any refactor)

Recorded 2026-09-24 on Windows 11, `master` @ c3b6ec9 with uncommitted edits (see REFACTOR-PLAN blockers).
Anything failing here is **pre-existing**, not a refactor regression.

| Check | Command | Result |
|---|---|---|
| Ruff | `ruff check app tests` (apps/api) | pass |
| Mypy | `mypy app` | pass, 217 files |
| Backend tests | `pytest -q` | **1097 passed, 13 failed, 4 skipped** (19 min) |
| Web typecheck | `npx tsc --noEmit` | pass |
| Web lint | `npx eslint .` | pass (no output) |
| Web unit | `npx vitest run` | 26 files, 187 tests, all pass |
| Migrations | `alembic current` | `0027_workflow_tests (head)` |

## The 13 backend failures: environment, not code

`tests/test_docling_chunking.py` (12) and `tests/test_rag.py::test_estimate_tokens` (1). Cause: the tiktoken
`cl100k_base` encoding cannot be downloaded from this machine (`ConnectionResetError 10054`), so the tokenizer falls back to
the `len/4` heuristic and the tests that assert exact token counts fail. The app logs
`tokenizer_unavailable ... pre-warm TIKTOKEN_CACHE_DIR`. Fix is environmental: pre-warm `TIKTOKEN_CACHE_DIR`.
CI presumably has network access; this was not verified.

## Not run

* Playwright E2E (needs API on :8010 with `LLM_FORCE_FAKE=true` and web on :3001).
* `npm run build`, widget build, Docker image builds, compose validation.
* Red-team corpus and retrieval-eval gates as separate CI steps (they run inside the full `pytest` above, but the
  retrieval keyword-eval script `scripts/eval_retrieval.py` was not run).

## Local environment notes

* Containers up: `botforge-postgres-1` (host port **5750**), `botforge-redis-1`. `.env` has `DATABASE_URL` on port
  **5433**, so tests need `DATABASE_URL=postgresql+asyncpg://…@localhost:5750/botforge` exported for the run. `.env` was not changed.
* Python 3.14 in `.venv` (CLAUDE.md says 3.11); everything above still passed.
