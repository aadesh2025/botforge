# docs/14 — Knowledge Pipeline v2: Docling ingestion + four-stage retrieval

> **Status:** design specification. Nothing implemented. Execute phase by phase, on request.
> **Supersedes:** parts of `docs/13-AI-COOKBOOK-REVIEW.md` — see §0 for a correction.
> **Revision 2 (2026-08-12):** scope widened after an operator decision — see §1.1. Revision 1
> covered ~40% of Docling; this covers the agreed set.
> **Sources reviewed:** `docling-project/docling` @ v2.119.0 (1,631 files),
> `daveebbelaar/ai-cookbook` @ HEAD (207 files), BotForge `apps/api/app/rag/` and
> `migrations/versions/`.
>
> **This track sits outside the §1 autonomous contract in `CLAUDE.md`, for the same reason
> `docs/11` does.** Each phase adds a dependency, a service, or a per-turn external call.
> Execute a phase only when asked for it by name.

---

## 0a. Status — 2026-08-13

**Phase K0 is done, and K4 is built but enabled nowhere.** K1–K3 (Docling) and K5-2/K5-3 are
untouched.

| Task | Status |
|---|---|
| **P0-1** FTS literal | ✅ measured and fixed — the `EXPLAIN` is below, and it settles §0 |
| **P0-2** Eval harness | ✅ `make eval-retrieval`, frozen corpus, two CI gates, baselines committed |
| **K4-1/2/3** Reranker | ✅ protocol, no-op default, HTTP cross-encoder, platform key, fails open |
| **K4-5** ADR | ✅ ADR-063 |
| **K4-4** latency delta | ❌ needs a real deployment running a rerank service |
| **K5-1** per-KB `fts_config` | ✅ migration 0019, with the per-config GIN index §5.4 demands |
| **K1–K3** Docling | ❌ not started |

**§0's seq-scan question is answered.** Measured on PostgreSQL 16.14 with `enable_seqscan=off`:
the literal form reaches `Bitmap Index Scan on ix_chunks_content_fts`; the bind-parameter form
under `plan_cache_mode = force_generic_plan` gets `Seq Scan (cost=10000000000.00..)`. So the
custom-plan escape hatch this section hoped for exists only for the first ~5 executions of a
prepared statement — asyncpg pools connections, so production graduates to the generic plan and
seq-scans. `make explain-fts` re-runs it.

**Two things §5.4 and docs/13 both got wrong, corrected in code:**

1. **PostgreSQL 16 ships `tamil` and `hindi` dictionaries.** §5.4's "be honest about the fix:
   Postgres ships no Tamil or Hindi dictionary, `simple` is the realistic option" is false.
   `tamil` genuinely stems — `கொள்கைகள்` → `கொள்கை` — it is not a `simple` alias. `simple`
   remains right only for a language with no entry at all.
2. **§4.3's pipeline diagram describes something that was not running.** The keyword half scored
   **NDCG@10 0.0278** because `plainto_tsquery` ANDs every term, so RRF had one non-empty list
   and `hybrid` was byte-identical to `dense`. Fixed (ADR-062) → 0.6604. See docs/13 §8.

**What this changes for K1–K3.** §5.1's claim that the eval harness "is the only thing that makes
every other change here falsifiable" is now testable rather than aspirational: `make
eval-retrieval-full` prints a baseline, and a Docling re-chunk that does not move it is a
re-embedding campaign spent for nothing. K2-5's "a number, not a claim" now has somewhere to
come from.

---

## 0. Correction to docs/13

**`docs/13` §3 finding 3 and §4 R4a are WRONG.** I claimed BotForge has no GIN index on the
FTS expression. It does — `migrations/versions/0004_rag_indexes.py` creates both:

```sql
CREATE INDEX ix_chunks_embedding_hnsw ON chunks USING hnsw (embedding vector_cosine_ops);
CREATE INDEX ix_chunks_content_fts    ON chunks USING gin (to_tsvector('english', content));
```

I grepped `alembic/versions/` when the real path is `migrations/versions/`, got no match, and
concluded absence from a failed search. **A negative grep is not evidence of absence — it is
evidence you searched the wrong place.** Recorded here rather than quietly edited.

**The correction found something sharper.** The index is built on a *literal* regconfig, but
SQLAlchemy renders the query with a *bind parameter*:

```python
# app/rag/retrieval.py:69
tsvector = func.to_tsvector("english", Chunk.content)
# renders as:  to_tsvector(%(to_tsvector_1)s, content)
# index is on: to_tsvector('english',        content)
```

An expression index only matches when the planner can prove the expression is identical.
Two-argument `to_tsvector(regconfig, text)` is `IMMUTABLE` only with a constant config. With a
generic plan the `Param` node never matches the index's `Const` node and **Postgres falls back
to a sequential scan**. With a custom plan (first ~5 executions) parameter folding *may* let it
match. **Plan-dependent — measure, do not assert.** Task **P0-1**.

---

## 1. Executive summary

Two repos, two halves of one pipeline. They do not overlap.

| | Docling | ai-cookbook |
|---|---|---|
| Solves | **Getting content out of documents correctly** | **Finding the right chunk, and proving it** |
| Stage | Ingest (offline, background) | Retrieval (online, per turn) |
| BotForge gap | `pypdf` flat text, no headings, no OCR, no tables, 4 formats | No reranker, no eval harness |
| Latency impact | **None** (Celery worker) | **Yes — critical path** |
| Risk | Storage, media queue policy, VLM memory | p50 first-token budget |

- **Docling is the bigger and safer win.** It runs in the background, so it cannot touch the
  417 ms p50 first-token budget. It fixes a live safety bug (§3.2 W1) as a side effect.
- **`docling-slim` is modular.** Base is 8 packages. Run it as `docling-serve` and **BotForge's
  own images carry zero ML dependencies** — the weight lives in Docling's container.
- **The retrieval eval harness is the highest-leverage item overall**, because it is the only
  thing that makes every other change here falsifiable.
- **Total: 5 phases, 20 tasks.** K0–K2 are safe. K3 (media/ASR) is a new job class. K4
  (reranker) touches per-turn latency and needs an explicit decision.

### 1.1 Agreed scope (operator decision, 2026-08-12)

| Decision | Choice |
|---|---|
| Format breadth | **Broad, minus dead weight** — all document/email/EPUB/LaTeX/ODF/image formats; **exclude** XBRL, USPTO, JATS, EBCDIC, video-with-diarization |
| ML pipelines | Layout + table structure · OCR · **Chart understanding** · **ASR (audio/video)** |
| Persist `DoclingDocument` JSON | **Yes** |

**⚠️ Two of these cost more than they appear. Read §3.6 and §3.7 before committing.**
Chart understanding is a **vision-language model**, not a small classifier. ASR is a
**different class of job** from document ingest and needs its own queue, not a bigger timeout.

---

## 2. Understanding the problem

### 2.1 What actually goes wrong today

`docs/11 §9` records grounding as the weakest link: **12/15 fabricated** on
`llama-3.1-8b-instant`, and **no safety phase A–G touches it**. The 2026-08-02 incident showed
the mechanism:

```
visitor asks about opening hours
  → retrieval scores 0.0318, below the 0.35 threshold
  → NO context block is appended at all
  → model invents "Mon–Fri, 9am–5pm"   (KB says Mon–Sat 10am–7pm IST)
