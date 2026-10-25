# Excel extractor experiment: pending work (hand-off plan)

Read this file first. It is written so that a smaller model can finish the job step by step without the earlier conversation.

## 0. Goal and rules
Build and prove `backend/experiment/excel_extractor/`: an Excel reader that turns any workbook into a rich, exact **sheet model** (JSON) plus
**region candidates** (tables, side-ways tables, key-value cards, picture strips, requirement lists, framed boxes), so that a later LLM step only has
to confirm or correct a map. No LLM calls in this folder.

Hard rules
1. Do **not** change anything under `backend/app/` or `frontend/`. This folder is isolated. (`compare` may import `app.ingestion.excel`, read only.)
2. Never alter a cell value. Values are read, never rewritten. `0` and `False` are real values (see `model.to_json`).
3. Every guess has evidence text and a confidence; uncertain regions set `needs_llm = True`.
4. Work in small steps. After each task: run the tests, then `git add -A JLR-Knowledge-Partner/backend/experiment && git commit && git push`
   (branch `claude/jolly-ramanujan-ee3mg9`). Commit message ends with the attribution lines from the session reminder.
5. Keep the code style of the existing files (type hints, short docstrings that say WHY, no dead code).

Environment (a fresh container has none of this)
```
python3 -m venv /tmp/kpvenv
/tmp/kpvenv/bin/pip install -r JLR-Knowledge-Partner/backend/requirements.txt xlsxwriter pytest playwright
cd JLR-Knowledge-Partner/backend
/tmp/kpvenv/bin/python -m pytest experiment/tests -q          # the new tests
/tmp/kpvenv/bin/python -m pytest tests -q                      # the app tests must stay green (22 pass on PostgreSQL, 18 + 4 skipped on SQLite)
```
Browser for report checks: Chromium at `/opt/pw-browsers/chromium-1194/chrome-linux/chrome` (use `--no-sandbox`).

## 1. What already exists (committed, commit 17f1457)
`backend/experiment/excel_extractor/`
| file | does |
|---|---|
| `model.py` | dataclasses: Style, Cell, Merge, Anchor, Picture, Shape, Comment, Link, Region, Sheet, Workbook; `to_json` (drops empty noise, keeps `v`, `eff`, `r`, `c`, `id`) |
| `geometry.py` | Excel sizes in pixels (column stored width x 7, 64 px default; row points x 96/72; EMU 9525 per px); `Geometry.left/top/col_at/row_at` |
| `grid.py` | openpyxl pass -> `SheetData` (cells, empty styled `frames`, `merge_at`), styles de-duplicated, display text, hidden rows/cols, tables, validations, hyperlinks, legacy comments, defined names. `read_workbook(path, with_formulas)` |
| `package.py` | zip + safe lxml: `Package.xml/rels/iterparse/part_groups` |
| `media.py` | `MediaRegistry`: pictures by sha256, sizes via Pillow, `export(out)` |
| `ooxml.py` | Place-in-Cell pictures (`vm` -> metadata.xml -> richData -> richValueRel -> media, alt text), `=IMAGE()` formulas, all drawing anchors (one / two / absolute), pictures, text boxes, groups (children mapped through the group transform), connectors, charts, SmartArt flag, OLE, form-control count, threaded comments |
| `regions.py` | `find_regions(SheetData)`: content mask -> blocks -> frames (bordered boxes split by dividers) -> title-bar splits -> leaf analysis (header rows with a vertical-merge guard, data / section rows, uniformity down columns vs along rows, kind + confidence + alternatives) -> attach pictures / shapes -> `Picture.neighbours` |
| `inventory.py` | per sheet counts + `problems` + verdict `complete` / `needs_attention` |
| `layout.py` | `build_layout(extraction, max_chars)`: compact summary for the future LLM Analyst, drops detail step by step to fit |
| `report.py` | `write_report`: HTML with Excel-sized grid, pictures at anchors, region outlines |
| `extract.py` | `extract(path, with_formulas=None) -> Extraction`; `Extraction.save(out_dir)` writes `model.json`, `cells/*.jsonl`, `layout.json`, `media/`, `report.html` |

Verified so far: only on one tiny file made by XlsxWriter (`embed_image`, `insert_image`, `insert_textbox`): in-cell picture + alt text, floating anchor
(`E2:E3`), text box (`G2:I7`) are found, all output files are written. Nothing else is proven.

