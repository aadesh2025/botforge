# Baseline

Record this before changing anything. Every later "pre-existing" claim is checked against it.

## Repository state

- Commit: `<hash>` on `<branch>`, `<date>`
- Modified tracked files before I started: `<list, or none>`
- Untracked files before I started: `<list, or none>`
- Stashes / operations in progress: `<none | detail>`
- Concurrent activity observed: `<none | what and how>`

## Environment

- OS / shell: `<...>`
- Language runtimes and package managers (versions): `<...>`
- Services available (name, host, port, who owns them): `<...>`
- Local configuration differences that matter (masked; no secrets): `<...>`
- Shared resources the checks touch and how I isolated them: `<...>`

## Discovered commands

| Check | Command | Source (doc / CI / manifest / convention) | Scope |
|---|---|---|---|
| install | | | |
| lint | | | |
| static analysis | | | |
| typecheck | | | |
| unit tests | | | |
| integration tests | | | |
| architecture tests | | | |
| e2e tests | | | |
| build | | | |
| migration check | | | |
| dependency audit | | | |

"no documented command" is a valid entry.

## Baseline results (untouched tree)

| Check | Result | Counts | Duration | Notes |
|---|---|---|---|---|
| | pass / fail / not run | | | |

## Failing tests at baseline

| Identifier | First error line | Classification | Evidence |
|---|---|---|---|
| | | baseline / environment / flaky / unknown | |

## Not run, and why

- `<check>`: `<exact reason>`
