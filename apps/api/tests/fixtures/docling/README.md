# K1-5 golden fixtures — provenance

> Generated 2026-08-17 because no real client PDFs were available, then verified and corrected
> 2026-08-17 against a real, running `docling-serve` (see docs/14 §0a K1-5 for the full report).
> **Read this before trusting any test result built on these files.**

Per docs/14 §11: *"hand-written fixtures cannot tell you what real extracted text looks
like."* These are **not hand-typed text** — each is a real PDF produced by a real generation
pipeline (`reportlab`), verified against a real `docling-serve` (v2.119.0) rather than assumed.

## 1. `table-heavy-pricing.pdf`

Two real tables (pricing plans, regional SLAs) via `reportlab.platypus`/`canvas` — genuine table
grid structure in the PDF content stream, not text made to look tabular.

**Verified live:** legacy `pypdf` flattens both tables to word-soup (445 chars, no row/column
structure). Docling reconstructs both as real markdown tables with columns intact (912 chars,
`has_structure=True`). **Confidence: high, and now measured, not assumed.**

⚠️ **Cold-start note — fixed 2026-08-17 (docs/14 K1-5 follow-up task 1).** The first real
conversion against a freshly-started `docling-serve` took **124.6 seconds** (loading the CPU-only
layout/object-detection model), past the 120s `DOCLING_TIMEOUT_SECONDS` default, so
`convert_with_fallback()` correctly fell back to the legacy extractor and logged
`docling_unavailable`. `app/rag/converters.py::probe_reachable()` now fires a real (not
health-check) conversion at API startup to absorb that cost before any client upload can hit it —
called from `app/main.py`'s `lifespan`, gated by `docling_enabled` exactly like real conversion.
**Verified live, end to end, on a genuinely fresh container:** the probe gives up client-side
after 5s (`docling_warmup_kicked_off` logged) while `docling-serve`'s own job worker keeps
processing in the background — confirmed in its logs, finishing 81.8s later — and the next real
client-shaped conversion then took **8.1s instead of 124.6s**. This narrows the window; it does
not close it — a `docling-serve` crash/restart independent of the API's own lifecycle, or a
restart during live traffic, still hits a cold instance.

**⚠️ The warm-up must send a real, valid PDF with `do_ocr`/`do_table_structure` matching
production, or it barely helps — measured, not assumed.** `docling-serve` initializes pipelines
lazily, keyed by an options hash. A warm-up using a plain `.txt` file with `do_ocr=false,
do_table_structure=false` only warmed the layout model and cut the next real conversion to 86.5s,
not 6-8s — the OCR and table-structure models still loaded cold. Garbage bytes with a `.pdf`
filename fail `docling-parse` in ~2s, *before* any model loads at all, so they warm nothing.
`probe_reachable()` embeds a genuinely valid minimal PDF for exactly this reason.

## 2. `scanned-refund-policy.pdf`

Text rendered to a **raster PNG**, then the PNG placed as the entire page — genuinely zero
embedded text layer, not text set in an unusual font.

**Verified:** `pypdf` extracts 0 chars. Docling's OCR fires and extracts 419 chars of real,
readable text (`has_structure=True`). **Confidence: high, and now measured live.**

## 3. `pii-incident-contact-page.pdf` — corrected 2026-08-17, read this before trusting it

**What the real 2026-08-03 incident was:** a phone number's internal spacing arrived as **tab
characters (`\x09`)** and a ☎ glyph arrived as **`\x01`**, so libphonenumber matched nothing.

**This fixture still does not reproduce the incident byte-for-byte** — `reportlab`'s font
substitution turns a literal tab into ordinary space characters and the glyph into `■`
(U+25A0), not `\x01`/`\x09`. That limitation is unchanged from the original version of this file
and is accepted for the same reason as before: hand-authoring a raw PDF content stream with
literal control bytes in a `Tj` string was judged not worth it here (docs/14 §11 wants a real
generation pipeline, not hand-typed bytes — `reportlab` clears that bar even though it can't hit
this one specific escape sequence).

### ⚠️ The first version of this fixture had a real, verified bug — this is the mistake, left visible

The original file used **five-space runs** between digit groups
(`"+91     93453     27506"`), on the assumption (stated in this README, now known wrong) that
`app/chat/pii.py::_matchable()` would "normalize a run of `0x20` to exactly one space." It does
not, and structurally **cannot without breaking its own documented invariant**:
`_matchable()` maps every character 1:1 (one input char → exactly one output char) specifically
so that `find_pii()`'s offsets stay valid against the *original* string. Collapsing a run of five
spaces into one would shift every offset after it.

Verified directly, isolated from PDF extraction entirely:

```python
>>> from phonenumbers import PhoneNumberMatcher, Leniency
>>> list(PhoneNumberMatcher('+91     93453     27506', None, leniency=Leniency.VALID))
[]   # five-space runs: no match, in EITHER the legacy or the Docling extraction
>>> list(PhoneNumberMatcher('+91 93453 27506', None, leniency=Leniency.VALID))
['+91 93453 27506']   # single spaces: matches
```

So the original fixture **never actually exercised what K1-5 asks for** — a phone number the
detector finds after cleanup — through either converter. That is a gap in the fixture, not
(only) in the detector, and it went unnoticed because no test ever ran `find_pii()` against this
file's real extracted text until now.

**Fixed by regenerating the PDF with single-space digit separators** (still with the `■`
phone-icon substitution, still calling out the incident in its own body text). Verified live
against the real `docling-serve`, phone number now detected through **both** paths:

```
[legacy]  find_pii() -> phone '+91 93453 27506' (plus 3 emails)
[docling] find_pii() -> phone '+91 93453 27506' (plus 3 emails)
has \x01 in either extraction: False   has literal tab in either: False
```

**⚠️ Separately real and NOT fixed here:** `PhoneNumberMatcher` genuinely cannot match a phone
number with wide (multi-character) irregular spacing between digit groups, and `_matchable()`
cannot fix that without breaking its offset-preservation guarantee. If a real client document
ever has a phone number mangled this way (as opposed to single tabs/control chars, which
`_matchable()` does handle), it will still go undetected. This is a real, narrower gap than the
2026-08-03 incident, filed here rather than silently absorbed into "fixed the fixture."

## Recommendation

All three fixtures now demonstrate what they claim to, verified against a real `docling-serve`,
not asserted. Swap fixture 3 for a real client document if one ever becomes identifiable — it
would close the byte-exact-incident gap that regeneration cannot.
