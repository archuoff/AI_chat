# NEWEST (2): edit and send a question

Hover a question in Chat: a pencil appears. Edit the text, press Enter or Send: the answers that followed that question disappear (also from the server's conversation memory) and the edited question is answered.

| File | State |
|---|---|
| `backend/app/graphs/chat_graph.py` | modified (`rewind_session`) |
| `backend/app/main.py` | modified (`POST /api/chat/{session}/rewind`) |
| `backend/tests/test_parallel_search.py` | modified (2 tests) |
| `frontend/src/lib/api.ts`, `frontend/src/chat/MessageView.tsx`, `frontend/src/chat/ChatView.tsx` | modified |

Images attached to the old question are not kept (only thumbnails exist); the editor says so.

---

# parallel search (LangGraph fan-out) + places for every part of a question

Copy these files (paths relative to `JLR-Knowledge-Partner/backend/`), no database change, no re-ingest needed:

| File | State |
|---|---|
| `app/rag/searchjob.py` | new (in-memory list of the searches of one question) |
| `app/rag/retriever.py` | modified (`search_specs`, `run_search`, `merge_hits`, `prepare`, `assemble`, per-sub-question places) |
| `app/graphs/chat_graph.py` | modified (`prepare -> search x N -> merge`) |
| `app/store.py` | modified (reads do not wait for each other when a Qdrant server is used; query cache lock) |
| `app/config.py` | modified (4 new settings, all with defaults) |
| `tests/test_parallel_search.py` | new |
| `tests/test_document_diversity.py` | modified |

Optional `.env` settings: `PARALLEL_SEARCH=true`, `SEARCH_WORKERS=6`, `PER_SUB_EVIDENCE=true`, `EVIDENCE_MIN_PER_SUB=2`.
Run: `python -m pytest tests -q` (78 pass). In Chat the "Searching documents" step is unchanged; `timings` now also show `retrieve.search_wall` (real waiting time)
and `retrieve.search_busiest` (the slowest single search): wall close to busiest = the searches really ran side by side.

---

# FIRST: the PostgreSQL / Alembic commit (70f4f3d) is missing on the office PC

The list below assumes you already have it. If `backend/alembic.ini` is missing, you do not. Without these files the backend
cannot start (startup runs the Alembic migrations, also on SQLite) and the picture catalog table is not created.
Copy these 19 files too (paths relative to `JLR-Knowledge-Partner/`), or simply pull the whole branch (recommended):

| File | State |
|---|---|
| `backend/alembic.ini` | new |
| `backend/migrations/env.py` | new |
| `backend/migrations/script.py.mako` | new |
| `backend/migrations/versions/0001_baseline.py` | new |
| `backend/app/dbcopy.py` | new |
| `backend/tests/test_database.py` | new |
| `backend/app/auth/db.py` | modified (engine, `init_db` runs the migrations) |
| `backend/app/auth/usage.py` | modified |
| `backend/app/cli.py` | modified (`migrate-db` command) |
| `backend/app/graphs/chat_graph.py` | modified (chat memory on PostgreSQL or SQLite) |
| `backend/app/images/catalog.py` | modified (also changed later: take the latest) |
| `backend/app/main.py` | modified (also changed later: take the latest) |
| `backend/app/config.py` | modified (also changed later: take the latest) |
| `backend/tests/conftest.py` | modified |
| `backend/requirements.txt`, `backend/requirements.lock.txt` | modified (`alembic`, `psycopg`, `langgraph-checkpoint-postgres`) |
| `backend/.env.example`, `backend/README.md`, `README.md` | modified (setup steps) |

Then, in the backend environment: `pip install -r requirements.txt`, restart the backend. With no `DATABASE_URL` set it keeps using the
SQLite file `backend/data/app.db` (your accounts stay; the Alembic baseline is stamped on first start). PostgreSQL itself is optional:
see `backend/README.md` when you want it.

---

# Office PC update: files changed since the Analyst run (commit 64e385d) and what to run

Easiest: `git pull origin claude/jolly-ramanujan-ee3mg9` (everything below comes with it).
To copy by hand instead, take the files below. Paths are relative to the repository root. **Nothing was deleted.**
No database migration is needed (tables are unchanged). Qdrant payloads get new fields, so documents must be re-ingested.

## New files (A)
| File | What it is |
|---|---|
| `JLR-Knowledge-Partner/backend/app/ingestion/incell.py` | reads Excel Place-in-Cell pictures (rich values) |
| `JLR-Knowledge-Partner/backend/app/ingestion/cleaning.py` | deterministic noise removal (PDF / Word / PowerPoint) |
| `JLR-Knowledge-Partner/backend/app/ingestion/pdf_docling.py` | Docling PDF extraction, chunking-ready JSON, adapter to `ParsedDocument` |
| `JLR-Knowledge-Partner/docs/ROADMAP.md` | what is done / to do |
| `JLR-Knowledge-Partner/docs/OFFICE_UPDATE.md` | this file |
| `JLR-Knowledge-Partner/backend/tests/test_breadcrumb.py` | tests |
| `JLR-Knowledge-Partner/backend/tests/test_chunker_hierarchical.py` | tests |
| `JLR-Knowledge-Partner/backend/tests/test_cleaning.py` | tests |
| `JLR-Knowledge-Partner/backend/tests/test_describe.py` | tests |
| `JLR-Knowledge-Partner/backend/tests/test_document_diversity.py` | tests |
| `JLR-Knowledge-Partner/backend/tests/test_excel_headings.py` | tests |
| `JLR-Knowledge-Partner/backend/tests/test_pdf_docling.py` | tests |
| `JLR-Knowledge-Partner/backend/tests/test_picture_links.py` | tests |
| `JLR-Knowledge-Partner/backend/tests/test_sheet_preview_pictures.py` | tests |

## Modified files (M)
| File | What changed |
|---|---|
| `backend/app/config.py` | new settings (see below) |
| `backend/app/ingestion/__init__.py` | `parse_file` runs the cleaning step |
| `backend/app/ingestion/documents.py` | `parse_pdf` uses Docling first, pypdf as fallback |
| `backend/app/ingestion/excel.py` | in-cell pictures, picture context, header / title-bar / section-row handling |
| `backend/app/ingestion/preview.py` | the preview returns the sheet's pictures with their cells |
| `backend/app/ingestion/chunker.py` | hierarchical + semantic chunking, `breadcrumb`, `relations` |
| `backend/app/graphs/ingest_graph.py` | passes the embedder to the chunker |
| `backend/app/images/catalog.py` | shares a description between identical pictures; picture breadcrumbs; repeat limit |
| `backend/app/images/describe.py` | cheap Excel mode, new prompts, run cap |
| `backend/app/store.py` | stores `breadcrumb` / `relations`; `section_key` index |
| `backend/app/rag/retriever.py` | picture links, whole-section expansion, document diversity |
| `backend/app/rag/answer.py` | sources carry the breadcrumb |
| `backend/app/main.py` | the preview endpoint passes the document id |
| `backend/requirements.txt` | `docling`, `docling-core` lines |
| `backend/experiment/excel_analyst/analyst.py` | picture-in-target check (already pulled if you took 1b69538) |
| `backend/experiment/tests/test_analyst.py`, `backend/experiment/tests/test_cli.py` | tests |
| `frontend/src/lib/types.ts` | picture types |
| `frontend/src/manage/SheetGrid.tsx` | pictures drawn in cells |
| `frontend/src/manage/SheetPreview.tsx` | Pictures toggle + picture panel |

## New optional `.env` settings (all have defaults)
```
PDF_ENGINE=auto               # auto | docling | pypdf   (set docling once it works on your PDFs)
DOCLING_ARTIFACTS_PATH=<folder with your Hugging Face Docling models>
CHUNKING=hierarchical         # or recursive (the old behaviour)
SEMANTIC_SPLIT=true
CLEAN_NOISE=true
CLEAN_REPEAT_PAGES=4          # same picture / table row on 4+ pages or slides = noise
VISION_EXCEL_MODE=brief       # brief | full   (GPT-4o cost for pictures inside Excel)
VISION_MAX_IMAGES_PER_RUN=300
LINK_PICTURES=true
DIVERSIFY_DOCUMENTS=true
```

## Run order on the office PC
1. Pull (or copy), `pip install -r requirements.txt` if Docling is not installed, restart the backend and the frontend.
2. Tests, from `backend`: `python -m pytest tests -q`, then separately `python -m pytest experiment/tests -q`.
3. One real PDF: `python -m app.ingestion.pdf_docling file.pdf --json out.json`, send me the summary line and the time.
4. **Re-ingest your documents** (needed for breadcrumbs, cleaning, hierarchical chunks, Excel pictures).
5. Manage -> Radar workbook -> Sheet preview: pictures in their cells, coverage, 10 pictures in cells.
6. Describe a few pictures (Manage -> Pictures): compare the cost estimate with the real tokens.
7. Chat checks: the bonnet bond-flange question (does the Design Guideline docx appear?), and a picture + its row question.
8. `python -m app.eval` with `CHUNKING=recursive`, then re-ingest the PDFs and run it with `CHUNKING=hierarchical`. Send both scores.
