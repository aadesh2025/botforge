# Two small follow-ups from K1-5 — implementation prompts

> Both are optional, independent, and small. Paste either or both into a fresh session. Neither
> depends on `docling-serve` being up (task 1 needs it running to *verify* the fix; task 2 needs
> nothing but a Python REPL).

---

## Task 1 — warm up docling-serve at startup

> **Status 2026-08-17 — done.** `converters.probe_reachable()` + `main.py` wiring, verified live
> end-to-end on a genuinely fresh container (124.6s → 8.1s on the next real conversion). See
> `apps/api/tests/fixtures/docling/README.md` §1 and `docs/14-KNOWLEDGE-PIPELINE-V2.md` §K1-5 for
> full detail, including the "report back" answer below.
>
> **Report back — does pinging vs. converting differ?** Yes, measured directly: many routine
> `/health` pings over the container's lifetime never once triggered model-loading log lines;
> only a real `/v1/convert/file` call does, and only when its `do_ocr`/`do_table_structure`
> options match what a real conversion will use (docling-serve caches pipelines by an options
> hash). A mismatched warm-up (text file, both flags off) only warmed the layout model and left a
> real conversion at 86.5s instead of ~6-8s.

### Context

`docs/14-KNOWLEDGE-PIPELINE-V2.md` §0a (K1-5 report) and
`apps/api/tests/fixtures/docling/README.md` §1 recorded a real, measured finding: the *first*
conversion against a freshly-started `docling-serve` took **124.6 seconds** — past the 120s
`DOCLING_TIMEOUT_SECONDS` default (`app/core/config.py:99`) — because it was loading the
CPU-only layout model cold. `convert_with_fallback()` correctly fell back to the legacy
extractor and logged `docling_unavailable`. A second, warm request finished in seconds.

**Not a bug.** The fallback did exactly what it should. The problem is purely operational: **the
first real client document uploaded after any `docling-serve` restart or deploy will silently
downgrade to the legacy extractor**, and nothing distinguishes that from `docling-serve` actually
being broken. Whoever is on call at that moment has no way to tell the two apart without reading
logs closely.

### What to add

A warm-up ping in `app/main.py`'s `lifespan`, following the **exact existing pattern** for
`embeddings.probe_reachable()` (`app/main.py:54`, called right after `_warn_missing_secrets()`):
non-blocking beyond a bounded timeout, logs loudly on failure, **never raises**, and is
disable-able for the test suite the same way `EMBEDDING_PROBE_ENABLED` disables the embeddings
probe.

```python
# app/main.py — inside lifespan(), near the existing embeddings.probe_reachable() call
await docling.probe_reachable()  # mirrors embeddings.probe_reachable(); see app/rag/converters.py
```

### Design constraints — read before writing this

- ⚠️ **Must not block application startup on a slow or unreachable `docling-serve`.** If the
  service is down, off, or still loading its model, the API must still come up. Cap the wait
  (a few seconds is enough to *kick off* a warm-up load without holding the process hostage —
  the actual model load can continue in the background on the `docling-serve` side after this
  call returns or times out).
- ⚠️ **`docling_enabled` gates this exactly like it gates conversion.** If `DOCLING_ENABLED` is
  `false` (today's default everywhere), skip the probe entirely — do not add network calls on a
  path that's off.
- **This is a hint, not a guarantee.** A restart *during* traffic, or a `docling-serve` crash and
  restart independent of the API's own lifecycle, will still hit a cold instance. The fix reduces
  the window; it does not close it. Say so in the log message if you add one at conversion time,
  and do not oversell this as "fixes cold starts."
- **New env var, if you add a configurable timeout for the probe separate from
  `DOCLING_TIMEOUT_SECONDS`**: goes in `.env.example` **and** `docs/ENV.md` (CLAUDE.md §2.6).
  If you reuse the existing `DOCLING_TIMEOUT_SECONDS`, say so explicitly in a comment so the next
  person doesn't assume there's a second knob.
- **Log field naming**: match the existing convention — `embeddings.probe_reachable()`'s
  counterpart log keys are the reference. A `docling_warmup_failed` / `docling_warmup_ok` pair
  with `elapsed_ms` is a reasonable shape, but check what the embeddings probe actually emits and
  mirror it rather than inventing a new naming style.

### Tests

- `DOCLING_ENABLED=false` → the probe is never called (assert no network call attempted)
- `DOCLING_ENABLED=true`, service unreachable → startup still completes, warning logged
- `DOCLING_ENABLED=true`, service slow → startup does not hang past the capped wait
- ⚠️ **Do not let this test suite make a real network call to a real `docling-serve`.** Follow
  the same mocking discipline `EMBEDDING_PROBE_ENABLED=false` in `conftest.py` already
  establishes for the embeddings probe — this is the same class of hazard.

### Verify against the real service (optional, needs Docker)

If `docling-serve` is reachable: restart it cold, start the API, confirm in the logs that the
warm-up fired **before** the first real client conversion request arrives, and that the first
real conversion no longer takes the ~125s hit. This is the only way to confirm the fix actually
closes the gap rather than just existing in code.

### Report back

- Whether the warm-up call itself has a meaningfully different cost profile than a real
  conversion (does pinging the service actually trigger the model load, or does the model only
  load on the *first conversion request specifically*? — verify this against the real service
  before assuming a lightweight health-check endpoint has the same warming effect)
- Update the README note in `apps/api/tests/fixtures/docling/README.md` §1 once this ships —
  it currently says "not fixed here"

---

## Task 2 — file the `PhoneNumberMatcher` wide-spacing gap

> **Status 2026-08-17 — measured, filed, not fixed**, per this task's own recommendation.
> Queried the real local Postgres (not a fixture): **5 documents, 18 chunks**, including the
> actual `Aurozen_AI_-_Knowledge_Base_and_Business_Profile.pdf` the 2026-08-03 incident came
> from. Searched for any chunk with a 3+-character whitespace run directly between two digits
> (the shape that defeated `PhoneNumberMatcher` in the fixture), and separately for any wide
> whitespace run near phone-context wording (`call`/`phone`/`contact`/`tel`/`mobile`/`whatsapp`).
> **Zero instances of either, across all 18 chunks.** Given the real fix's cost (an
> offset-remapping layer touching `find_pii()`'s core invariant, re-verifying every existing
> caller) against zero measured real occurrences, filed rather than fixed — exactly this task's
> own recommended outcome. Recorded inline in `app/chat/pii.py::_matchable()`'s docstring so the
> next session sees it without re-reading this file. Revisit if a real document ever surfaces the
> pattern, or if `docs/14`'s eval harness surfaces it as a live miss.
>
> **Caveat on the measurement's own limits:** 18 chunks is a small sample — this is a solo-founder
> dev database, not the full multi-org production corpus docs/11's session log references (that
> data, if it still exists, is not reachable from this machine/session). "Zero in 18" is real
> signal, not proof of "zero ever"; the filed decision is a bet on cost-vs-likelihood, not a claim
> the gap can't occur.

