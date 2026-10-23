# Plan: automatic, AI-assisted ingestion

Status: draft for discussion. Builds on the existing LangGraph ingestion pipeline (`backend/app/graphs/ingest_graph.py`).

## 1. Goal

Today a developer uploads a file, waits while it is processed inside the HTTP request, then fixes the domain,
confidentiality and Excel header rows by hand on the Manage page.

Target: a file appears (dropped in a watched folder, uploaded, later SharePoint), and the system on its own
- parses it and checks how well it was parsed, repairing what it can (e.g. Excel header rows),
- works out what it is: domain, document type, title, summary, key entities, confidentiality,
- spots duplicates and new versions of documents it already has,
- publishes it to chat when it is confident, or puts it in a review **Inbox** with its reasons when it is not,
- describes its pictures within a cost budget.

Every AI decision is recorded with its confidence and reason, and a person can override it.

## 2. What exists and what is missing

| Area | Today | Gap |
|---|---|---|
| Trigger | Upload / `ingest-folder` call, runs synchronously in the request (`main.py` `upload_documents`) | No background jobs, no queue, no retries; a 97 MB workbook blocks the request |
| Sources | Upload, one-off server folder | No watched folder, no SharePoint / OneDrive, no deletion sync |
| Identity | `doc_id = uuid5(file name)` (`store.py` `doc_id_for`) | Renamed file = new document; same name from two folders collides; no version history; exact duplicates under another name are indexed twice |
| Domain | `unassigned` unless given; LLM suggestion only on request, after indexing (`classify.py`) | Not automatic, runs too late |
| Confidentiality | Manual flag | No detection; a confidential file is visible to every user until someone flags it |
| Excel structure | Good heuristics + per-table overrides (`parse_options`), coverage % recorded (`excel.py`) | Overrides are manual even though coverage already tells us when a table went wrong |
| PDF | `pypdf` text only; scanned pages produce a warning | No OCR |
| Metadata | Free-form manual `meta` JSON | No document type, title, summary, vehicle/part/material tags |
| Pictures | Extracted automatically; describing is a manual button | No automatic describing with a budget |
| Quality | `app.eval` run by hand; no unit tests | No parser regression tests, no ingestion quality metrics |

The pipeline is already a LangGraph graph whose docstring plans for new nodes between `chunk` and `index`, and
the Excel overrides already have a clean schema, so most of this is adding nodes and a job layer, not a rewrite.

## 3. Architecture

```
 Sources                        Job layer                         Pipeline (LangGraph, per file)
 ───────                        ─────────                         ──────────────────────────────
 Watched folder ─┐                                                fingerprint ─► dedupe ─► parse
 Upload (UI/API) ┼─► ingest_jobs table ─► worker pool ─►            ─► assess ─(weak)─► repair ─► parse (≤2 tries)
 SharePoint (P4) ┘   (SQLite/Postgres)    (in API process)           ─► profile ─► chunk ─► [enrich] ─► gate
                         ▲                                           ─► index (published | review) ─► images ─► END
                         └── Inbox UI: approve / edit / reject ◄──── needs_review
```

### 3.1 Sources (connectors)

One small interface, so new sources do not touch the pipeline:

```python
class Source(Protocol):
    id: str                                    # "folder:C:/KG/inbox", "sharepoint:<site>/<library>"
    def changes(self, since: Cursor) -> list[Change]   # added / modified / deleted, with source_uri, mtime, size
    def fetch(self, change: Change) -> Path             # local copy to ingest
```

- **Watched folder** (phase 1): polling scanner (every N s) rather than OS file events, because network shares
  and Windows file locks make events unreliable. A file is picked up only after its size and mtime are stable for
  two scans (avoids half-copied files). Sub-folder names can map to a domain (`inbox/adas/...` → `adas`), which is a
  strong, free signal the profiler uses.
- **Upload**: the existing endpoint stores the file and enqueues a job instead of processing inline.
- **SharePoint / OneDrive** (phase 4): Microsoft Graph delta queries with an app registration on the company tenant.
- **Deletions**: a file removed from a source marks the document `source_missing`; removal from the knowledge base
  is a policy setting (auto or via Inbox).

### 3.2 Job layer

- New table `ingest_jobs` in the existing accounts database (`auth/db.py` engine):
  `id, source, source_uri, file_name, content_hash, state, attempts, error, decisions (JSON), usage (JSON),
  doc_id, created_at, started_at, finished_at, created_by`.
- States: `queued → running → published | needs_review | skipped | failed`; `needs_review → published | rejected`.
- Worker pool (2 threads by default) started in the FastAPI lifespan. It must live in the API process while Qdrant
  runs embedded (single process). Moving to a Qdrant server (`QDRANT_URL`) later allows a separate worker process.
- Retries with backoff for transient LLM / embedding errors; parse errors fail immediately.
- API: `GET /api/ingest/jobs`, `GET /api/ingest/jobs/{id}`, `POST /api/ingest/jobs/{id}/retry`,
  `POST /api/ingest/jobs/{id}/approve` (with optional edits), `POST /api/ingest/jobs/{id}/reject`,
  `GET/PUT /api/ingest/sources`. Upload returns job ids immediately.