How a real Place-in-Cell file looks (XlsxWriter `embed_image` writes the same structure as Excel):
`<c r="C5" t="e" vm="1"><v>#VALUE!</v></c>`; `xl/metadata.xml` (`valueMetadata/bk` number = vm, `rc t=1 v=N` -> `futureMetadata[XLRICHVALUE]/bk[N]/rvb@i`);
`xl/richData/rdrichvalue.xml` `rv[i]` values ordered like `rdrichvaluestructure.xml` keys (`_rvRel:LocalImageIdentifier`, `CalcOrigin`, `Text`=alt);
`xl/richData/richValueRel.xml` rel list + `_rels/richValueRel.xml.rels` -> `../media/imageN.png`.

## 2. Tasks (do in this order)

### T1. Fixtures: `experiment/excel_extractor/testkit.py`  (+ add `xlsxwriter` to `backend/requirements-dev.txt`)
Helpers: `png_bytes(w, h, color)` (valid PNG, stdlib `zlib` + `struct`), `write_png(dir, name, color)`.
Builders, each `def name(path: Path) -> Path` using XlsxWriter:
1. **`radar_like`**: sheet "Radar Sensor", `set_column` A=3, B=28, C:F=26. Formats: title bar (fill #7F7F7F, bold, white, border), dark header (fill #1F2D5A,
   bold, white, border), body (border, text wrap). Layout (1-based):
   - `B3:F3` merged title "Radar Market Study".
   - `B4:B5` merged dark header "Radar Sensor Specifications"; `C4:F4` dark headers "Mercedes-Benz GLC 300", "AUDI SQ6 e-tron", "Range Rover Evoque P300e", "BMW iX xDrive 50".
   - Row 5 height 80: `embed_image` in `C5..F5` (different colours, `description` = vehicle name).
   - Rows 6-10: B labels "Radar Sensor Manufacturer", "Object Detection Min. Range", "Object Detection Max. Range", "IP - Protection Class", "Operating Temp. Range";
     C:F values `BOSCH,BOSCH,BOSCH,VALEO` / `0.15 m` x4 / `5.5 m,5.5 m,5.5 m,5.0 m (Valeo typical)` / `IP6KX / IP9K` x3 + `IP6KX (typical Valeo)` / `-40°C to +95°C` x4. All bordered.
   - Framed overview rows 13-28: merged bordered blocks `B13:C28`, `D13:E28`, `F13:F28` (dividers only between C|D and E|F, border all around); text in `B13`
     "Level 2+ Positional Overview ..." and `D13` "Level 3 Positional Overview ..." (wrap, top); `insert_image` at `B15`, `D15`, `F15`.
   - "Front Radar" card: `B31:C31` merged title bar; `B32` dark "Radar Specifications", `C32` dark "AUDI SQ6 e-tron"; `B33` "Radar Specifications" + `embed_image` `C33`;
     `B34:C36` label / value rows "Width x Height x Depth (in mm)" / "146 x 111 x 50", "Unit weight" / "0.491 Kg", "Material" / "PBT-GF; Electronic component".
   - Picture strip: `B39` title bar "Bracket fixation"; `B40` dark "AUDI SQ6 e-tron"; `B41` caption, `B42` `embed_image`, `B43` caption, `B44` `embed_image`.
   - Requirement list: `B47:D47` merged title bar "Design Guidelines for the RADAR"; rows 48-53 (height 40): `B` text "SSA Requirement 00165101 The Mid Radar Front pitch shall be ..." (IDs 00165101, 00165103, 00165102, 00165105, 00165099, 00165100), `C48:C50` merged "DVA Requirement for Mid Radar", `C51:C53` merged "DVA Requirement for Corner Radar", `insert_image` at `D51`, `D52`, `D53`. All bordered.
   - Stray text `N5` "stray note".
