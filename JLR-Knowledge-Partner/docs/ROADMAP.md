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
2. **VLM descriptions with neighbour context**: box title, column header, row label, caption, same-row text; one call per picture.
3. **Sheet preview draws pictures at their cell** (backend preview JSON + `SheetGrid` / `SheetPreview`).
4. **Image fetching in retrieval**: picture chunks linked to the record chunks of the same sheet / row, both ways.
5. **PDF: replace `pypdf` with Docling** (layout + tables + OCR, models from a local folder); then reuse steps 2 and 4 for PDF pictures.

## Later
- Experimental pipeline: apply Analyst proposals and re-extract; fix FMEA typing; picture straddle judge; review inbox; run on real Radar / FMEA files; wire into `app/`.
- Retrieval Phase 1 (trace log, truncation notices, answer verification, weak-evidence retry, bigger eval set).
- Qdrant server migration tool, Angular migration + SSO backend (team answers needed), folders in domains, gold set for the 90% target.
