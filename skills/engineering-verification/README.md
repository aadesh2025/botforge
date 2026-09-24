# engineering-verification

A behavioral protocol for coding agents. It has two jobs:

- **Verification mode**: assess and stabilize an existing repository. Discover its real commands and
  architecture, record a baseline, separate regressions from pre-existing, environmental and flaky failures,
  check security and architecture boundaries, fix only justified issues, and report factually.
- **Feature-safety mode**: before adding a feature, find the owning domain, reuse existing abstractions, write
  an impact plan, and keep the change local instead of rippling through unrelated code.

It is project-agnostic. It contains no language, framework or tool commands; the agent discovers them from the
repository. It is deliberately conservative: verification is not refactoring, and the existing architecture is
the default.

## When to invoke

Use it when you want to:

- stabilize or "check" a codebase before building on it, or after a batch of changes;
- confirm a security or architecture fix holds and was not bypassed elsewhere;
- produce an evidence-based readiness report;
- add a non-trivial feature without collateral damage.

Do not use it to redesign an architecture, migrate a framework, or do broad cleanup. The protocol will say so
and ask what outcome you want.

## Contents

```
engineering-verification/
├── SKILL.md              the protocol (usable on its own)
├── README.md             this file
├── references/           depth: security, architecture, testing, git-discipline, future-changes
└── templates/            baseline, architecture-map, verification-report, feature-impact
```

`SKILL.md` is the single source of truth. Everything else supports it. Agent-specific files are thin pointers
and contain no protocol text.

## Using it

Give the agent one instruction that points at `SKILL.md`, in whatever form your tool accepts:

- Verification: `Follow skills/engineering-verification/SKILL.md, mode A, on this repository.`
- Feature safety: `Follow skills/engineering-verification/SKILL.md, mode B, before implementing: <feature>.`
- One recent change: `Follow skills/engineering-verification/SKILL.md, mode A, scoped to commits <a>..<b>.`

The agent writes a baseline note first, works through the checks it can actually run, and ends with the report
from `templates/verification-report.md` (or the feature report from `templates/feature-impact.md`). Its status
is `PASS`, `PASS WITH FOLLOW-UP` or `BLOCKED`; there are no scores.

## Installation

Copy the `engineering-verification/` directory into the repository (or a shared location) and keep its internal
structure: `SKILL.md` links to `references/` and `templates/` by relative path.

### Claude Code (adapter provided in this repository)

Claude Code project skills are directories under `.claude/skills/<name>/` with a `SKILL.md` that has `name` and
`description` frontmatter; this repository already uses that layout. The adapter is
`.claude/skills/engineering-verification/SKILL.md`, a thin file that carries the same `name` and `description`
and tells the agent to read the canonical protocol here.

To use the skill in another repository with Claude Code, copy this whole directory to
`<that repo>/.claude/skills/engineering-verification/`. The canonical `SKILL.md` already has valid frontmatter, so
no adapter is needed in that case, and the relative links keep working.

### Other agents (no adapter provided)

The formats used by other agent tools (Codex CLI, Gemini CLI, Cursor, OpenCode and others) are not present or
verifiable in this repository, so no adapter files are provided for them and none are guessed. Because the
protocol is plain Markdown, it can be used without an adapter:

1. Put the `engineering-verification/` directory somewhere in the repository.
2. In the instruction file your agent reads for project guidance (check that tool's documentation for its
   name and format), add a short pointer such as:
   `For verification or feature-safety work, follow skills/engineering-verification/SKILL.md and read the files
   it references.`
3. Or paste that instruction into the session when you start.

If a tool has its own skill or rule format, write a thin file in that format that points at `SKILL.md`. Do not
copy the protocol text into it, so there is one source of truth.

## Keeping adapters honest

The Claude adapter repeats the `description` line from `SKILL.md`. When you change the description in
`SKILL.md`, change it in the adapter. Nothing else is duplicated.

## Limitations

- It is a procedure the agent follows, not a tool that enforces itself. It works only as well as the agent
  applies it; its stop conditions rely on the agent noticing them.
- It cannot discover facts that are not in the repository or the environment (production data, credentials,
  services you have not provided). It is required to say so rather than guess.
- Concurrent-session detection is by observation (moving `HEAD`, unexpected changes, foreign processes), so it
  is best effort.
- Multi-tenancy, SSRF and other security checks are conditional on the project having those surfaces; it does
  not replace a dedicated security assessment or penetration test.
- Running the project's real checks can take a long time and can touch shared services. The protocol tells the
  agent to isolate them, but the environment must permit that.
- It does not cover redesigns, framework migrations or dependency-upgrade projects.

## Examples

**Stabilize before building.** "Follow the engineering-verification skill, mode A. Do not change application
code unless a failure is proven to be a regression from my last three commits." Expected result: a baseline
note, a classified failure list, and a report ending `PASS WITH FOLLOW-UP` with optional follow-up items
unimplemented.

**Check a security fix.** "Mode A, scoped to the security review: confirm the URL-fetch fix cannot be bypassed
by other HTTP clients or background jobs." Expected result: the traced request path per client, sibling-path
findings reported (not silently expanded into a rewrite), and tests named.

**Add a feature safely.** "Mode B: add a new notification channel." Expected result: an impact plan naming the
owning area, the existing adapter contract to implement, files that must not change, and a stop if the diff
outgrows the plan.
