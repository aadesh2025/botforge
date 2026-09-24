# RISK-REGISTER.md — BotForge known risks (pre real-client / pre-audit)

> Compiled 2026-08-24 from the project's own session log (`CLAUDE.md` §11) and the
> `docs/11`/`docs/13`/`docs/14`/`docs/17` tracks. Every item here is something the
> project has already documented about itself — this is not new discovery, it's a
> single prioritized view of gaps that are currently scattered across ADRs and
> progress notes. Re-derive this list from the source docs periodically; it will
> go stale the moment a gap is closed or a new one is found.
>
> Scoring: **Severity** = how bad if it bites. **Likelihood** = how likely it bites
> given current usage (near-zero real traffic today). Both `Critical/High/Medium/Low`.
> Sorted by Severity × Likelihood-adjusted priority, worst first.

---

## P0 — Fix before onboarding any real paying client

| ID | Area | Risk | Severity | Likelihood today | Why | Recommended action |
|----|------|------|----------|-------------------|-----|---------------------|
| ~~R1~~ | Data protection | **✅ CLOSED 2026-09-23 (ADR-082).** ~~Backup script doesn't cover uploads.~~ `backup.sh`/`restore.sh` now cover the `uploads` volume (same script, same `backup` service, read-only mount of the SAME volume api/worker write to — no duplicate). Still open for **k8s** specifically — no RWX volume/backup story exists there (see R11). | n/a | n/a (was High/High) | Verified with a real backup→restore round trip against this project's own dev DB + uploads dir (48 tables, 2993 files): restored row counts and a `diff -rq` of the restored directory both matched the source exactly. Backward compatible — `UPLOADS_DIR` unset still gets the DB dump, now with a loud warning instead of a silent gap. | Closed — see ADR-082, `docs/09-DEPLOYMENT.md` §4, `docs/15-DEPLOYMENT-CAPACITY.md` §8.3. |
| R2 | PII exposure | **A live client KB document (aurozenai) was found to contain unredacted contact PII and is still flagged, not cleaned.** Egress redaction is a backstop, not a fix — the source document still has it. | High | Certain (already true today) | 2026-08-03 log: "the live `aurozenai` KB document is flagged and the contact details are still in it. Egress redaction is a backstop, not a fix." | Operator task, not code: open the flagged document, redact/re-ingest. This is the one item on this list that is pure ops work, not engineering. |
| R3 | Security validation | **No third-party penetration test or external red-team has ever been run.** Every attack fixture in the repo (docs/11 Phase D, docs/17's tool-result fixtures) was authored by Claude against its own code. | Critical | Certain (structurally true, not a "maybe") | Self-authored tests systematically miss what the author didn't think to test — this is true of any codebase, not a criticism specific to this one. | Before handling a real client's real data at any meaningful volume: commission an external security review. Do this once, not as an afterthought. |
| ~~R4~~ | Reliability | **✅ MEASURED 2026-09-23.** ~~No load or scale testing has ever been performed.~~ Real concurrency numbers now exist (`infra/perf/load_test.py`, docs/15 §11): zero HTTP-level errors at any tested concurrency (chat up to c=50, workflow runs up to c=25), but latency degrades close to linearly — two **identified, not yet resized** bottlenecks: no `pool_size`/`max_overflow` set on the async DB engine (asyncpg default caps at 15 concurrent connections per process), and the documented Windows dev `--pool=solo` Celery worker (one process, no parallelism) caps workflow-run throughput at ~3.3 req/s regardless of load. | n/a | n/a (was High, "rises fast with real usage") | Sizing (connection pool, worker concurrency) is a production capacity-planning decision, not a code bug — deferred to whoever sizes the real deployment, now with real numbers to size against instead of zero. | Measured — see `docs/15-DEPLOYMENT-CAPACITY.md` §11.1. Set `pool_size`/`max_overflow` and Celery worker concurrency deliberately (not on defaults) before promising any client an SLA. |
| ~~R14~~ | Reliability / data integrity | **✅ FIXED 2026-09-24 (ADR-083), one small residual.** Was: a client that dropped a streaming chat mid-reply never had the assistant reply persisted (and, when the drop landed early, lost the conversation and user message too) with HTTP 200 throughout — found by R4's load test. Now a dropped stream hands its reply to a Celery task (`chat.finalize_turn`) that recreates anything that never became durable; handles both ways Starlette ends a stream (`CancelledError` and `GeneratorExit`). | n/a (was High) | Residual ~0.5% | Verified on the real stack: concurrent load test 91/91 conversations, 91/91 user messages, **90/91** replies (was 0/91); 100 sequential early-disconnects → 100/100/100. **One unexplained straggler in ~190 requests was not chased.** Recovered replies are whatever had streamed so far (may be truncated). A drop during the widget path's pre-generation awaits can still lose that turn's user message. | Closed with residuals — see ADR-083 and docs/15 §11.2. Revisit only if real traffic shows missing replies. |

---

## P1 — Fix soon, real user-facing risk, not yet blocking

| ID | Area | Risk | Severity | Likelihood | Why | Recommended action |
|----|------|------|----------|------------|-----|---------------------|
| R5 | AI safety | **Distress/crisis detection has measured live gaps.** The 2026-08-10 live checklist run found real failures at items 7.2/7.3 (abuse aimed at the agent raised no flag live) while a direct re-run of the same input scored correctly — inconsistent, not solved. | Critical (user wellbeing) | Medium (depends on whether any deployed agent handles emotionally charged conversations) | Documented directly in the 2026-08-10 session log entry. | Re-run that checklist 3x (as the log itself recommends) before trusting the result either way. Do not treat one clean re-run as proof it's fixed. |
| R6 | AI safety | **L2/L3 guard models fail open, and both make a live external API call per turn on a shared platform key.** A Groq outage or rate-limit silently disables that whole safety layer with no visible signal to the operator. | High | Medium-High (already observed: "Running the checklist exhausts the Groq free tier... L3 then 429s") | 2026-08-04 and 2026-08-10 log entries both document this directly. | Add alerting on `guard_l2_unavailable`/`guard_l3_unavailable` so a silent fail-open is at least visible; consider a paid-tier key before real client traffic. |
| R7 | AI safety | **Grounding/fabrication is still 12/15 on the production model with no retrieved context** — no phase in docs/11 (Phase A through G) touches this. It's the guardrail track's own stated "weakest link." | High | High for any query outside a client's KB coverage | Stated explicitly in the docs/11 Phase G wrap-up: "grounding remains the weakest link at 12/15 fabricated." | This needs its own investigation, likely a stronger base model or a stricter no-context refusal policy — not a patch on top of the existing guardrail stack. |
| R8 | AI safety | **Cross-turn/accumulated prompt injection is uncovered by every layer.** An attack spread across 5 benign-looking messages with no single damning one passes screening entirely — stated as a known, structural gap, not a bug. | Medium-High | Low-Medium (requires a deliberately patient attacker) | 2026-08-04 log: "screening is per-message... caught by no layer." | Would need session-level (not per-message) analysis — a genuinely new capability, size it separately before committing to it. |

---

## P2 — Real gaps, lower urgency

| ID | Area | Risk | Severity | Likelihood | Why | Recommended action |
|----|------|------|----------|------------|-----|---------------------|
| R9 | RAG quality | Reranker is built and tested but enabled for zero live agents — retrieval quality is dense+keyword fusion only. | Medium | Low (quality, not security) | docs/13/14 log. | Enable per-agent once a real measured p50/p95 latency delta is available (already the stated blocker). |
| R10 | RAG quality | Docling (better PDF/scanned-doc parsing) blocked on missing real test fixtures (K1-5); structural chunking measured a regression and stays off. | Medium | Low | docs/14 K1-5/K2-6 entries. | Needs 3 real binaries (scanned PDF, table-heavy PDF, the known PII-incident PDF) committed before this can move — explicitly blocked, not forgotten. |
| R11 | Infra | k8s manifests are documented but not fixed for multi-replica uploads (needs RWX volume/object storage) — fine on the current single-box deploy, breaks the moment it's scaled to k8s. | Medium | Low today, High if/when k8s is adopted | docs/15 PROD-3 log entry. | Decide the object-storage migration before any k8s deployment attempt, not during one. |
| R12 | Roadmap | Phase 5 (Integration SDK) not built — by design, gated on real client workflow usage. | Low | N/A (deliberate) | This session. | Not a risk, listed here only so it isn't mistaken for an oversight. |
| R13 | Compliance | No SOC 2 / ISO 27001 / formal compliance work has been started. | Medium | Depends entirely on target customer segment | Not mentioned anywhere in the session log — genuine absence, not a documented gap. | Only relevant if targeting enterprise clients who require it — confirm before it's on the roadmap at all. |

---

## How to use this

- **Before onboarding client #1 with real data:** clear R2 and R3 at minimum (**R1
  closed 2026-09-23**, ADR-082; **R4 measured 2026-09-23**, see docs/15 §11; **R14 fixed
  2026-09-24**, ADR-083). R2 is a same-day
  fix (it's a document, not code). R3 is the one
  that needs a human decision (budget/vendor for an external review) — flag it to whoever owns
  that budget rather than trying to self-serve it with more self-authored red-team fixtures,
  which is the exact blind spot R3 describes.
- **Before promising any uptime/response-time SLA:** size the DB connection pool and Celery
  worker concurrency deliberately using the R4 numbers (docs/15 §11.1) — the defaults measured
  there are not production-sized.
- **Re-derive, don't just re-read, this file** once real usage starts — a risk register
  written before any real traffic is a prediction, not a measurement. The first real
  incident should prompt a rewrite, not just a new row.