### 3.3 Document identity and versions

- Keep `doc_id` stable per logical document, but key it on `source_id + source path` instead of the bare file name
  (migration: existing ids stay valid for the current documents).
- Exact duplicate (same `content_hash` already indexed under another name/path): skip, link the job to the existing
  document.
- Possible new version: same title/near-identical profile summary embedding (cosine ≥ 0.95) but different content →
  Inbox: "looks like a new version of *X* — replace / keep both".
- Keep the previous version's registry entry (`versions` list) so a bad automatic update can be rolled back.

## 4. The AI steps

All LLM calls use the existing `get_chat_model(fast=True)` with structured output (as `classify.py` does), record
tokens through `add_usage`, and have a deterministic fallback so ingestion still works offline.

### 4.1 `assess` — parse quality (mostly deterministic)

Cheap metrics first, LLM only for borderline cases:
- Excel: coverage % per table (already computed), tables with 0 header rows, columns named `Column X`, records
  whose title is a number.
- PDF: share of pages with no text, garbled-text ratio (non-word characters), average characters per page.
- All: number of chunks, very short / duplicate chunks.

Output: `quality: {score, issues[]}`. Low score on PDF pages → OCR route (4.3). Low Excel table score → `repair`.

### 4.2 `repair` — Excel structure agent

For each weak table only, send the LLM a compact sketch of the block (first ~25 rows, cell addresses, merged ranges,
value types) and ask for corrections in **the existing `parse_options` schema**:

```json
{"tables": {"CCB!A3:R40": {"header_rows": 2}}, "sheets": {"Lookup": {"skip": true}}, "reason": "..."}
```

Re-parse with the proposed options and keep them only if coverage and the table checks improve (max 2 rounds).
They are stored as `parse_options` with `source: "ai"`, so the Sheet preview shows them and a person can change them
exactly like manual corrections today.

### 4.3 OCR for scanned PDFs / image-only slides (optional)

Pages flagged by `assess` are sent to OCR: Azure AI Document Intelligence (`prebuilt-layout`, also gives tables) on
the **company** Azure resource, or the configured vision deployment as fallback. Off unless configured, same rule as
picture describing today.

### 4.4 `profile` — understand the document (before indexing)

One structured call per document on a sample (file name and folder, first pages / slide titles / sheet names with
their headers, first rows):

```python
class DocumentProfile(BaseModel):
    domain: DomainId; domain_confidence: float; domain_reason: str
    doc_type: Literal["design_guideline", "fmea", "benchmarking_data", "lessons_learned", "specification",
                      "test_report", "process", "presentation", "other"]
    title: str
    summary: str                    # 2-4 sentences; indexed as a document-level chunk
    entities: dict[str, list[str]]  # vehicles / programmes, parts, materials, suppliers, standards
    confidentiality: Literal["none", "marked", "suspected"]; confidentiality_reason: str
    language: str
```

- Reuses and replaces the on-demand `suggest_domain`: the domain is set **before** `index`, so chunks are labelled
  correctly from the start. Keyword scoring (`_keyword_suggestion`) and the folder→domain mapping are combined with
  the LLM answer; agreement raises confidence.
- `doc_type`, `title` and `entities` go into the document registry and each chunk payload (filterable in Qdrant;
  the planner can later filter by `doc_type`).
- The summary becomes one extra chunk (`kind: "summary"`) so "which document covers frunk design?" finds the
  document directly.
- Confidentiality: rule-based markings first (`Confidential`, `Strictly confidential`, `Proprietary`, `Internal
  only` in headers/footers/first page, source folder rules), the LLM signal second. **Any signal → document is
  indexed as confidential and goes to review.** Failing safe matters more than saving a click.

### 4.5 `enrich` — contextual chunks (phase 3, only if the eval says it helps)

Prepend a one-line LLM-written context to text chunks (what the section is about, using the document summary), the
"contextual retrieval" approach. Costs tokens per chunk, so it is batched per section, cached by chunk hash, and
switched on only if `app.eval` shows better retrieval on our questions. Records already carry strong context
(sheet › table › row key) and are left as they are.

### 4.6 `gate` — publish or review

Configurable policy, evaluated on the decisions above:

| Auto-publish when all hold | Otherwise → `needs_review` with reasons |
|---|---|
| domain confidence ≥ 0.8 (or folder mapping agrees with the LLM) | low or conflicting domain |
| quality score ≥ threshold (e.g. Excel coverage ≥ 95 %) | weak parse after repair |
| confidentiality = none | marked / suspected confidential |
| no duplicate / version suspicion | possible new version |

Review documents are indexed straight away, but with payload `review: true`, and `access_filters`
(`auth/deps.py`) adds `"!review": True` for chat. Approving is then a payload update (like
`set_document_domain`), with no re-embedding. Developers can try a document in chat before approving (filter off for
them in a "preview" mode).