2. `stacked_tables`: two bordered tables, no blank row between them, each starting with a merged dark title bar then a header row.
3. `multi_level_header`: merged parent headers over 2-3 columns + sub-header row + 5 data rows.
4. `section_rows`: a table with single-cell section rows between groups of data rows (must NOT be split into separate tables).
5. `side_by_side`: two tables on the same rows separated by blank columns; plus two tables stacked with a blank row.
6. `key_value`: two-column label / value cards (no header) and a card with pairs across four columns.
7. `merges_fill_down`: vertical merges in data columns (group labels) and a block merge holding a value.
8. `objects_all`: text box, chart, cell comment, hyperlink (cell + internal), data validation list, `add_table`, an image in a merged cell.
9. `visibility`: hidden rows, hidden columns, a hidden and a very-hidden sheet, grouped rows, autofilter, freeze panes.
10. `values_formats`: ints, floats, percent (`0.0%`), thousands, dates, booleans, text numbers, line breaks, long text, unicode, an error cell (`=1/0`), formulas.
11. `formula_no_cache(path)`: take a workbook with formulas and remove the `<v>` of formula cells by editing the zip.
12. `group_shape(path)`: workbook with one picture; rewrite `xl/drawings/drawing1.xml` so the `xdr:pic` sits inside an `xdr:grpSp` with `a:xfrm` (`off`, `ext`, `chOff`, `chExt` with a scale of 2).
13. `big_sheet(path, rows=20000)`: `constant_memory`, 12 columns of mixed text / numbers.
14. `empty_sheet`, `merged_only_sheet`.

### T2. Command line: `experiment/excel_extractor/__main__.py`  (run: `python -m experiment.excel_extractor <cmd> ...` from `backend/`)
- `extract FILE --out DIR [--formulas/--no-formulas] [--layout-chars N]` -> `Extraction.save`; prints one line per sheet: regions, pictures, verdict.
- `inspect FILE [--json]` -> **counts only, no cell content, no file names of media** (safe to run on confidential files and paste the output). Per sheet:
  cells with `vm`, rich values resolved / unresolved, `=IMAGE(` formulas, floating pictures, groups, text boxes, charts, OLE, SmartArt, form controls,
  comments (legacy / threaded), hyperlinks, merges, hidden rows / cols, tables, validations, regions by kind, inventory verdict. Workbook: `Package.part_groups()`.
- `compare FILE` -> run `app.ingestion.excel.parse_excel` (needs `PYTHONPATH=.`) and the new extractor; print per sheet: old tables / records / coverage %
  vs new regions / pictures / verdict, and the list of in-cell picture cells the old reader marks "ignored".
- Exit code 0; errors are printed in one readable line (no traceback unless `--debug`).

### T3. Tests: `experiment/tests/test_*.py`  (pytest, fixtures from `testkit`, `tmp_path`)
Write one test file per theme and assert exactly:
- `test_radar.py` on `radar_like`:
  region `B3:F10` kind `transposed_table`, `orientation == "columns"`, `header_rows == [4]`, `corner_label == "Radar Sensor Specifications"`, title "Radar Market Study",
  row 5 in `data_rows` (the picture row is NOT a header row), `headers` contain the four vehicle names; 4 in-cell pictures with alt texts, each `neighbours.column_header` = its vehicle and
  `row_label == "Radar Sensor Specifications"`; framed overview kind `frame` with 3 children; floating pictures assigned to the children; "Front Radar" `key_value`; strip `picture_strip`;
  requirement block `requirement_list` (6 ID rows); `N5` is `stray`; inventory `uncovered_cells == []`.
- `test_in_cell.py`: pictures resolved with media + alt, cell `t == "p"` with `pic:<id>` flag, no `error:value` flag left, merged cell picture covers the merge range; `=IMAGE()` cell kept as `linked`.
- `test_anchors.py`: one / two cell anchors, absolute anchor, hidden column shrinks the anchor, group child anchor equals the transformed position, text box text, chart type + series refs, SmartArt flagged.
- `test_merges.py`: `merge_at` for every cell of a merge, master flag, effective value of covered cells, vertical label merge does not extend header rows, multi-level headers joined `Parent > Child`.
- `test_regions_*.py`: stacked tables split on title bars; section rows do NOT split; side-by-side tables are separate; key-value cards; a normal table is `table` with orientation `rows`.
- `test_values.py`: `0` and `False` survive `to_json`; percent / thousands display; dates ISO; error cells `t == "e"` with `error:<kind>`; formulas with no cache flagged; unicode intact.
- `test_inventory.py`: complete workbook -> `verdict == "complete"`; a floating picture outside any region, a SmartArt, a missing media part, an `=IMAGE` link each produce a problem line.
- `test_layout.py`: layout JSON for `big_sheet` is <= `max_chars` per sheet, ends with the omission note when trimmed, never contains more than 4 sample rows per region.
- `test_scale.py`: `big_sheet(20000)` extracts in < 60 s and < 1.5 GB (use `tracemalloc` peak or just the time).
- `test_cli.py`: `inspect --json` output contains no cell text (search for a unique string written into the fixture); `extract` writes all files; `compare` runs.

