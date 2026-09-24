# Refactor plan (Phase B) and audit findings

> Status (2026-09-24): S-01, S-02, A-02, A-03, A-01, A-07, R-01 done; the rest open — see the
> **Status** column at the end. Evidence for every item is in `REPOSITORY-MAP.md`; verification was done
> on 2026-09-24 against the working tree. Ranking: P0 security/data integrity · P1 architectural correctness ·
> P2 maintainability · P3 cosmetic.

## Headline

The backend is already in better shape than the refactor brief assumes: no file over 1 000 lines, no file-level
import cycle, thin routers, one abstraction per concept, no `utils`/`helpers` files, typed and linted clean.
A large restructure into a new tree would add risk and no clarity, so this plan **does not move directories**.
The valuable work is (1) two security findings that are behavior changes and need a decision, (2) closing the gap
between docs and code, (3) locking the current boundaries in with an architecture test.

## Blockers before any code change

* Working tree is dirty: `chat/pii.py`, `db/templates.py`, `llm/types.py`, `infra/docker-compose.yml`, `CLAUDE.md`,
  docs. These are in-progress edits that are not mine. Commit or stash them first; the plan touches `pii.py`'s
  neighbours and must not entangle with them.
* Local test DB: `.env` says Postgres port 5433, the running container is on 5750. Baseline used a one-off
  `DATABASE_URL` override; `.env` was not edited.

## P0: needs your decision (these change behavior, so they are outside a "preserve behavior" refactor)

### S-01 Any `editor`/`admin`/`owner` can make the API host spawn an arbitrary process
* Where: `tools/service.py:461 create_mcp_server` (only checks `TOOLS_MANAGE`), `:506 test_mcp_server_connection`,
  `tools/mcp_client.py:48-52` (`StdioServerParameters(command=..., env=...)`), `tools/schemas.py:103`.
* Why it matters: `editor` is the *client* role and holds `TOOLS_MANAGE`. POST a server with `transport=stdio`,
  `url_or_command=<any binary>`, then POST `/test-connection` → the API process runs it with the caller's `env`.
  That is remote code execution on the host by any tenant. `docs/17` open question 1 (MCP allowlist) has no recorded
  ADR answer, and `include_mcp` gating only covers *agent* use, not test-connection.
* Options: (a) reject `stdio` in the API unless a platform-level setting enables it and the caller is staff
  (recommended: smallest change, closes the hole, SSE keeps working); (b) command allowlist; (c) run stdio in a sandbox.
* Also: SSE `url_or_command` gets no SSRF check (see S-02), so an org can point the server at internal addresses.
* Tests required: non-staff `stdio` create → 403/422; SSE to a private IP → refused; existing `tests/test_mcp.py`
  `test_stdio_server_with_args_and_env` must be rewritten deliberately (it currently asserts the hole is allowed).

### S-02 SSRF guard is bypassable by redirect and by DNS rebinding
* Where: `rag/loaders.py:load_url` calls `_is_blocked_host(host)` once, then `httpx.AsyncClient(follow_redirects=True)`.
* Failure: a public URL that 302s to `http://169.254.169.254/...` or an internal host is fetched (only the first hop is
  checked); resolving the name twice (guard, then httpx) also allows rebinding. `_is_blocked_host` also does blocking
  `socket.getaddrinfo` on the event loop, and **no test references it**.
* Fix shape: check every redirect hop (manual redirect loop or an `httpx` event hook), pin the resolved IP, use
  `loop.getaddrinfo`. `tools/http_tool.py` and `webhooks/dispatch.py` already use `follow_redirects=False`; only the
  ingestion path is exposed.

### S-03 Tenant-supplied LLM `base_url` is fetched with no SSRF guard (found in the verification pass, NOT fixed)
* Where: `modules/credentials` (`CredentialCreate/Update.base_url`, any role with `tools:manage`, incl. `editor`) ->
  `llm/registry.py::build_chat_provider` -> `CustomProvider`/`OpenAICompatibleProvider` POSTs to
  `{base_url}/chat/completions` from the API host. `core/ssrf.py` is not applied anywhere in `llm/` or `credentials/`.