### Context

`app/chat/pii.py::_matchable()` (line 122) is a **length-preserving** cleanup pass: every
character maps to exactly one character (control chars, tabs, and whitespace categories become a
single space; newlines are kept as-is). This exists specifically so `find_pii()`'s returned
offsets stay valid against the *original* string — the output guard slices the original text with
those offsets, so a length-changing transform would corrupt every span after the first change.

K1-5 verified directly, in isolation from any PDF extraction:

```python
>>> from phonenumbers import PhoneNumberMatcher, Leniency
>>> list(PhoneNumberMatcher('+91     93453     27506', None, leniency=Leniency.VALID))
[]   # 5-space runs between digit groups: no match
>>> list(PhoneNumberMatcher('+91 93453 27506', None, leniency=Leniency.VALID))
['+91 93453 27506']   # single spaces: matches
```

**This is real and current — `_matchable()` cannot fix it.** Collapsing a run of five spaces into
one would shift every offset after that point, which is exactly the invariant `_matchable()` was
written to preserve. So this is not a bug in the existing code; it's a genuine, narrower gap than
the original 2026-08-03 incident (which was about control characters and tabs, both of which
`_matchable()` already handles correctly).

**⚠️ This task is almost entirely judgement, not code.** Read the rest of this prompt as a
decision framework, not a spec to implement blindly.

### The actual question to answer first

**How often does a real client document contain a phone number with wide (multi-space or
multi-tab-equivalent) irregular spacing between digit groups, as opposed to the
single-tab/control-character corruption the 2026-08-03 incident and `_matchable()` already
cover?**

This has not been measured. Before writing any fix:

1. Check whether the 12 orgs' existing ingested documents (referenced throughout `docs/11`'s
   session log, e.g. the 2026-08-03 audit) contain any real example of this pattern. If the
   original incident is the *only* known real-world instance and it was a tabs/control-char
   pattern (already fixed), this may be a theoretical gap rather than a live one.
2. If real examples exist, characterize the actual spacing pattern (how many chars, how
   consistent) rather than assuming "five spaces" generalizes.

### If it's worth fixing — the shape of a fix, and its cost

A length-preserving collapse of *multiple* whitespace characters into a single space is not
possible without an offset-remapping layer (transform text → keep a mapping table → translate
matched spans back to original-string offsets). This is a real, non-trivial change to
`_matchable()`'s contract, not a one-line fix:

- `_matchable()` currently returns `str`. A fix likely needs it to return `(str, offset_map)` or
  equivalent, and `_phone_matches()` / `find_pii()`'s span reporting needs to translate through
  that map instead of indexing directly.
- **Every existing caller and every existing test of `find_pii()`'s offsets needs to be
  re-verified against the new mapping**, since this touches the exact invariant the whole PII
  redaction and output-guard slicing depends on. This is high-blast-radius for a narrow gap.

### Recommendation, not a directive

Given the cost of a real fix vs. an unmeasured real-world frequency, this is a reasonable
candidate for **"file it, don't fix it yet"** — record as a known limitation (it already is, in
the fixtures README), and revisit only if:

- a real client document is found with this exact pattern, or
- `docs/14`'s eval harness (P0-2 / K1-5's own measurement discipline) surfaces it as a live
  retrieval/redaction miss on real data.

**Do not implement the offset-map fix speculatively** without first doing the measurement in the
section above — that is exactly the kind of unfalsifiable change `docs/11` Phase D and `docs/14`
P0-2 both exist to prevent.

### If you do decide to fix it

- New test cases in whatever test file covers `_matchable()`/`find_pii()`, covering: single
  space (already works), tab (already works, existing coverage), 2–3 spaces, 5+ spaces, mixed
  tab+space runs.
- ⚠️ Explicitly test that offsets returned by `find_pii()` are still correct for text *after* a
  collapsed run — this is the property most likely to silently break.
- Full existing PII/redaction/output-guard suite must stay green — this is a shared-invariant
  change, not an additive one.

### Report back

Either:
- "Measured against real data, found N instances / 0 instances of this pattern — here's why I
  did/didn't implement the fix," or
- If implemented: the offset-map approach taken, and confirmation the full existing PII suite
  passed unchanged.
