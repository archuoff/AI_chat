"""Screenshot of the HTML report for a fixture (not collected by pytest).

Run from backend/:  python -m experiment.tests.shot <workbook.xlsx> <out.png>
"""
import sys
import tempfile
from pathlib import Path

from playwright.sync_api import sync_playwright

from experiment.excel_extractor.extract import extract


def main(xlsx: str, png: str) -> None:
    out = Path(tempfile.mkdtemp())
    ex = extract(xlsx)
    try:
        ex.save(out)
    finally:
        ex.close()
    with sync_playwright() as p:
        b = p.chromium.launch(executable_path="/opt/pw-browsers/chromium-1194/chrome-linux/chrome", args=["--no-sandbox"])
        pg = b.new_page(viewport={"width": 1500, "height": 1100})
        pg.goto((out / "report.html").as_uri())
        pg.wait_for_load_state("load")
        pg.screenshot(path=png, full_page=True)
        b.close()
    print(png)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