* Impact: an org member can aim the API host at loopback/private/metadata addresses with a fixed path suffix and
  see error text. Same class as S-01/S-02; narrower (POST, fixed suffix) but real.
* Not fixed here because it is a behavior change that needs your call: self-hosters may legitimately point a custom
  provider at a private-network endpoint (LAN vLLM/Ollama). Options: block private hosts for non-staff (like stdio),
  or an explicit `ALLOW_PRIVATE_PROVIDER_URLS` opt-in per deployment.

### R-01 Tenant isolation is by convention, and 47 flagged queries were only partly reviewed
* See `REPOSITORY-MAP.md` §7. No leak found in the ~15 reviewed; ~30 remain unreviewed. Plan: finish the review, add one
  parametrised cross-tenant test per resource that takes a client-supplied id (agents, conversations, documents, chunks,
  contacts, workflows/runs, channels, tools, MCP servers, API keys). No behavior change.

## P1: architectural correctness

### A-01 Docs claim a repository layer that the code does not have
* `CLAUDE.md §8`, `docs/02-ARCHITECTURE.md` (§module layout line 38, §Security line 110) say each module has
  `repository.py` and a base repository injects `organization_id`. In code: 0 module repositories; `BaseRepository`
  is used only in `tests/test_db.py`; 34 files query directly.
* Recommendation: **fix the docs, do not retrofit repositories** (34 files of churn on the most security-sensitive layer
  for no behavior gain). Record as an ADR: "isolation = org-scoped `_get_*` fetch + parent-scoped child queries,
  verified by R-01 tests". Leave `BaseRepository` in place, flagged as unused by app code (do not delete: prove unused
  first, and the ADR may choose to adopt it for new modules).
* Files touched: `docs/02-ARCHITECTURE.md`, `CLAUDE.md §8`, `docs/DECISIONS.md`. Untouched: all `app/`.

### A-02 SSRF guard lives in `rag/loaders.py` under a private name, imported by three other packages
* **Done (eb73d0f).** Moved `_is_blocked_host` to `core/ssrf.py` as `is_blocked_host` (identical behavior), updated
  `rag/loaders`, `tools/builtins`, `tools/http_tool`, `webhooks/dispatch`. Do this **before** S-02 so the fix has one home
  and a test. Removes the `webhooks → rag` edge from cycle #2.
* Files: 4 call sites + new `core/ssrf.py` + a new unit test. Rollback: revert the commit.

### A-03 Architecture tests (new `tests/test_architecture.py`, AST-only, no new dependency)
Encode what is true today so it cannot rot; each rule is a real invariant, not an aspiration:
1. no file-level import cycles under `app/` (currently zero);
2. `models` imports only `db.base`/`models`; `llm` imports only `core`/`models`/`llm`;
3. `core` imports nothing outside `core`/`models` (allowlist: `core/audit → models`, `core/metrics → app.__version__`);
4. no cross-package import of an underscore-prefixed name — **the audit undercounted: there are 23 today** (chat.inbound, worker.tasks, inbox, public, agent_tests, workflow_tests reuse private helpers of conversations/agents/workflows services; two routers import `orgs.deps._load_context`). Implemented as a ratchet: no new ones, fixed ones must be removed from the list. Promoting those helpers to public names is open item A-12;
5. routers import no `sqlalchemy.select` except an allowlist (`audit/router.py`);
6. `packages/widget` has no imports; `apps/web/src/components` never imports from `app/`.
* Package-level cycles #1-#3 in the map are recorded as **accepted** in the test's allowlist with a reason, not "fixed".

## P2: maintainability

