---
name: engineering-verification
description: Senior-engineer verification and stabilization pass on an existing repository, plus a change-impact protocol for adding features safely. Discovers the project's real commands and architecture, establishes a baseline, separates regressions from pre-existing, environmental and flaky failures, verifies security boundaries, fixes only justified issues, and reports factually. Use to assess or stabilize a codebase, to check a recent change, or before implementing a non-trivial feature. Not for redesigns or unsolicited refactors.
---

# Engineering verification

A behavioral protocol for any coding agent. It contains no project-specific commands: discover them.

**Verification is not refactoring.** The existing architecture is the default. Preserve behavior. Make the
smallest change that fixes a proven problem. Record everything else as follow-up instead of doing it.

Depth lives in `references/` (read the one you need, when you need it). Fill-in forms live in `templates/`.

## Ground rules

1. **Evidence over assumption.** A claim in a report must trace to a command you ran, a file you read, or a
   reproduction. Documentation, comments and earlier reports describe intent; the code and the running
   result are the truth. When they disagree, believe the code and fix the document.
2. **Never claim a check passed if you did not run it.** Say "not run" and why.
3. **Never hide or reword a failure** to get a cleaner report. Never call a failure pre-existing without
   evidence (see Failure classification).
4. **Baseline before you modify anything.** Record what passes and fails on the untouched tree first.
5. **Do not invent commands.** Take them from repository documentation, CI configuration, manifests or
   scripts. If none exists for a check, report "no documented command" rather than improvising one.
6. **Do not start a rewrite.** No new layers, patterns, frameworks, dependency upgrades or directory moves
   unless the user asked for them or a verified failure cannot be fixed without one (then stop; see Stop
   conditions).
7. **Protect other people's work.** You did not write the uncommitted changes you find. Do not revert,
   reformat, stage or commit them.
8. **Report what you changed and what you left alone.** Unsolicited improvements go under Optional
   follow-up, not into the diff.

## Choose a mode

| The user wants to... | Mode |
|---|---|
| assess, stabilize or "check" an existing codebase or a recent set of changes | **A: Verification** |
| add or change a feature, and you must avoid collateral damage | **B: Feature safety** |
| redesign, migrate a framework, or clean up broadly | Neither. Say this protocol does not cover it; ask what outcome they want. |

If the request is ambiguous and a wrong guess is expensive, ask one specific question. Otherwise pick a
default, state it, and continue.

## Phase 0: Preflight (both modes)

1. **Git state.** Inspect status (staged, unstaged, untracked), current branch, recent commits, stashes, and
   whether the base is clean. Note every pre-existing modification and who plausibly owns it. Details:
   `references/git-discipline.md`.
2. **Concurrent agents.** Look for signs another agent or person is using the same worktree: `HEAD` moving
   between your checks, files changing that you did not touch, index or lock files, other running test or dev
   processes on shared resources. If so, **stop and tell the user** before running anything that writes to
   the tree or to shared services. Suggest an isolated worktree instead.
3. **Read the project's own instructions**, in this order: agent instruction files (whatever the repository
   uses), README and contributing docs, architecture docs and decision records, environment/setup docs, CI
   configuration. Note explicit rules (forbidden areas, required checks, "read X before touching Y") and obey
   them.
4. **Detect the stack** from manifests, lockfiles, build and test configuration. Record languages, package
   managers, frameworks, datastores, external services, deployment model, and whether it is a monorepo.
5. **Discover commands** for: install, lint, static analysis, typecheck, unit tests, integration tests,
   end-to-end tests, build, migrations. Source priority: documented command > CI job > manifest script >
   convention. Record where each came from. Prefer the CI form, because that is what "passing" means.
6. **Find shared resources** the checks will touch: databases, caches, queues, ports, files, external APIs,
   paid services. Decide how to avoid harming them (own instance, own namespace, dry run, mocks). Never run
   something that deletes or mutates data you did not create without reading it and doing a dry run first.
7. **Identify what you must not do**: production access, credentials you were not given, destructive scripts.

Deliverable: a short baseline note (`templates/baseline.md`) written before any change.

## Mode A: Verification

Run in order. Skip a step only if it does not apply, and say so. If the user scoped the pass (a commit range,
an area, one concern), review that scope in depth, still record the baseline and run the checks that cover it,
and list what was out of scope in the report.

1. **Discover and map.** Fill `templates/architecture-map.md`: top-level layout, domains and owners, layers,
   dependency direction, integration boundaries, public surfaces, background execution, generated code,
   test locations. Use tooling or a throwaway script to measure imports rather than guessing.
   Method: `references/architecture.md`.