### T4. Fix what the tests show (most of the effort)

**Status (done):** both known gaps are fixed and their tests are strict (no expected failures left).
1. Merged areas now read their border from the master cell (`Sheeter.border`). Before, covered cells had no style, so merged blocks looked borderless and no frame was found. Result: the framed overview is a `frame` with three children.
2. Blocks are split at every column that is blank for their rows (`find_blocks`). The old rule merged column groups that overlapped in rows, which joined side-by-side tables. Trade-off: a table with an empty spacer column inside it is now split in two. Accepted because "blank column = break" is the same rule used for rows; revisit if a real file shows it.
Open weak spots (not yet fixed, no test yet): tables with only two data rows, borderless fill-only tables, pictures straddling two regions.
Where to adjust (all in `regions.py` unless noted), with the current thresholds:
- Title bar split: `_bar` score >= 5 (width span >= 80 % +2, dark / mid fill +2, bold or size >= 13 +1, next row header-like +2, next row data-like -1).
- Frame: `_split_frame` needs outer border >= 80 % of the perimeter and dividers on >= 80 % of the box length; if vertical OR horizontal dividers cover >= 60 % of the boundaries it is a ruled list / grid table, not a frame.
- Header: first body row with >= 2 items, >= 70 % text and (>= 50 % bold / filled or clearly different from the rows below); vertical merge extends the header only if the cells beside it are header-like; horizontal merge parents add a sub-header row (max 4 rows).
- Kind scores: `table = 0.5 + 0.4*U_col - 0.35*max(0, U_row-U_col)`; `transposed_table = 0.35 + 0.7*max(0, U_row-U_col) + 0.12 if first column is labels`; `key_value` 0.78 (2 columns) / 0.8 (one value column under a header); `requirement_list` 0.82 when >= 3 rows have ID tokens (`ID_TOKEN`); `picture_strip` 0.75; `needs_llm` when confidence < 0.7 or the top two scores differ by < 0.15.
- If a fixture exposes a wrong decision, change the rule or threshold, add a comment saying why, and keep every earlier test green. Do not special-case a fixture.
Known weak spots to check first: a table whose data rows are all different shapes (low uniformity), tables with only 2 data rows, a title bar that is not merged, borderless tables with fills only, pictures straddling two regions, hidden rows inside a region, very wide sheets (> 40 columns), and sheets where fills cover almost every cell (`FRAME_LIMIT`).

### T5. Look at the report
Script (put in `experiment/tests/shot.py`, not collected by pytest): extract `radar_like`, open `report.html` with Playwright (Chromium, viewport 1500x1100, `--no-sandbox`),
screenshot to `/tmp/radar_report.png`, and view it. Verify visually: merged cells drawn as merged, picture row shows the four pictures in `C5:F5`, floating pictures sit inside the framed boxes,
region outlines match the expected ranges (labels like `R3 transposed_table 0.9`). Fix `report.py` if pictures or outlines are off by a row / column.

### T6. README: `experiment/README.md`
What it is, how to run each command, the output files, a short JSON schema description (model.json / cells jsonl / layout.json), the edge-case matrix with the test that covers each case, known limitations, and how the later LLM step will use `layout.json` (patch instructions, never rewritten values).

### T7. Wrap up
Run both test suites, commit and push, then update `JLR-Knowledge-Partner/backend/experiment/PENDING_WORK.md` (tick what is done, list what is left).

## 3. Definition of done
- `pytest experiment/tests` green, `pytest tests` still green, no change under `app/` or `frontend/`.
- `python -m experiment.excel_extractor inspect <file>` and `extract` work on every fixture.
- The Radar-like fixture gives the regions and neighbours listed in T3 and a report that looks right in the browser.
- README written; everything committed and pushed.

## 4. Not in scope (later steps, do not start)
LLM calls (map, validator, enrichment), cards / chunking from regions, VLM picture descriptions, wiring into `app/`, the Sheet preview UI, Angular.

## 5. When the owner has the real (confidential) file
Ask the owner to run on the office PC: `python -m experiment.excel_extractor inspect "<file>"` and paste the output. Compare with the assumptions in section 1
(rich values, `vm` cells, `richData` parts); fix `ooxml.py` if the real structure differs (for example other rich value types or `_webimage`).