```

The prompt was rewritten and re-measured to 0/3 fabricated on that state. **That is a
mitigation, not a fix.** The root cause was retrieval failing to find a chunk that existed.

Every stage here attacks that root cause from a different side:

```
Docling extraction   → the fact is legible at all             (§3.2 W1)
More formats         → the fact is in the KB at all           (§3.5)
Heading-aware chunks → the fact is embedded with its context  (§3.3)
Reranker             → the right chunk beats the near-miss    (§5.2)
Eval harness         → you can prove any of the above         (§5.1)
```

### 2.2 Verified state of the code

| Component | File | Current implementation |
|---|---|---|
| Loaders | `rag/loaders.py:146` | `pypdf` · `python-docx` · `csv` · else `utf-8 decode` — **4 formats** |
| HTML | `rag/loaders.py:47` | `trafilatura` → markdown ✅ already good |
| Chunking | `rag/chunking.py:39` | Recursive **character** split |
| Token count | `rag/chunking.py:14` | `len(text) / 4` — an estimate, not a tokenizer |
| Chunk metadata | `rag/ingest.py:85` | `{filename, source_url}` only |
| Vector dim | `models/knowledge.py:18` | `EMBEDDING_DIM = 768`, **module-level constant** |
| Retrieval | `rag/retrieval.py:83` | pgvector cosine + Postgres FTS + RRF (k=60) |
| Indexes | `migrations/0004` | HNSW ✅ + GIN ⚠️ (§0) |
| Rerank / Eval | — | **neither exists** |

### 2.3 Spec drift already in the repo

`docs/03-DATABASE-SCHEMA.md:79` declares `chunks.metadata (jsonb: {page, heading, ...})`.
`docs/06-AI-ENGINE.md:63` says ingestion should *"attach metadata (page, heading, ordinal)"*.

**Neither is ever populated.** The column exists, the spec requires it, `pypdf` cannot produce
it. Docling closes this without a schema change — the column is already `jsonb`.

---

## 3. Part A — Docling (ingestion)

### 3.1 What Docling is

- **IBM Research Zurich**, hosted under the **Linux Foundation AI & Data**. MIT. v2.119.0,
  production-stable, active changelog.
- Converts **28 input formats** to one `DoclingDocument` — a structured tree (headings,
  sections, tables, figures, captions, reading order), not a text blob.
- **Runs fully locally.** No client data leaves your infrastructure.

### 3.2 The four core wins

**W1 — Layout-aware extraction fixes a live safety bug.**

On 2026-08-03 the PII audit reported `email=2, phone=0` against a KB that visibly contained a
phone number. Cause: PDF extraction delivered the ☎ glyph as `\x01` and the number's internal
spacing as **tabs**, so libphonenumber matched nothing. The fix was a length-preserving cleaned
copy in the detector — correct, but **a backstop on bad input**.

Docling produces structured text with real spacing. **The PII detector then sees a real phone
number.** A safety improvement, not only a quality one.

**W2 — `contextualize()`: chunks embedded with their heading path.**

Highest-value, least-obvious feature. `BaseChunker.contextualize(chunk)` returns the
metadata-enriched serialization intended to feed the embedding model:

```
# what BotForge embeds today
"Refunds are processed within 14 days of the original purchase date."