| ID | Item | Decision |
|---|---|---|
| A-04 | `channels ↔ contacts` cycle (`contacts/service` imports `channels.base` types) | Fold the 104-line `contacts/service.py` into `channels/` (its only caller is `channels.service`) **or** leave. Low value; do only if A-03 is green and nobody else imports it. |
| A-05 | `modules/orgs/deps.py` is a de-facto core (`OrgContext`, `current_org`, ~40 importers) | **Leave.** Moving means touching ~40 files for a rename. Document in ADR as the accepted tenancy entry point. |
| A-06 | `tools`, `workflows`, `channels`, `webhooks`, `contacts`, `crm` sit beside `modules/` instead of inside it | **Leave.** Document the rule ("`modules/` = CRUD-style domains with a public router; sibling packages = engine/adapters"). A move touches ~100 imports and every test path for zero behavior gain. |
| A-07 | `docs/06-AI-ENGINE.md` tool-loop wording vs `chat/runtime` iterative loop (`max_iters`) | Sync docs to code (read `chat/runtime.py` and `chat/budget.py` first). |
| A-08 | `chat/inbound.py` (channel turns) and `conversations/service._prepare_turn` (web turns) may duplicate turn preparation | **Investigate only.** Both use `chat.assembly`; do not merge without a behavior-equivalence test. |
| A-09 | `chat/runtime.run_turn` 253 lines, `chat/inbound.events` 217 lines | **Leave.** `docs/11 §10a` and the no-context A/B rule apply; splitting the highest-risk function for a line count is the exact AI-refactor smell the brief warns about. |
| A-10 | `db/templates.py` holds agent prompt content inside `db/` | **Leave.** CLAUDE.md §12 requires an A/B re-run after any edit; it has uncommitted changes now. |
| A-11 | `.env` DB port drift (5433 vs container 5750) | Resolved 2026-09-24: gitignored `.env` and `infra/.env` now say 5750 (Windows reserves 5430-5729 after a reboot). `.env.example` stays at the canonical 5432. |

| A-12 | 23 cross-package imports of `_private` helpers (see A-03 rule 4), notably the turn pipeline in `conversations.service` reused by `chat.inbound` and `worker.tasks` | Promote to public names in small commits (rename + call sites, no logic change), deleting each line from `KNOWN_PRIVATE_IMPORTS`. This is also the real answer to A-08: the two turn paths share code, they do not duplicate it. |

## P3

* `apps/web/src/components/builder/tabs/channels-tab.tsx` (700 lines) – inspect for two responsibilities; split only if it has them.
* Two raw `fetch` calls outside `lib/api` (`analytics/page.tsx` export, `_bff.ts`): the second is the BFF layer and is
  legitimate; the first could move into `lib/api/analytics.ts`.
* Untracked root files (`admin-staff.png`, `.docx`, `designreference/`): keep out of the repo or add to `.gitignore`.

## Status

| Item | State |
|---|---|
| S-02 redirect SSRF + A-02 guard move | done, `eb73d0f` (tests: `tests/test_ssrf.py`) |
| S-01 stdio MCP / SSE SSRF | done, `35cd189` (tests: `tests/test_mcp.py`) — review existing prod rows with `transport=stdio` |
| A-03 architecture tests | done, `b3b4f07` |
| A-01 docs correction + ADR-084/085 | done |
| R-01 cross-tenant test sweep | done: `tests/test_tenant_isolation.py` (69 tests: 65 endpoint probes as a member of another org, spoofed `X-Org-Id`, list emptiness). No leak found. Mutation-checked: removing the org check in `agents._get_agent` fails 5 probes. Covers ~65 of the id-taking endpoints; workflow-run/test-run, agent-test and inbox sub-routes are not in the table yet |
| A-07 tool-loop wording | done in `docs/06 §3`, `docs/02 §3.1`, `docs/07` (the doc's iteration cap was accurate; the drift was the file path and the missing agentic budget) |
| A-04, A-12, P3 items | open, optional |

## Proposed execution order

1. Your decisions on S-01 / S-02 and the dirty tree.
2. R-01 tests (no behavior change, finds problems early).
3. A-02 (pure move) → S-02 fix → S-01 fix, each its own commit with its own tests.
4. A-03 architecture tests, then A-01 / A-07 docs + ADR.
5. Full suite, Playwright smoke, tag.

Explicitly **not** doing: directory restructure to the brief's target tree, repository-per-module, microservices,
splitting `run_turn`, frontend `features/` rename.
