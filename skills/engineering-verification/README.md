# engineering-verification

A portable behavioral protocol that makes an AI coding agent work like a disciplined senior engineer inside a
repository it did not write. It contains no project-specific facts; the agent discovers the stack, commands and
architecture of whatever repository it is given.

## The problem it solves

Coding agents tend to assume a stack, invent commands, call every red test a regression, "fix" things nobody
asked about, restructure architecture that works, create a second copy of an abstraction that already exists,
spread a small feature across unrelated modules, and overwrite work in progress. This protocol replaces those
habits with: understand first, measure instead of guess, baseline before changing, classify failures with
evidence, reuse before creating, keep changes local, and stop when uncertain.

## The three modes

| Mode | Use it to | Default behavior | Output |
|---|---|---|---|
| **1. Investigation** | understand an unfamiliar or existing repository | read, analyze, report; no code changes unless asked | `templates/investigation-report.md` |
| **2. Verification** | decide whether the repository is a stable baseline, or check a recent change | baseline, run the checks that exist, classify failures, fix only justified issues, re-verify | `templates/verification-report.md` |
| **3. Feature safety** | add a feature without collateral damage | investigate, identify the owner, reuse existing abstractions, write an impact plan, implement locally | `templates/feature-impact-plan.md` |

It is not for redesigns, framework migrations or broad cleanups; it says so and asks what outcome you want.

## Contents

```
engineering-verification/
├── SKILL.md              the authoritative protocol; usable without the other files
├── README.md             this file
├── references/           deeper methodology
│   ├── investigation.md      how to investigate a repository; facts vs inferences vs open questions
│   ├── verification.md       baseline record, check sequence, fix loop, status rules
│   ├── security.md           risk-based attack-surface method, SSRF trace, tenant isolation, fix design
│   ├── architecture.md       discovering boundaries, measuring dependencies, lightweight enforcement
│   ├── testing.md            command discovery, running checks, failure classification, flakes, E2E
│   ├── git-discipline.md     preflight, concurrent sessions, worktrees, staging, lockfiles
│   └── feature-safety.md     impact plan, change locality, duplicate-abstraction search
└── templates/            reusable output structures
    ├── investigation-report.md
    ├── verification-report.md
    ├── architecture-map.md
    └── feature-impact-plan.md
```

`SKILL.md` holds the operating rules. References hold method. Templates hold output shapes. Nothing is
duplicated across them; agent-specific files are thin pointers with no protocol text.

## Using it

Point the agent at `SKILL.md` and name the mode:

- `Follow skills/engineering-verification/SKILL.md, mode 1 (investigation), on this repository.`
- `Follow skills/engineering-verification/SKILL.md, mode 2 (verification). Do not change application code
  unless a failure is proven a regression.`
- `Follow skills/engineering-verification/SKILL.md, mode 3 (feature safety), before implementing: <feature>.`
- Scope a pass: `..., mode 2, scoped to commits <a>..<b>.`

Expected outputs: an investigation report, a verification report ending in `PASS`, `PASS WITH FOLLOW-UP` or
`BLOCKED` (no scores), or a feature impact plan followed by a feature impact report. Every report separates
what was observed from what was inferred and lists what was not run.

## Installation

Copy the `engineering-verification/` directory into the repository, or a shared location, and keep its internal
structure: `SKILL.md` links to `references/` and `templates/` by relative path.

**Claude Code (adapter provided in this repository).** Project skills are directories under
`.claude/skills/<name>/` with a `SKILL.md` that has `name` and `description` frontmatter; this repository
already uses that layout. The adapter `.claude/skills/engineering-verification/SKILL.md` carries the same `name`
and `description` and tells the agent to read the canonical protocol here. Invoke with
`/engineering-verification`. To use the skill in another repository, copy this whole directory to
`<that repo>/.claude/skills/engineering-verification/`; the canonical `SKILL.md` already has valid frontmatter,
so no adapter is needed there.

**Other agents (no adapter provided).** The skill and rule formats of Codex, Gemini CLI, Cursor, OpenCode and
similar tools are not present or verifiable in this repository, so none are provided and none are guessed. The
protocol is plain Markdown: place the directory in the repository and add a pointer to it in the instruction
file that tool reads (check its documentation for the name and format), or paste the pointer into the session.
If a tool has its own skill or rule format, write a thin file in that format that points at `SKILL.md`; do not
copy protocol text into it.

## Portability

The core makes no assumption about language, framework, package manager, database, test runner, CI system,
agent or operating system. Commands are discovered from the target repository. It assumes git for its
examples and says how to adapt when the project uses something else. Examples in the references are
illustrative, never mandatory.

## Limitations

- It is a procedure the agent follows, not an enforcer; stop conditions rely on the agent noticing them.
- It cannot discover what is not in the repository or environment (production data, credentials, services you
  did not provide). It requires the agent to say so rather than guess.
- Concurrent-session detection is by observation (moving `HEAD`, unexpected changes, foreign processes).
- Security checks are conditional on the project having those surfaces; it is not a penetration test.
- Real checks can be slow and can touch shared services; the protocol requires isolation, but the environment
  must allow it.
- It does not cover redesigns, framework migrations or dependency-upgrade projects.

## Version

**engineering-verification v1.0.0** is the frozen baseline.

- The universal skill answers "what should an AI coding agent do?". Facts about a particular repository (its
  commands, layout, rules, decisions) belong in that repository's own instructions, never in this skill. Do not
  customize the skill per project.
- Changes are intentional and versioned with semantic versioning:
  **MAJOR** for breaking changes to the protocol's behavior; **MINOR** for new capabilities that do not
  invalidate existing behavior; **PATCH** for clarifications, corrections and non-breaking improvements.
- Keep the version in three places: the heading of `SKILL.md`, this section, and the commit message of the
  change. Record what changed in the commit that bumps it. The Claude adapter repeats the `description` line;
  when it changes, change it in both files.