# what contextualize() produces
"Returns Policy
International Orders
Refunds are processed within 14 days of the original purchase date."
```

A visitor asks *"how long for a refund on my overseas order?"* — today that chunk carries no
signal it is about international orders, because the heading was discarded at chunk time.
**This is exactly the near-miss the 0.35 threshold then rejects.** One method call at ingest.

**W3 — OCR turns a hard failure into a working document.**

Today: `scanned PDF → pypdf → "" → LoaderError → status=failed`. A client uploads a scanned
policy and the product tells them it is broken.

**W4 — Table structure survives.** `do_table_structure=True` reconstructs row/column
relationships into real markdown tables. A pricing table today becomes word soup where numbers
lose their row — precisely the content shape that produces confidently wrong price answers.

### 3.3 Chunking: `HybridChunker`

Two passes over hierarchical chunker output:

1. **Split** only chunks exceeding the tokenizer's limit.
2. **Merge** undersized adjacent chunks *sharing the same headings and captions*
   (`merge_peers=True`).

Table controls: `repeat_table_header=True` re-emits the header on every chunk of a spanning
table; `omit_header_on_overflow` drops it for rows that only fit without it.

`DocMeta` — verified by introspecting installed `docling_core`, not read from docs:

| Field | Type | → `chunks.metadata` |
|---|---|---|
| `headings` | `list[str] \| None` | `heading` (section path) |
| `captions` | `list[str] \| None` | `caption` |
| `doc_items` | `list[DocItem]` | `page` (via provenance) |
| `origin` | `DocumentOrigin \| None` | `mimetype`, `binary_hash` |

### 3.4 Persisting the `DoclingDocument` — the architecture fix

**This was missing from revision 1 and it changes the risk profile of re-chunking.**

`DoclingDocument` round-trips losslessly: `save_as_json()` / `load_from_json()`,
`model_dump_json()` / `model_validate_json()` (verified on the installed package).

Without persistence, every chunking change re-runs the **full ML pipeline** over every document
in every org. With persistence:

```
convert ONCE (expensive: layout + OCR + tables + charts + ASR)
   └─▶ store DoclingDocument JSON
          └─▶ re-chunk N times, FREE          ← tune chunk size, try LineBasedTokenChunker,
                                                 change tokenizer, re-embed — no re-conversion
```

This turns chunking from a one-shot commitment into a **tunable parameter the eval harness can
optimise**. It is what makes §5.1's feedback loop actually usable.

**⚠️ Storage decision required (see §6).** These JSON blobs are large for a big PDF —
per-element geometry, provenance, table cells. Do **not** default them into a Postgres `jsonb`
column without measuring size against real client documents first.

### 3.5 Format coverage — agreed scope

Formats are **cheap**: mostly one small pure-Python parser each, and under `docling-serve` they
live in Docling's image, not BotForge's.

| Format | Extra | In scope | Why |
|---|---|---|---|
| PDF | `format-pdf` | ✅ | Core |
| DOCX / PPTX / XLSX | `format-office` | ✅ | Core client docs |
| HTML / Markdown | `format-web` | ✅ | Already served by trafilatura; Docling adds structure |
| CSV, TXT, AsciiDoc | base | ✅ | Already supported |
| Images (PNG/TIFF/JPEG) | base + OCR | ✅ | Screenshots, scanned pages |
| **Email (EML, MSG)** | `format-email` | ✅ | **See below — biggest omission in rev 1** |
| EPUB | `format-html` + `defusedxml` | ✅ | Manuals, handbooks |
| ODF (ODT/ODS/ODP) | `format-opendocument` | ✅ | LibreOffice clients |
| LaTeX | `format-latex` | ✅ | Cheap, technical clients |
| Box Notes | base | ✅ | Free |
| **Audio / Video** | `format-audio` | ✅ | **§3.7 — own phase, own queue** |
| XBRL | ~~`format-xml-xbrl`~~ | ❌ | Financial filings. Not this product. `arelle-release` is heavy |
| USPTO patents | ~~`format-xml-uspto`~~ | ❌ | Not this product |
| JATS articles | ~~`format-xml-jats`~~ | ❌ | Academic publishing. Not this product |
| EBCDIC | ~~base~~ | ❌ | Mainframe encoding |
| Video + diarization | ~~`format-video`~~ | ❌ | `resemblyzer` → `webrtcvad`, **no wheels, needs a C compiler**. Docling excludes it from its own `all` bundle for this reason |
| HTML render | ~~`format-html-render`~~ | ❌ | Pulls Playwright. Not needed server-side |

**Email deserves its own paragraph.** You are building a **customer support** product. Your
clients' single richest knowledge source is years of resolved support threads — the exact
questions real customers ask, in their words, with the answers that worked. Revision 1 did not
mention it. `format-email` handles `.eml` and `.msg` natively.

**⚠️ Email is the highest-PII-density format you will ever ingest.** Every thread carries
signatures, direct dials, personal addresses, and other customers' details. `scan_document_text()`
already runs at ingest (`ingest.py:73`) and `pii_flags` is populated — but the docs/11 §6 operator
workflow (review flagged documents, clean the source) is **still outstanding** and no code
replaces it. **Do not enable email ingest for clients until that workflow exists.** Egress
redaction is a backstop, not a fix — that is docs/11's own wording.

### 3.6 ⚠️ Chart understanding is a VLM

You selected chart understanding. It is worth having — a pricing or comparison chart is
currently *invisible* to your KB. But be clear on the cost:

```python
# docling/datamodel/chart_extraction_options.py
class ChartExtractionModelKind(str, Enum):
    GRANITE_VISION    = "granite-vision"
    GRANITE_VISION_V4 = "granite-vision-v4"   # default