2. **Baseline.** Run the discovered checks on the untouched tree. Capture exact counts, durations and the
   list of failing test identifiers. Method: `references/testing.md`.
3. **Architecture review.** Run existing architecture or dependency tests. Check dependency direction,
   cycles, layer violations, private-symbol imports across boundaries, duplicated abstractions, oversized
   or mixed-responsibility files. If rules are documented but not enforced, consider whether a small
   automated check would help; propose it, and add it only if the user's task includes it.
4. **Security review.** Identify the attack surfaces that actually exist in this project and verify only
   those. Method: `references/security.md`. If the product is multi-tenant, verify isolation (below).
5. **Tests.** Run unit, integration, security, isolation, architecture and frontend tests as they exist.
   Where an area has no tests, report the gap. Do not write broad new suites unprompted; add focused tests
   only for a fix you make or a boundary you were asked to verify.
6. **Static checks.** Lint, formatters in check mode, typecheck, static analysis, dependency audit if
   documented.
7. **Build.** Run the production build for each deliverable (apps, packages, images) using the documented
   command. Watch for tracked files the build modifies.
8. **End-to-end.** Read the E2E setup first: required services, ports, data, environment. Run it in an
   isolated stack if it would touch shared data or another session's services. If it cannot run, record the
   exact reason; do not claim it passed.
9. **Documentation consistency.** Check that README, architecture docs, decision records, environment docs,
   security docs and test instructions match the implementation. Correct factual drift only.
10. **Git review.** Review the complete diff. Classify every modified file (see Git). No unexplained change.
11. **Report** using `templates/verification-report.md`.

### Failure classification

Every failing check gets exactly one label, with the evidence that justifies it:

| Label | Required evidence |
|---|---|
| **Baseline failure** | Fails identically on the untouched base (same identifiers, same error), reproduced by you: run the base in a temporary worktree or checkout, not from memory or from a document. If you cannot reproduce the base, do not use this label; use Unknown and say why. |
| **New regression** | Passes on the base, fails with the changes, reproducible. |
| **Environment failure** | Cause is outside the code (missing network, credentials, service, disk, port, clock). Show the error that proves it. |
| **Flaky** | Passes and fails on the same code. Show repeated runs; record the pass/fail counts. A stall or dropped connection that vanishes on rerun is flaky or environmental until shown otherwise, and you say the cause is unproven. |
| **Unknown** | Everything else. State what you tried. Do not round Unknown up to a friendlier label. |

Where a failure looks unrelated to the current work, still confirm it against the base. When the same set
of failures appears in two runs, compare the identifier lists, not the counts.

### Multi-tenancy (only if the product is multi-tenant)

Identify the tenant boundary, where tenant context comes from, the authorization model and resource
ownership. Then test as a member of a *different* tenant against real resources of the first: read, list,
nested resources, search, update, delete, export, background jobs, webhooks, caches, queues, and a spoofed
tenant header or id. Expect refusal or an empty result, and confirm the owner's data is intact afterward.
One organization filter in one query does not prove isolation. Prove a test can fail before trusting it
(mutation check in an isolated worktree, never in a shared tree).

## Mode B: Feature safety

Use before implementing any non-trivial feature or behavior change. Non-trivial means it adds an entry point,
stored data, an outbound call, a permission, or a dependency, or it touches more than one domain. A change
whose location and effect are obvious and local can skip the written plan, not the search for existing
code. Method: `references/future-changes.md`.

1. **Understand the request.** Restate it in your own words with acceptance criteria. Ask one question only
   if a wrong guess would be expensive.
2. **Locate the owning domain.** Find where this concern already lives. The feature goes there.
3. **Find existing abstractions** (see Duplicate-abstraction protection). Reuse before creating.
4. **Write the impact plan** before editing (`templates/feature-impact.md`): expected files, files that must
   *not* change, API, data, security, authorization, tenant, integration, frontend, background-job, test and
   documentation impact, ripple effects.
5. **Security, access and tenant analysis** for the new surface, using `references/security.md`.
6. **Implement in small steps** along the plan. After each step run the narrowest relevant check.
7. **Test** the new behavior and its failure cases; add regression tests at the security boundary.
8. **Verify**: relevant broader suites, lint, typecheck, build, and the architecture checks if present.
9. **Report** using the feature section of `templates/feature-impact.md`.

### Change locality and budget

`new feature -> owning domain -> existing interface -> minimal dependencies.` Do not edit an unrelated
module because it is nearby or convenient.

Set a budget from the plan. If the change grows past it, or touches a file or domain the plan said it would
not (a working guide: more than about ten files, or more than one domain you did not expect), **stop and
explain the dependency chain** before continuing. Decide with the user whether: an existing abstraction
should be reused, a boundary is in the wrong place, the feature genuinely crosses domains, or the edit is
accidental. Do not keep editing to see whether it works out.

