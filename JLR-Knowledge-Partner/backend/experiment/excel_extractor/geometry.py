"""Excel's own sizes in pixels, so pictures and shapes land where Excel puts them.

Column width as stored in the file (characters, padding included) -> pixels: round(width * 7) for the default font (max digit width 7 px);
a column without a stored width is 64 px; row height (points) -> pixels * 96 / 72;
drawing offsets are EMU (9,525 per pixel). Hidden rows / columns take no space.
"""
from __future__ import annotations

from bisect import bisect_right

from .model import Sheet

EMU_PX = 9525
MAX_COLS = 16384
MAX_ROWS = 1048576


def col_px(width_chars: float) -> int:
    return max(0, int(width_chars * 7 + 0.5)) if width_chars > 0 else 0


def row_px(height_pt: float) -> int:
    return max(0, round(height_pt * 96 / 72))


class Geometry:
    """Pixel position of every cell edge of one sheet, computed lazily and only as far as needed."""

    def __init__(self, sheet: Sheet):
        self.s = sheet
        self._hc, self._hr = set(sheet.hidden_cols), set(sheet.hidden_rows)
        self._cx: list[int] = [0]  # _cx[i] = left edge of column i+1
        self._ry: list[int] = [0]

    def _col_w(self, c: int) -> int:
        return 0 if c in self._hc else col_px(self.s.col_w.get(c, self.s.default_col_w))

    def _row_h(self, r: int) -> int:
        return 0 if r in self._hr else row_px(self.s.row_h.get(r, self.s.default_row_h))

    def _extend(self, edges: list[int], size, upto: int, limit: int) -> None:
        while len(edges) <= min(upto, limit):
            edges.append(edges[-1] + size(len(edges)))

    def left(self, c: int) -> int:
        self._extend(self._cx, self._col_w, c, MAX_COLS)
        return self._cx[min(c - 1, len(self._cx) - 1)]

    def top(self, r: int) -> int:
        self._extend(self._ry, self._row_h, r, MAX_ROWS)
        return self._ry[min(r - 1, len(self._ry) - 1)]

    def width(self, c0: int, c1: int) -> int:
        return self.left(c1 + 1) - self.left(c0)

    def height(self, r0: int, r1: int) -> int:
        return self.top(r1 + 1) - self.top(r0)

    def col_at(self, x: int) -> int:
        """1-based column that contains pixel x (grows the table as needed)."""
        while self._cx[-1] <= x and len(self._cx) < MAX_COLS:
            self._cx.append(self._cx[-1] + self._col_w(len(self._cx)))
            if len(self._cx) > 4000 and self._cx[-1] <= x:  # absurd position: stop at the last column we can reasonably model
                break
        return max(1, min(bisect_right(self._cx, x), len(self._cx)))

    def row_at(self, y: int) -> int:
        while self._ry[-1] <= y and len(self._ry) < MAX_ROWS:
            self._ry.append(self._ry[-1] + self._row_h(len(self._ry)))
            if len(self._ry) > 200000 and self._ry[-1] <= y:
                break
        return max(1, min(bisect_right(self._ry, y), len(self._ry)))