```

- It runs **Granite Vision**, a vision-language model — not a small classifier.
- It requires `models-vlm-inline`: `transformers`, `accelerate`, `qwen-vl-utils`, `peft`.
- Three prompt modes: `chart2csv` (default on), `chart2code`, `chart2summary` (both default off).
- Gated behind `do_picture_description` / picture classification, so **it only fires on documents
  that actually contain figures** — the cost is per-chart, not per-document.

**Recommendation:** enable `chart2csv` only, leave `chart2code` and `chart2summary` off. A CSV
table is what retrieval and the chunker can use; generated Python is noise in a support KB.

**⚠️ This is the single largest RAM contributor on docling-serve.** Size the container for it, and
treat it as the first thing to disable if the service is memory-constrained.

### 3.7 ⚠️ ASR is a different class of job

You selected audio/video. It is a real product feature — *"upload your onboarding webinar, the
agent answers from it"*. But it does not belong in the document queue.

| | Document ingest | Media ingest |
|---|---|---|
| Typical duration | 1–30 seconds | **Minutes to hours** |
| Input size | KB–MB | **Hundreds of MB** |
| Failure cost | Retry is cheap | Retry is very expensive |
| Model | Layout/OCR | Whisper (`WHISPER_TINY` … `WHISPER_LARGE`) |

**⚠️ Sharing one Celery queue means one client's 2-hour webinar backlog starves every other
client's document ingestion.** This is a multi-tenant fairness problem, and it is the same class
of mistake as the pre-fix n8n visibility default: it looks fine with one tenant and is wrong with
twelve. **Media gets its own Celery queue and its own worker.**

Also required before enabling:

- **Per-org media quota** (minutes/month). Unbounded ASR is unbounded compute spend.
- **Whisper model choice per deployment.** Default is `WHISPER_TINY` — fast, and too weak for
  accented or technical speech. `WHISPER_TURBO` or `WHISPER_DISTIL_LARGE_V3` are the practical
  quality/speed picks. **Measure on real client audio before choosing**; a transcript with wrong
  product names is worse than no transcript, because it grounds the model in falsehoods.
- **Upload size cap + explicit timeout**, separate from `document_timeout`.

### 3.8 ⚠️ Packaging traps found by installing it

**Trap 1 — `chunking-openai` still imports `huggingface_hub`.** Installing
`docling-core[chunking-openai]` (the tiktoken path chosen to *avoid* HF) and importing the chunker
fails:

```
ModuleNotFoundError: No module named 'huggingface_hub'
  chunker/__init__.py → hybrid_chunker.py → line_chunker.py
    → tokenizer/huggingface.py → from huggingface_hub import hf_hub_download
```

`LineBasedTokenChunker` imports the HF tokenizer unconditionally. **Pin `huggingface_hub`
explicitly** even on the OpenAI path. Reproduced, not inferred.

**Trap 2 — never `pip install docling`.** Always the explicit extras list, or `torch`,
`transformers` and `accelerate` land somewhere you did not intend.

**Trap 3 — RapidOCR breaks on read-only filesystems.** Called out in Docling's own
`PdfPipelineOptions` docstring. Provide a writable model-cache volume, or use Tesseract.

**Trap 4 — XML parsers are XXE surface.** Docling pins `defusedxml` for exactly this reason.
Excluding XBRL/USPTO/JATS removes three parsers you had no use for anyway — a security win, not
only a size one.

### 3.9 Target dependency set

```
docling-slim[
  format-pdf, format-office, format-web, format-opendocument,
  format-latex, format-email, format-audio,
  models-local, models-vlm-inline,
  feat-ocr-rapidocr, feat-chunking
]
+ huggingface_hub          # Trap 1
# EXCLUDED: format-xml-*, format-video, format-html-render, models-remote
```

Under `docling-serve` (§4.1 Option B) this is **Docling's image**. BotForge's worker installs
only `docling-slim[service-client]` — `httpx`, `websockets`, `typer`, `rich`.

---

## 4. Architecture

### 4.1 Deployment shape

**Option A — in-process (Docling inside the Celery worker).** Simple, no network hop. But with
`models-local` + `models-vlm-inline` + Whisper the worker image is very large and models load per
worker process. **Not viable at the agreed scope.**

**Option B — `docling-serve` as its own compose service. ★ required at this scope**

```
┌──────────┐   ┌───────────────┐   ┌──────────────────────┐
│ FastAPI  │   │ celery worker │   │    docling-serve     │
│  (api)   │──▶│  q=documents  │──▶│  layout · OCR ·      │
└──────────┘   └───────────────┘   │  tables · charts(VLM)│
                       │            │  · ASR              │
┌───────────────┐      │            └──────────────────────┘
│ celery worker │──────┘                      ▲
│   q=media     │─────────────────────────────┘
└───────────────┘   (§3.7 — separate queue, separate worker)
        │
        ▼
┌────────────┐   ┌──────────────────┐
│ Postgres   │   │  object storage  │
│ + pgvector │   │  DoclingDocument │
└────────────┘   │  JSON (§3.4/§6)  │
                 └──────────────────┘
```

| Criteria | A: in-process | B: docling-serve |
|---|---|---|
| Worker image | **Huge** (torch + VLM + whisper) | **Tiny — no ML deps** |
| Cold start | Slow, per worker | Unaffected |
| Scaling | Coupled to worker count | **Independent** |
| GPU later | Must GPU every worker | **Just the one service** |
| Failure isolation | A bad PDF can OOM the worker | **Contained** |
| Ops complexity | Lower | One more service |

**Design behind an interface regardless**, so A↔B is a config switch:

```python
class DocumentConverter(Protocol):
    async def convert(self, data: bytes, *, filename: str | None,
                      mime_type: str | None) -> ConvertedDocument: ...
```

Implementations: `DoclingServiceConverter` (B) · `DoclingLocalConverter` (A) ·
`LegacyConverter` (today's `loaders.load_bytes`, **never deleted** — it is the fallback).

### 4.2 Target ingest pipeline

```
Document row (queued)
  │
  ├─▶ 1. ROUTE     media (audio/video) → q=media
  │                 everything else    → q=documents
  │
  ├─▶ 2. CONVERT   docling-serve → DoclingDocument
  │                 · layout · reading order · table structure
  │                 · OCR if scanned · chart2csv if figures · ASR if media
  │                 ⤷ on ANY failure: LegacyConverter  ← never regress
  │
  ├─▶ 3. PERSIST   DoclingDocument JSON → object storage (§3.4)
  │
  ├─▶ 4. PII SCAN  scan_document_text(markdown_export)
  │                 (now runs on clean text — §3.2 W1)
  │
  ├─▶ 5. CHUNK     HybridChunker(tokenizer, max_tokens, merge_peers=True)
  │                 ⤷ contextualize() → embed_text
  │                 ⤷ DocMeta → {heading, caption, page}
  │
  ├─▶ 6. EMBED     embedder.embed([c.embed_text ...])   ← NOT c.content
  │
  └─▶ 7. STORE     Chunk(content=raw, meta={...}, embedding=vec)

  RE-CHUNK PATH:   step 3 → 5 → 6 → 7      (skips conversion entirely)
