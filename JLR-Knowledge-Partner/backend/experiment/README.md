# Excel extractor (experiment)

Reads an Excel workbook and turns it into an exact **sheet model** plus **region candidates** (tables, side-ways tables, key-value
cards, picture strips, requirement lists, framed boxes). It makes no LLM calls and changes nothing in `app/`. The later LLM step only
confirms or corrects the regions this folder proposes.

## Run (from `backend/`)

```
python -m experiment.excel_extractor extract  FILE.xlsx --out OUTDIR   # full output
python -m experiment.excel_extractor inspect  FILE.xlsx [--json]       # counts only, no cell text: safe for confidential files
python -m experiment.excel_extractor compare  FILE.xlsx                # old reader (app.ingestion.excel) vs this extractor
python -m pytest experiment/tests -q                                   # tests (XlsxWriter fixtures)
python -m experiment.tests.shot FILE.xlsx shot.png                     # screenshot of report.html (Playwright, Chromium)
```

`extract` options: `--formulas / --no-formulas` (formula text; large files are read without by default), `--layout-chars N`.
Errors print one readable line; add `--debug` on `compare` for a traceback.

## Output (OUTDIR)
| file | content |
|---|---|
| `model.json` | workbook: sheets, merges, styles (de-duplicated), pictures (kind, anchor, media, alt, neighbours, flags), shapes, comments, links, tables, validations, regions (kind, range, headers, data/section rows, confidence, evidence, `needs_llm`), inventory |
| `cells/NN_<sheet>.jsonl` | one line per cell with a value, formula, picture or error (sparse, safe for large sheets) |
| `layout.json` | compact summary for the later LLM step: regions, headers, a few sample rows, pictures with neighbours, bounded size |
| `media/` | picture files, named by content hash |
| `report.html` | the sheet drawn with Excel sizes, pictures at their anchors, region outlines with kind and confidence |

## Edge cases and the test that covers each
| case | test |
|---|---|
| Place-in-Cell pictures (`vm` cells, rich values), alt text, error cell not a value | `test_radar`, `test_in_cell_cells_are_pictures_not_errors` |
| Floating pictures, one- and two-cell anchors, group child transform, text boxes, charts, comments, links, validations, Excel tables | `test_objects` |
| Merged cells: master value, vertical label not a header, merged block outside a table | `test_merges` |
| Transposed table with a picture row, side-ways attribute rows | `test_radar` |
| Framed box with child blocks | `test_framed_overview_is_a_frame_with_children` |
| Stacked tables split at title bars; multi-level headers joined `A > B` | `test_regions_more` |
| Section rows inside a table | `test_section_rows_do_not_split_the_table` |
| Side-by-side tables split at a blank column | `test_side_by_side_tables_are_separate` |
| Spacer column inside a titled table stays one table; untitled spacer = two tables (by design) | `test_spacer_column_inside_a_titled_table_stays_one_table`, `test_untitled_spacer_is_two_tables_by_design` |
| Key-value cards; two-data-row table; borderless fill-only table | `test_regions_more`, `test_radar` |
| Picture covering two boxes: flagged `straddles:` and both boxes need review | `test_picture_covering_two_boxes_is_flagged_and_reviewed` |
| Picture alone in a free area becomes its own box | `test_straddling_picture_alone_is_its_own_box` |
| Values: 0 and False kept, percent / thousands display, dates, text numbers, unicode, line breaks | `test_values` |
| Formulas without a saved result are flagged | `test_formula_without_saved_result_is_flagged` |
| Hidden rows / columns / sheets, freeze panes, autofilter | `test_objects`, `test_hidden_and_very_hidden_sheets_are_marked` |
| Inventory: complete vs needs attention (unreadable objects) | `test_inventory_layout` |
| Layout size bound and sample caps | `test_inventory_layout` |
| 20,000-row sheet in time; empty and merged-only sheets | `test_scale` |
| CLI: inspect prints no cell text, extract writes all outputs, compare runs, readable errors | `test_cli` |

## Known limitations
- Region kinds are rule-based guesses with a confidence. Anything below 0.7, or close between two kinds, is marked `needs_llm`. Nothing is decided silently.
- A table with an empty spacer column is one table only when a merged area runs across the gap; otherwise it is two tables (deliberate).
- Pictures that straddle two boxes are flagged, not assigned.
- SmartArt, ink and form controls are counted and flagged as unreadable; their text is not extracted.
- Vector pictures (EMF, WMF, SVG) are kept as files but not rendered.
- The rules are tested on fixtures built by XlsxWriter, not yet on your real workbooks. Use `inspect` on the real file first.

## How the LLM step uses this
It reads `layout.json`, which is small and bounded. It returns patch instructions only (region kind, header rows, section rows, keep or hide, picture box). Code applies them, rebuilds the output from `model.json`, and checks coverage and values again. It never returns or rewrites cell values.
