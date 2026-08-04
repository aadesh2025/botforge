# Policy documents (docs/11 §4-L3)

> **⚠️ DRAFT WORDING — NOT REVIEWED.** Every `.md` file in this directory was drafted by the
> implementing session and has **not** been reviewed by a human. They are live inputs to a
> classifier that decides whether a customer conversation is escalated, so the wording is
> product policy, not implementation detail. Read them before relying on the behaviour.
>
> Once reviewed, replace this block *and* `test_policies_are_flagged_as_unreviewed` together —
> the marker and the test that enforces it are one safeguard, and flipping only one of them
> removes it silently. Hot-reload means tuning the wording later needs no deploy.

Each file is one concern, loaded at startup and **hot-reloadable** (`reload_policies()`), so an
operator can tune wording without a deploy. They are concatenated into one system prompt for
`openai/gpt-oss-safeguard-20b`, which is a bring-your-own-policy classifier: it grades against
the text here rather than a fixed taxonomy, so editing these files *is* the tuning mechanism.

## Editing rules

- **Say what the level means to a human, not to a model.** These are read by a 20B model that
  follows plain English better than it follows jargon.
- **Every level needs a negative example.** Without one, the classifier drifts upward — an
  annoyed customer becomes "elevated" and the queue fills with noise nobody reads.
- **`crisis` must stay narrow.** It suppresses the bot's answer entirely and hands to a human.
  If it fires on ordinary frustration, operators stop trusting the red badge, and then it is
  worth nothing on the day it matters.
- Re-run `pytest tests/test_policy_guard.py` after any edit — the fixtures pin the graded
  examples, so a widened definition shows up as a test failure rather than in production.

## Files

| File | Returns | Drives |
|---|---|---|
| `distress.md` | `none` / `mild` / `elevated` / `crisis` | tone, alerting, and (crisis only) suppression |
| `abuse.md` | violation + category | flag for review |
| `off_topic.md` | violation + category | flag; Phase G uses it to skip a web search |
| `pii_request.md` | violation | flag; redaction is enforced separately in `output_guard` |