```

**⚠️ Store `content` raw, embed `contextualize()`.** The heading path improves the *vector*; it
must not be shown to the visitor or counted twice against the context budget. `content` remains
the citation text; the enriched string is embedding input only and is not persisted.

### 4.3 Target retrieval pipeline

```
query
  ├─▶ dense  (pgvector cosine, HNSW)  ─┐
  ├─▶ sparse (Postgres FTS, GIN)      ─┤─▶ RRF k=60 ─▶ top-50 ─▶ rerank ─▶ top-k
  └── candidate_k = 50 (today: 20)     │              (exists)   (NEW)
```

---

## 5. Part B — ai-cookbook (retrieval)

### 5.1 The eval harness — do this first

From `knowledge/hybrid-retrieval/docs/build-your-own-eval.md`. Five steps, ~$0.05:

1. Sample ~100 chunks from a real KB.
2. Prompt a small model per chunk: *"generate one realistic question a user would ask that this
   answers, in their own words, not the document's phrasing, under 20 words."*
3. Emit `corpus`, `queries`, `qrels(query_id, source_chunk_id, 1)`.
4. *(Recommended)* LLM-as-judge over the top-20, so a **different but also correct** chunk does
   not score 0.
5. Compute NDCG@10 per variant.

NDCG@10 in pure numpy — no dependency:

```python
def ndcg_at_k(predicted_ids: list[str], relevant: dict[str, int], k: int = 10) -> float:
    dcg = sum(relevant.get(d, 0) / math.log2(r + 2)
              for r, d in enumerate(predicted_ids[:k]))
    ideal = sorted(relevant.values(), reverse=True)[:k]
    idcg = sum(rel / math.log2(r + 2) for r, rel in enumerate(ideal))
    return dcg / idcg if idcg > 0 else 0.0
