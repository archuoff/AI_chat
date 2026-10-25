import time

from experiment.excel_extractor.extract import extract


def test_big_sheet_extracts_in_time(fx):
    t0 = time.time()
    ex = extract(fx["big"], with_formulas=False)
    took = time.time() - t0
    try:
        sh = ex.book.sheets[0]
        assert sh.max_row >= 20000
        assert sh.non_empty >= 20000 * 12 * 0.9
        assert took < 60, f"took {took:.1f}s"
    finally:
        ex.close()


def test_empty_and_merged_only_sheets(fx):
    for key in ("empty", "merged_only"):
        ex = extract(fx[key])
        try:
            assert ex.book.sheets[0].inventory["verdict"] == "complete"
        finally:
            ex.close()