### 4.7 `images` — automatic describing

After publish, queue the document's waiting pictures for the existing describe job when a vision deployment is
configured, within `VISION_DAILY_TOKEN_BUDGET` / per-document caps. Over budget → stays waiting, visible in the Inbox.

## 5. Inbox (Manage knowledge → new tab)

- Job list with state, source, time, tokens used; filters (needs review / failed / today).
- Per job: the AI decisions and reasons (domain, type, title, confidentiality, repairs applied, duplicate match,
  quality issues), each editable; buttons **Approve**, **Approve with changes**, **Reject** (removes the indexed
  data), **Retry**.
- Links to the existing Overview / Sheet preview / Records / Chunks / Pictures tabs for the document.
- Bulk approve for high-confidence batches.
- Every decision and override is written to `decisions` on the job (model, prompt version, confidence, user who
  changed it): an audit trail and, later, labelled data for tuning thresholds.

## 6. Quality and testing

- `pytest` suite (none exists today): parser tests on small fixture files (cut-down copies of the `DATA/` files),
  pipeline test with the LLM mocked, gate policy tests, job state machine tests.
- `eval/ingestion.json`: expected domain, doc_type and confidentiality for every file in `DATA/`; a CLI command reports
  classification accuracy so prompt or threshold changes can be judged.
- Keep `app.eval` (answer quality) as the gate for `enrich` and for any chunking change.
- Metrics on the Library dashboard: auto-publish rate, review rate, override rate per decision type, tokens per
  document.

## 7. Configuration (new `.env` keys)

```
INGEST_WORKERS=2
INGEST_WATCH_FOLDERS=C:/KG/inbox             # ; separated; sub-folder name = domain id when it matches
INGEST_SCAN_SECONDS=30
INGEST_AUTO_PUBLISH=true                     # false = everything goes through the Inbox
INGEST_MIN_DOMAIN_CONFIDENCE=0.8
INGEST_MIN_EXCEL_COVERAGE=95
INGEST_DELETE_MISSING=review                 # review | auto | ignore
INGEST_ENRICH_CHUNKS=false
AZURE_DOCINTEL_ENDPOINT= / AZURE_DOCINTEL_API_KEY=   # OCR, company resource; empty = off
VISION_DAILY_TOKEN_BUDGET=0                  # 0 = no automatic describing
```

## 8. Phases

| Phase | Deliverable | Main files |
|---|---|---|
| **0 Foundation** | `ingest_jobs` table, worker pool, async upload, job API, job list in UI, pytest scaffolding + parser fixtures | `graphs/ingest_graph.py`, new `ingestion/jobs.py`, `main.py`, `auth/db.py`, `frontend/src/manage/UploadPanel.tsx` |
| **1 Auto-classify + gate** | Watched-folder source, `profile` node (domain, type, title, summary, entities, confidentiality) before `index`, `review` payload flag + chat filter, Inbox tab, `eval/ingestion.json` | new `ingestion/sources.py`, new `ingestion/profile.py` (absorbs `classify.py`), `store.py`, `auth/deps.py`, new `frontend/src/manage/InboxTab.tsx` |
| **2 Self-repair** | `assess` + Excel `repair` agent, OCR route for scanned pages | `ingestion/excel.py`, new `ingestion/assess.py`, new `ingestion/repair.py`, `ingestion/documents.py` |
| **3 Smarter library** | Duplicate / version detection, version history + rollback, automatic picture describing with budget, optional chunk enrichment (eval-gated) | `store.py`, `images/describe.py`, new `ingestion/enrich.py` |
| **4 Enterprise sources** | SharePoint / OneDrive connector (Graph delta), deletion sync | `ingestion/sources.py` |

Each phase ships on its own; phase 1 already removes most of the manual work (domain + confidentiality).

## 9. Risks

- **Confidential leakage** through wrong auto-publish → fail-safe gate (any signal = confidential + review), rules
  before LLM.
- **Wrong domain silently published** → confidence threshold, folder mapping, override-rate metric; re-labelling is
  cheap (payload update).
- **Token cost on large workbooks** → profile uses a fixed-size sample; repair sends only weak tables; enrich and
  image describing are budgeted and off by default.
- **Embedded Qdrant is single-process** → workers in the API process until a Qdrant server is used.
- **AI repairs making a table worse** → accepted only when measured coverage/quality improves; always visible and
  reversible in the Sheet preview.

## 10. Open questions

1. Which sources first: a shared network folder, SharePoint, or upload only?
2. Auto-publish allowed at all, or must every document be approved by a person at first?
3. Is Azure AI Document Intelligence available on the company resource for OCR?
4. Token budget per month for ingestion (profiling, repairs, pictures)?
5. When a file disappears from the source, should it leave the knowledge base automatically?
6. Can we run a Qdrant server (Docker / Qdrant Cloud) now, or stay embedded for the time being?
7. Is the domain list fixed, or should the AI propose new domains when many documents fit none?