```

**Why first.** `docs/11` already paid for this: Phase D exists because every recall figure before
it was measured against probes written in the same session as the code — unfalsifiable. **This is
Phase D for retrieval.** It turns `score_threshold=0.35` (moved from 0.7 by feel on 2026-07-21),
`top_k=5` and `chunk_size` from guesses into measurements — and combined with §3.4's persisted
JSON, re-chunking to test a hypothesis costs nothing.

**⚠️ Freeze the generated set.** Regenerating makes runs non-comparable. Commit as a fixture.
**⚠️ Absolute numbers will not match BEIR** — the set is biased by the generating model. The
*relative ordering on your data* is the signal.
**⚠️ Own CI step.** Buried in 773 tests, "1 failed" reads as flake.

### 5.2 The reranker — stage 4

BotForge has stages 1–3 (FTS + dense + RRF k=60). Missing: the cross-encoder. A bi-encoder embeds
query and document **separately**; a cross-encoder feeds both into one model with joint attention.
Much more accurate, much slower — so run it only on the top ~50 fused candidates.

Public BEIR baselines, FiQA-2018, NDCG@10 (`6-evaluate.py` docstring):

| Stage | NDCG@10 |
|---|---|
| BM25 only | ~24 |
| `text-embedding-3-small` only | ~31 |
| **+ cross-encoder rerank** | **~40+** |

**⚠️ Two constraints the cookbook does not have:**

1. **Latency.** NFR-1 is p50 417 ms first token. A hosted rerank call adds a round trip *before*
   generation starts, per turn.
2. **Whose key pays.** ADR-055 established guard models resolve on the **platform** key, never the
   org's, because the fallback chain would silently resolve the wrong credential. **A reranker is
   the same class of decision.** Do not let it fall through `resolve_credential()`.

### 5.3 Recommended: self-hosted `bge-reranker-v2-m3`

| Criteria | Cohere API | bge-reranker-v2-m3 |
|---|---|---|
| Latency | Network RTT every turn | Local inference |
| Cost | Per call, per org, forever | Fixed compute |
| Data egress | Client KB → third party | **None** |
| Multilingual | Good | **Strong — trained multilingual** |
| Ops | None | A model to host (~568 MB) |

**Multilingual is decisive.** `docs/11 §9.2a` records Tamil as a first language in this market.
It also partly compensates for §5.4.

**docling-serve already exists by this phase**, so a second small inference service is a much
smaller marginal step than it would have been. That is an argument for sequencing K1 before K4.

### 5.4 Non-English retrieval is half-off today

`to_tsvector('english', ...)` is hardcoded. For Tamil or Hindi, English stemming is meaningless
and **the keyword half of hybrid retrieval contributes nothing**. The retrieval-side twin of the
known "L1 is English-first" guardrail gap.

**Be honest about the fix:** Postgres ships no Tamil or Hindi dictionary. `'simple'` (tokenize, no
stemming) is the realistic option and is still far better than English stemming on Tamil.

**⚠️ Changing the regconfig requires a matching index** — one GIN index per config in use, or a
generated `tsvector` column. Do not change the literal and leave `0004`'s index behind.

---

## 6. Data model

**No migration is required for the core Docling work.** `chunks.metadata` is already `jsonb` and
already declared as `{page, heading, ...}` in docs/03.

Required additions at the agreed scope:

| Change | Why | Verdict |
|---|---|---|
| `documents.extraction_backend` (`docling`\|`legacy`) | Makes a re-ingest campaign targetable and a regression attributable | **Required** |
| `documents.docling_json_path` (nullable text) | §3.4 persisted document | **Required** |
| `documents.media_duration_seconds` (nullable int) | Per-org ASR quota (§3.7) | **Required with K3** |
| `organizations.media_minutes_quota` | §3.7 | **Required with K3** |
| `knowledge_bases.fts_config` (default `'english'`) | §5.4 | With K5 |
| `knowledge_bases.embedding_dim` | `EMBEDDING_DIM=768` is a module constant, so all KBs share one dim — blocks 1536-dim models per KB | **Out of scope — own ADR** |

**⚠️ Where the DoclingDocument JSON lives is a real decision, not a detail.**

| Option | Verdict |
|---|---|
| Postgres `jsonb` column | ❌ Blobs are large (per-element geometry, provenance, table cells). Bloats the table every tenant query touches, and pushes backup size up fast |
| Object storage / disk, path in DB | ✅ **Recommended.** Same shape as `documents.storage_path`, which already exists |

**Measure real blob sizes against actual client PDFs before committing.** If a 200-page document
produces a 50 MB JSON, retention needs a policy too.

Chunk metadata contract:

```jsonc
{
  "filename": "refund-policy.pdf",
  "source_url": null,
  "heading": ["Returns Policy", "International Orders"],  // NEW — DocMeta.headings
  "caption": null,                                        // NEW — DocMeta.captions
  "page": 4,                                              // NEW — doc_items provenance
  "backend": "docling"                                    // NEW — provenance
}
```

**⚠️ Every consumer must tolerate the old shape.** Existing chunks have `{filename, source_url}`
until re-ingested. Read defensively; never assume `heading` exists.

---

## 7. Implementation plan

### Phase K0 — Measure first (no new dependencies)

| # | Task | Done when |
|---|---|---|
| **P0-1** | `EXPLAIN ANALYZE` the FTS query on real data (§0). If seq-scanning, render the regconfig as a literal | `EXPLAIN` output in the PR body showing Bitmap Index Scan on `ix_chunks_content_fts` |
| **P0-2** | Eval harness: generator, frozen fixture, `ndcg_at_k`, `make eval-retrieval`, own CI step | Baseline NDCG@10 for dense / FTS / hybrid committed as the number to beat |

**⚠️ P0-2 gates everything after it.** Without a baseline, K1–K5 are unfalsifiable.

### Phase K1 — Docling core (documents)

| # | Task | Done when |
|---|---|---|
| K1-1 | `DocumentConverter` protocol + `LegacyConverter` wrapping `load_bytes` | Existing tests pass unchanged through the interface |
| K1-2 | `docling-serve` compose service (§3.9 deps, **no ASR yet**) + `DoclingServiceConverter`; env vars in `.env.example` + `docs/ENV.md` | Service healthy; converter returns markdown for a fixture PDF |
| K1-3 | Wire into `ingest_document` **behind `DOCLING_ENABLED`, default off**, fallback on any failure | A Docling outage degrades to today's behaviour, logged, never a failed document |
| K1-4 | `documents.extraction_backend` + `docling_json_path`; persist the JSON (§3.4, §6) | JSON round-trips via `load_from_json()` in a test |
| K1-5 | Golden-file tests: scanned PDF, table-heavy PDF, **the 2026-08-03 PII-incident PDF** | The PII fixture yields a phone `classify_contact()` detects, no `\x01` |

**K1-5 is the acceptance test for the phase** — it converts a past incident into a regression test,
the same move docs/11 made with the red-team corpus.

> **Status 2026-08-16 — K1-1 … K1-4 shipped; K1-5 is OPEN, so K1 is not done.** ADR-064.
> `app/rag/converters.py`, migration 0020, the `docling` compose service (`expose:` only, no
> published port), `DOCLING_*` settings off by default. Covered by `tests/test_converters.py`
> (13) and `tests/test_ingest_docling.py` (6) — both directions on the same input, including a
> simulated outage still reaching `status=ready` via `LegacyConverter`.
>
> **K1-5 is blocked on binaries, not on code.** It names three real files (a scanned PDF, a
> table-heavy PDF, the PII-incident PDF) and none are in the repo. §11 of this document is
> explicit that hand-typed fixtures cannot substitute — that is precisely how the 2026-08-03 PII
> detector shipped believing it worked, when real extracted text carried `\x01` for ☎ and tabs
> for spacing and libphonenumber matched nothing. Writing a synthetic "scanned PDF" here would
> reproduce that mistake with a green tick on top. **Docling stays disabled for every deployment
> until K1-5 has real files**, which is the honest reading of "K1-5 is the acceptance test".

### Phase K2 — HybridChunker + real tokens

| # | Task | Done when |
|---|---|---|
| K2-1 | Tokenizer wrapper (tiktoken). **Pin `huggingface_hub`** (§3.8 Trap 1). Replace `estimate_tokens` | `token_count` exact for a known fixture |
| K2-2 | `HybridChunker`; map `DocMeta` → metadata (§6) | Heading path on every chunk of a headed document |
| K2-3 | Embed `contextualize()`, persist raw `content` (§4.2) | Test asserts stored `content` has no heading prefix **and** embedding input does |
| K2-4 | **Re-chunk backfill from persisted JSON** (§3.4) — resumable, per-org, no re-conversion | Backfill re-runs safely after interruption |
| K2-5 | **Re-run P0-2.** Record the NDCG delta in this file | A number, not a claim |

**⚠️ Do not ship K2 if K2-5 shows no improvement.** That is what P0-2 is for.

### Phase K3 — Format breadth + media

| # | Task | Done when |
|---|---|---|
| K3-1 | Enable document extras: email, EPUB, ODF, LaTeX, images, Box Notes (§3.5). Widen upload validation + UI file types | One golden fixture per newly accepted format |
| K3-2 | **Gate email ingest on the docs/11 §6 PII workflow** (§3.5) | Email uploads refused with a clear message until the workflow ships |
| K3-3 | Chart understanding: `do_chart_extraction=True`, **`chart2csv` only** (§3.6) | A chart fixture yields a CSV table; RAM delta on docling-serve measured and recorded |
| K3-4 | **Separate `q=media` Celery queue + worker** (§3.7) | A long media job provably does not delay a document job — tested, not assumed |
| K3-5 | ASR: `format-audio`, Whisper model chosen **on real client audio**, upload cap, media timeout | Model choice justified with a measured comparison, not a default |
| K3-6 | `media_duration_seconds` + per-org `media_minutes_quota`, enforced before conversion | Over-quota upload rejected with a typed error |

**⚠️ K3-4 before K3-5.** Shipping ASR onto the shared queue is the multi-tenant fairness bug
described in §3.7 — and it will look fine in dev with one tenant.

### Phase K4 — Reranker

| # | Task | Done when |
|---|---|---|
| K4-1 | `Reranker` protocol + `NoOpReranker` default | Retrieval byte-identical with the no-op |
| K4-2 | `BgeReranker` self-hosted (§5.3). `candidate_k=50`. Platform-resolved, **never** `resolve_credential()` | Own metrics bucket, not folded into `TurnResult` |
| K4-3 | Per-agent + platform toggle, **default off**; unavailable → no-op, logged loudly | A reranker that is off must not look like one finding nothing (the Phase C lesson) |
| K4-4 | **Re-run P0-2** + measure p50/p95 added latency | NDCG delta **and** latency delta, both recorded |
| K4-5 | **ADR:** platform infrastructure vs BYO-key org feature | Written before enabling for any client |

**⚠️ Fail open, and say so.** Every guard layer in docs/11 fails open; a reranker must too. A
rerank outage degrades to RRF ordering — never an error, never an empty result set.

### Phase K5 — Language and long tail

| # | Task |
|---|---|
| K5-1 | `knowledge_bases.fts_config`; per-config GIN index; `'simple'` for non-English (§5.4) |
| K5-2 | `document_timeout` tuning (Docling recommends 90–120 s), page-count caps |
| K5-3 | Retention policy for persisted DoclingDocument JSON (§6) |

---

## 8. Edge cases

| Case | Handling |
|---|---|
| docling-serve down | `LegacyConverter` fallback, log `docling_unavailable`, document still ingests |
| Docling returns empty text | Extraction failure → fallback → only then `LoaderError` |
| Huge PDF (500+ pages) | `document_timeout` 90–120 s; page cap; failure message names the limit |
| Encrypted / corrupt file | Typed error on the document row, never a worker crash |
| **2-hour video** | `q=media`; quota checked **before** conversion; own timeout |
| **ASR produces gibberish** | Low-confidence transcript is worse than none — it grounds the model in falsehoods. Needs a confidence floor and a `failed` status, not silent ingest |
| Chart with no readable data | Chart extraction returns nothing; document still ingests |
| Chunk exceeds embedding max input | `HybridChunker` splits on tokens — structurally impossible after K2 |
| Mixed old/new chunk metadata | Read defensively (§6) |
| Persisted JSON missing on re-chunk | Fall back to full re-conversion; log it |
| Reranker times out | No-op → RRF order. **Never** empty |
| Non-English query | Dense half works; FTS half inert until K5-1 |
| Zero candidates after RRF | Unchanged: no context, fallback message. **Still the fabrication path** — §9 |

---

## 9. Security

- **Tenant isolation unchanged.** Every query in `retrieval.py` filters on `organization_id`. The
  reranker operates on already-filtered candidates — **never** give it a broader pool "for better
  ranking".
- **docling-serve is internal.** Bind to the compose network. **Do not publish its port.** It
  accepts arbitrary documents and URLs — a public port is SSRF plus resource exhaustion, and with
  ASR enabled it is also a compute-exhaustion target.
- **SSRF rules still apply.** `loaders.py` validates IPs/hostnames for URL ingest. If Docling is
  ever handed a URL directly it **must** go through the same validation — a new code path must not
  bypass an existing control.
- **Email is the highest-PII-density format** (§3.5). Gate on the docs/11 §6 workflow.
- **Media files carry PII in a form your detector cannot see.** `scan_document_text()` runs on the
  *transcript* — a spoken credit-card number becomes text and is scannable, but the **source audio
  is not**, and it is now sitting in your storage. Retention and access control for uploaded media
  is a new question this phase creates.
- **Excluding XBRL/USPTO/JATS removes three XML parsers** — an XXE-surface reduction, not only a
  size one.
- **A self-hosted reranker keeps client KB content in-house.** A hosted one ships client document
  text to a third party — contractual and residency, not just technical.
- **Untrusted content stays untrusted.** Better extraction does not make a document trustworthy.
  `neutralize_injections()` must still wrap retrieved chunks. **A cleaner parser is not a
  guardrail** — a well-parsed PDF carries an indirect injection just as well as a mangled one.
  Chart-to-CSV and ASR transcripts are *new* untrusted-content channels and must go through the
  same wrapping.

---

## 10. Performance

| Stage | Where | Latency impact |
|---|---|---|
| Docling conversion | `q=documents` worker | **None on chat.** Ingest slows to seconds–tens of seconds |
| Chart extraction (VLM) | `q=documents` worker | None on chat. Significant per-figure cost + **RAM** |
| ASR | `q=media` worker | None on chat. Minutes per file |
| HybridChunker / `contextualize()` | worker | None |
| Re-chunk from JSON | worker | **Much faster than rev 1's plan** — no re-conversion |
| FTS literal fix (P0-1) | per query | **Improvement** if seq-scanning today |
| `candidate_k` 20 → 50 | per query | Small — both indexes support it |
| **Reranker** | **per turn, pre-generation** | **The only real cost. Measure in K4-4** |

**NFR-1 is p50 417 ms first token. K4 is the only phase that can breach it** — which is why it is
last, defaults off, and requires a measured latency delta before enablement.

---

## 11. Testing

- **Golden files, not hand-typed fixtures.** The 2026-08-03 lesson was explicit: *hand-written
  fixtures cannot tell you what real extracted text looks like*. Commit real files — scanned PDF,
  table-heavy PDF, chart PDF, `.eml` thread, short audio clip, and the PII-incident document.
- **Test the fallback, not just the happy path.** Simulate a docling-serve outage and assert the
  document still ingests via `LegacyConverter`. The 2026-08-04 lesson: when a feature has an allow
  path and a deny path, testing one proves nothing.
- **Assert both directions of `contextualize()`** — stored `content` clean, embedding input
  enriched. One assertion passes when the feature is broken.
- **Test queue isolation explicitly** (K3-4): enqueue a long media job, assert a document job
  completes without waiting. Do not assume it.
- **Never let tests call docling-serve, Whisper, or a rerank model for real.** `conftest.py` must
  disable all three, exactly as it does for L2/L3 guard models — otherwise every ingest test hits a
  live service on a machine where the URL is set.
- **The eval corpus is its own CI gate** (P0-2), separate from the 773-test suite.

---

## 12. Rollout

1. `docling-serve` up, `DOCLING_ENABLED=false`. Nothing changes. Confirm health and RAM headroom.
2. Enable for **one internal org**. Compare conversions side by side against legacy.
3. Enable for new documents platform-wide. Old chunks untouched — mixed state is expected (§6).
4. Backfill re-ingest per org, off-peak, resumable, tracked by `extraction_backend`.
5. K3 formats one at a time, each with a golden fixture. **Email last**, after the docs/11 §6 PII
   workflow. **ASR only after the media queue is proven isolated.**
6. K4 stays off until K4-4 produces both numbers and K4-5's ADR is written.

Rollback at every step is a flag flip, because `LegacyConverter` is never deleted.

---

## 13. Priority

| Rank | Task | Effort | Risk | Payoff |
|---|---|---|---|---|
| 1 | **P0-1** FTS literal (verify + fix) | S | Very low | Possibly large latency win |
| 2 | **P0-2** Eval harness | M | Low | **Makes everything else provable** |
| 3 | **K1** Docling core + persisted JSON | M | Low (fallback) | Quality **+ a safety fix** |
| 4 | **K2** HybridChunker + contextualize | M | Low *(was Med — §3.4 de-risks it)* | Largest retrieval-quality gain |
| 5 | **K3-1/2** Document formats + email gate | M | Low | **Email is the richest untapped KB** |
| 6 | **K5-1** Per-KB FTS config | S | Low | Non-English recall |
| 7 | **K3-3** Chart understanding | M | Med (RAM) | Charts stop being invisible |
| 8 | **K3-4/5/6** Media queue + ASR + quota | L | **Med (fairness, cost)** | New product capability |
| 9 | **K4** Reranker | L | **Med (latency)** | Large accuracy gain |

---

## 14. Future

- Docling MCP server — expose the KB to external agents. Product decision, not performance.
- `granite-docling` VLM pipeline for the hardest layouts — only once P0-2 shows the standard
  pipeline failing on them.
- Video keyframe extraction (without diarization, §3.5).
- LLM-as-judge answer-quality eval on top of the retrieval eval.
- Per-KB `embedding_dim` (§6), unblocking 1536-dim models.
- **Explicitly rejected:** LangChain / LlamaIndex / CrewAI / Haystack integrations. BotForge has
  its own runtime, guardrail layers and tool loop. A second orchestration stack means two places a
  safety bug can hide, and docs/11's layers would not apply to the second one.

---

## 15. Confidence

**High — gap analysis (§2.2, §2.3).** Read from source: `pypdf` at `loaders.py:151`, `len/4` at
`chunking.py:14`, metadata at `ingest.py:85`, `EMBEDDING_DIM` at `knowledge.py:18`, indexes in
`migrations/0004`.

**High — Docling capability, packaging, and the chart/ASR cost claims (§3).** Read from v2.119.0
source and `pyproject.toml`. `DocMeta` fields and JSON round-tripping verified by installing
`docling-core` and introspecting. Trap 1 reproduced, not inferred. `ChartExtractionModelKind =
granite-vision` read from `chart_extraction_options.py`. Whisper defaults from
`asr_model_specs.py`.

**High — K1 and P0-1 being safe.** K1 keeps the legacy path; P0-1 is a rendering fix behind an
`EXPLAIN`.

**Medium — §0's seq-scan conclusion.** The expression/parameter mismatch is certain; whether
Postgres works around it via custom-plan parameter folding is plan-dependent. Stated as "measure
it" because that is the honest reading. **Do not skip the `EXPLAIN`.**

**Medium — the *size* of retrieval gains.** The ~40+ NDCG figure is FiQA (financial forum posts),
not a support KB. The *direction* is well established; the magnitude on BotForge's corpora is
unknown until P0-2 exists. **That uncertainty is the argument for P0-2 first, not against K2/K4.**

**Medium-low — docling-serve RAM at full scope.** Layout + table + OCR + Granite Vision + Whisper
in one container is a lot. I have not measured it. **Size it empirically in K1-2 and K3-3 before
committing to a production instance type.**

**Low — ASR quality on real client audio.** Entirely dependent on audio conditions, accent, and
domain vocabulary. `WHISPER_TINY` is the library default and is almost certainly not the right
choice. K3-5 must measure, not assume.

**Assumptions that would change this plan**

- If ingest latency becomes user-visible (a client watching an upload spinner), chart extraction
  and ASR need progress reporting, not just a status field.
- If most client KBs are HTML/markdown, K1 drops in priority — trafilatura already covers HTML —
  but **K2 stays**, because `contextualize()` and real tokens help every format.
- If a client requires data residency, hosted rerank is off the table and K4 is self-hosted from
  day one.
- If p50 latency is a harder constraint than accuracy, K4 becomes permanently per-agent opt-in,
  like the Phase G web tool.
- If media storage or ASR compute cost exceeds its revenue value, K3-4/5/6 should be cut. It is
  the most expensive phase here and the only one that is a **new product capability** rather than
  a fix to an existing one.
