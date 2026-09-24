# FINAL VERIFICATION REPORT

Factual only. No scores, grades or praise. "Not run" is an outcome and needs a reason.

## Overall Status

One of: **PASS** / **PASS WITH FOLLOW-UP** / **BLOCKED**

`<two or three sentences: what is established, what is not, what blocks (if BLOCKED)>`

## Baseline

- Commit and state at start: `<...>`
- Baseline results and known failing identifiers: `<link to baseline note or summary>`
- Failures classified against the base: `<count by label, and how each was reproduced>`

## Security

| Area (only those that apply) | Result | Evidence / notes |
|---|---|---|
| | verified / finding / not applicable / not verified | |

Findings, in order of severity: path, who controls it, impact, evidence, recommended option, whether fixed.

## Architecture

- Boundaries checked and method: `<...>`
- Architecture tests: `<run / none exist>`, result: `<...>`
- Violations: `<list, each labeled violation / accepted exception / debt>`

## Tests

| Suite | Command source | Result | Counts | Notes |
|---|---|---|---|---|
| | | pass / fail / not run | | |

Failing tests, each with one label (baseline / new regression / environment / flaky / unknown) and evidence:

| Identifier | Label | Evidence |
|---|---|---|
| | | |

## Static Checks

| Check | Scope | Result |
|---|---|---|
| lint | | |
| typecheck | | |
| static analysis | | |
| dependency audit | | |

## Build

| Deliverable | Command source | Result | Tracked files changed by the build |
|---|---|---|---|
| | | | |

## Documentation

- Checked: `<documents>`
- Drift found and corrected: `<list>`
- Drift found and left (with reason): `<list>`

## Git Worktree

- Changes I made: `<files, with why>`
- Pre-existing changes I left alone: `<files>`
- Lockfile / generated-file status: `<...>`
- Untracked or local-only files: `<...>`
- Commits made: `<none | hashes>`
- Final state: `<clean | dirty, and why>`

## Regressions

`<none found | each: what, how reproduced, fixed or open>`

## Remaining Risks

`<each risk, and whether the cause is proven, inferred or unknown>`

## Optional Follow-Up

Items deliberately not done (unsolicited refactors, debt, improvements). Do not implement these in this pass.

## Final Readiness

State in plain terms whether the repository is a sound base for further work, and name any blocking item.
