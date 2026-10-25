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
1. **Excel Place-in-Cell pictures in `app/ingestion/excel.py`**: port the reader from the experiment; count pictures
   in coverage (no false "All data captured"); picture row is data, not a header; transposed table gives one card per column.
2. **VLM descriptions with neighbour context**: box title, column header, row label, caption, same-row text; one call per picture.
3. **Sheet preview draws pictures at their cell** (backend preview JSON + `SheetGrid` / `SheetPreview`).
4. **Image fetching in retrieval**: picture chunks linked to the record chunks of the same sheet / row, both ways.
5. **PDF: replace `pypdf` with Docling** (layout + tables + OCR, models from a local folder); then reuse steps 2 and 4 for PDF pictures.

## Later
- Experimental pipeline: apply Analyst proposals and re-extract; fix FMEA typing; picture straddle judge; review inbox; run on real Radar / FMEA files; wire into `app/`.
- Retrieval Phase 1 (trace log, truncation notices, answer verification, weak-evidence retry, bigger eval set).
- Qdrant server migration tool, Angular migration + SSO backend (team answers needed), folders in domains, gold set for the 90% target.
