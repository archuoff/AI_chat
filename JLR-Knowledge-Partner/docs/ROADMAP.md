# Roadmap: done and to do

## Done
- Upload popup: New / Update choice + similar-document suggestions (signatures, superseded versions, restore).
- `DATA/` removed from the repo.
- SQLite to PostgreSQL: Alembic migrations, PostgresSaver chat memory, `migrate-db` copy tool.
- Experiment, step 1 (`backend/experiment/excel_extractor`, ~2,800 lines + tests): reads merged cells, nested
  grids, Place-in-Cell pictures, drawing anchors, text boxes, comments; finds regions; inventory; HTML report; CLI.
- Experiment, step 2 (`backend/experiment/excel_analyst`): Azure Analyst proposes a layout map (patch-only),
  code checks every reference; verified live on the ADAS Sensors sheet (table + 8 picture links).
- Plans written: agentic ingestion design, Angular migration, retrieval review (Phase 1), Qdrant server migration.

## To do next: bring pictures and Docling into the live pipeline (before the experimental pipeline)
1. **DONE (code + tests; run on the real Radar file on the office PC):** Excel Place-in-Cell pictures in `excel.py` (`incell.py`):
   pictures count in coverage, shown as `[picture: alt]`, a picture row is data not a header, each picture carries box title /
   column / row label / alt text for the VLM. Heading fixes: stacked tables split at bold title bars, nested section rows
   (level 1 / level 2), tall merged labels are not headers, multi-level headers with a plain column, header line breaks cleaned.
   Still open: one card per vehicle for comparison (transposed) tables.
   Also DONE: `cleaning.py`, deterministic noise removal for PDF / Word / PowerPoint (page numbers, repeated headers and footers,
   boilerplate, TOC dot leaders, logo / icon / divider / blank / duplicate pictures), reported in `stats["cleaning"]`.
2. **DONE (code + tests; real GPT-4o run on the office PC):** VLM descriptions with neighbour context. Excel pictures use a short low-detail answer (`VISION_EXCEL_MODE=brief`), identical pictures are described once and shared, run cap `VISION_MAX_IMAGES_PER_RUN`; the same picture on 4+ pages / slides is noise (`CLEAN_REPEAT_PAGES`), also repeated header / footer table rows.
3. **DONE (code + tests + browser check on a generated workbook):** Sheet preview draws pictures in their cells (thumbnails instead of `[picture]`, in-cell and floating, merged areas use the top-left cell), a Pictures toggle, and a detail panel with the large image, status, description and the text sent to the vision model.
4. **DONE (code + tests):** image fetching in retrieval: a selected Excel row brings its pictures and a selected picture brings its row (same for PowerPoint slides), `LINK_PICTURES` / `MAX_LINKED_CHUNKS`. PDF pages: later, with Docling captions.
5. **PDF: replace `pypdf` with Docling** (layout + tables + OCR, models from a local folder); then reuse steps 2 and 4 for PDF pictures.

6. **DONE (code + tests; re-ingest documents to get it):** `breadcrumb` (path to the chunk) and `relations` (group, prev / next, parent, row_key) on every chunk of every format, in the Qdrant payload, the evidence and the Docling JSON; the chunk's `context` line is now built from the breadcrumb.

7. **TO DO (next session):** Excel transposed tables: one card per vehicle (column) for comparison questions, rows kept as fallback.

## Later
- Experimental pipeline: apply Analyst proposals and re-extract; fix FMEA typing; picture straddle judge; review inbox; run on real Radar / FMEA files; wire into `app/`.
- Retrieval Phase 1 (trace log, truncation notices, answer verification, weak-evidence retry, bigger eval set).
- Qdrant server migration tool, Angular migration + SSO backend (team answers needed), folders in domains, gold set for the 90% target.