Do not combine a feature with a refactor, a dependency upgrade or a framework migration. Separate changes.

### Duplicate-abstraction protection

Before creating a service, manager, helper, utility, provider, client, repository, adapter, hook, context,
middleware, validator, or configuration mechanism:

1. Search for the concept by name, by synonym, and by behavior (who already makes this HTTP call, parses
   this format, checks this permission, reads this setting).
2. Check the neighboring modules and the shared/core area, and the tests, for how it is done today.
3. If an equivalent exists, reuse or extend it. If it does not fit, write one sentence saying why, in the
   plan. "I could not find it" is not a reason; widen the search first.
4. Prefer a narrow, named module over a generic bucket (`utils`, `helpers`, `common`, `misc`).

## Fixing, when justified

Fix only when all hold: the problem is verified; you can explain the cause; the fix is small and preserves
intended behavior; it needs no architectural change. Then:

1. State the finding and the smallest safe fix before editing.
2. Add or update a focused test that fails without the fix.
3. Make the fix. Touch as few files as possible.
4. Run the focused test, the neighboring suite, then the broader checks.
5. Re-verify the original failing check.

If a fix changes behavior that legitimate users may rely on, **stop and get a decision** first, and present
the trust-boundary analysis and the options. When you find the same class of bug on a sibling path, report it;
fix it only if it is the same small, behavior-preserving change and within the user's request.

A security fix that gates a capability by "who set it" is fragile if a less-privileged actor can later edit
the same record. Prefer a control owned by whoever operates the deployment, enforced at the point of use.

## No architecture cosplay

Do not introduce architecture because it looks sophisticated. Unless the repository already uses it or the
user asked, do not add: repository-per-module, service-per-class, factory-per-provider, interface-per-
function, microservices, event buses, dependency-injection frameworks, CQRS, or clean/hexagonal/DDD
rewrites. An abstraction needs a present reason: several implementations exist, an external system must be
isolated, tests need a substitute, or a boundary is being violated in practice. Do not split coherent files
or functions only to meet a line count.

## Stop conditions

Stop, report, and wait when any of these is true. Do not guess past them.

- Another agent or person appears to be modifying the same worktree or shared services.
- Production data would have to be read or changed, or credentials are needed and unavailable.
- The architecture or a security boundary cannot be determined confidently.
- The fix requires a broad redesign, an unexpected migration, or a dependency upgrade.
- Files you did not expect are changing, or a lockfile or generated file changes in a large unexplained way.
- A failure cannot be classified with evidence.
- Continuing would delete, overwrite or publish something that is hard to reverse.
- You found a serious security issue: report it clearly at once; do not fold it into a bigger rewrite.

## Safety

- **Destructive commands**: no force operations, hard resets, blanket cleans, recursive deletes of paths you
  did not create, or history rewrites without explicit instruction. See `references/git-discipline.md`.
- **Commits**: create them only when the task calls for it or the user asked; stage explicit paths only.
- **Secrets**: never print, log, commit or paste secrets, tokens, credentials or credentialed URLs. Mask
  connection strings in output. Edit only local, untracked configuration, and only when the task calls for it.
- **Processes and ports**: stop only processes you started. Use different ports and separate service
  namespaces for your own runs. Remove temporary worktrees, files and services you created.
- **Cleanup scripts and test wrappers** that delete data: read them, dry-run them, and confirm what they
  target before running.
- **Long or hung runs**: bound them with a timeout; enable a stack dump on stall if the tool offers one;
  do not leave background processes behind.
- **Verification side effects**: builds and installs can rewrite tracked files (lockfiles, generated code).
  Check the worktree after each such command.

## Reporting

Use the templates. The report is factual: exact counts, exact commands' outcomes, explicit "not run".
Do not use numerical scores, grades or praise. Name what changed, what did not, and what remains risky.
State cause as proven, inferred or unknown. Overall status is one of **PASS**, **PASS WITH FOLLOW-UP**,
**BLOCKED**.

## Files

- `references/security.md`: attack-surface identification and per-class methodology, SSRF trace, fix design.
- `references/architecture.md`: discovering boundaries, measuring dependencies, lightweight enforcement.
- `references/testing.md`: command discovery, baseline procedure, classification, flakes, E2E isolation.
- `references/git-discipline.md`: preflight, concurrency, staging, lockfiles, safe commands, worktrees.
- `references/future-changes.md`: impact plan, locality, duplicate search, feature report.
- `templates/`: `baseline.md`, `architecture-map.md`, `verification-report.md`, `feature-impact.md`.
