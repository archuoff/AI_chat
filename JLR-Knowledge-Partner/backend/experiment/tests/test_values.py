import json

from conftest import sheet
from experiment.excel_extractor.model import to_json


def cells(ex):
    return {c.a1: c for c in ex.data[sheet(ex).name].cells.values()}


def test_zero_and_false_are_kept_in_json(ex_cache):
    c = cells(ex_cache("values"))
    assert to_json(c["C2"])["v"] == 0
    assert to_json(c["C7"])["v"] is False


def test_percent_and_thousands_display(ex_cache):
    c = cells(ex_cache("values"))
    assert c["C4"].d == "12.5%"
    assert c["C5"].d == "1,200.00"
    assert c["C5"].v == 1200


def test_dates_are_iso_text(ex_cache):
    assert cells(ex_cache("values"))["C6"].v.startswith("2026-03-01")


def test_text_number_stays_text(ex_cache):
    c = cells(ex_cache("values"))["C8"]
    assert c.t == "s" and c.v == "0012"


def test_error_cell_kind(ex_cache):
    c = cells(ex_cache("values"))["C12"]
    assert c.t == "e" and "error:div0" in c.flags


def test_unicode_and_line_breaks_survive(ex_cache):
    c = cells(ex_cache("values"))
    assert c["C11"].v == "Dév Üser 日本 ✓"
    assert "\n" in c["C9"].v


def test_formula_result_kept(ex_cache):
    c = cells(ex_cache("values"))["C13"]
    assert c.v == 4.69 and c.f == "=C3*2"


def test_formula_without_saved_result_is_flagged(ex_cache):
    sh = sheet(ex_cache("nocache"))
    assert any("formula_no_cache" in c.flags for c in cells(ex_cache("nocache")).values())
    assert any("no saved result" in p for p in sh.inventory["problems"])


def test_json_has_no_nan(ex_cache):
    json.dumps(to_json(sheet(ex_cache("values"))), allow_nan=False)
