"""Bitmap canvas: one bit per sub-pixel, one fg colour per cell, a fill layer per cell.

No alpha, no antialiasing. Ports the model from DESIGN.md's "The canvas is a bitmap"
section, shaped so a real Canvas class can replace this with a move rather than a rewrite.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from glyphs import Glyphs

if TYPE_CHECKING:
    from collections.abc import Callable

RGB = tuple[int, int, int]


class Canvas:
    def __init__(self, width_cells: int, height_cells: int, glyphs: Glyphs) -> None:
        self.width_cells = width_cells
        self.height_cells = height_cells
        self.glyphs = glyphs
        self.sub_w = width_cells * glyphs.cols
        self.sub_h = height_cells * glyphs.rows
        self._bits = [[0] * self.sub_w for _ in range(self.sub_h)]
        self._fg: dict[tuple[int, int], RGB] = {}
        self._bg: dict[tuple[int, int], RGB] = {}
        self._value_sum: dict[tuple[int, int], float] = {}
        self._value_count: dict[tuple[int, int], int] = {}

    def _cell_of(self, x: int, y: int) -> tuple[int, int]:
        return x // self.glyphs.cols, y // self.glyphs.rows

    def set_bit(self, x: int, y: int, *, color: RGB | None = None, value: float | None = None) -> None:
        if not (0 <= x < self.sub_w and 0 <= y < self.sub_h):
            return
        self._bits[y][x] = 1
        cell = self._cell_of(x, y)
        if color is not None:
            self._fg[cell] = color
        if value is not None:
            self._value_sum[cell] = self._value_sum.get(cell, 0.0) + value
            self._value_count[cell] = self._value_count.get(cell, 0) + 1

    def line(self, x0: int, y0: int, x1: int, y1: int, *, color: RGB | None = None, value: float | None = None) -> None:
        dx, dy = abs(x1 - x0), -abs(y1 - y0)
        sx = 1 if x0 < x1 else -1
        sy = 1 if y0 < y1 else -1
        err = dx + dy
        x, y = x0, y0
        while True:
            self.set_bit(x, y, color=color, value=value)
            if x == x1 and y == y1:
                break
            e2 = 2 * err
            if e2 >= dy:
                err += dy
                x += sx
            if e2 <= dx:
                err += dx
                y += sy

    def rect(self, x0: int, y0: int, x1: int, y1: int, *, fill: RGB | None = None, solid: RGB | None = None) -> None:
        """Fill paints only the background layer (invisible without colour); solid also lights every bit."""
        lo_x, hi_x = min(x0, x1), max(x0, x1)
        lo_y, hi_y = min(y0, y1), max(y0, y1)
        if solid is not None:
            for y in range(lo_y, hi_y + 1):
                for x in range(lo_x, hi_x + 1):
                    self.set_bit(x, y, color=solid)
        if fill is not None:
            for cy in range(lo_y // self.glyphs.rows, hi_y // self.glyphs.rows + 1):
                for cx in range(lo_x // self.glyphs.cols, hi_x // self.glyphs.cols + 1):
                    self._bg[cx, cy] = fill

    def fill_cell(self, cx: int, cy: int, color: RGB) -> None:
        self._bg[cx, cy] = color

    def resolve_value_colors(self, colormap: Callable[[float], RGB]) -> None:
        for cell, total in self._value_sum.items():
            mean = total / self._value_count[cell]
            self._fg[cell] = colormap(mean)

    def cell_bits(self, cx: int, cy: int) -> int:
        bits = 0
        for row in range(self.glyphs.rows):
            for col in range(self.glyphs.cols):
                sub_x, sub_y = cx * self.glyphs.cols + col, cy * self.glyphs.rows + row
                if self._bits[sub_y][sub_x]:
                    bits |= 1 << (row * self.glyphs.cols + col)
        return bits

    def cell_char(self, cx: int, cy: int) -> str:
        return self.glyphs.to_char(self.cell_bits(cx, cy))

    def cell_fg(self, cx: int, cy: int) -> RGB | None:
        return self._fg.get((cx, cy))

    def cell_bg(self, cx: int, cy: int) -> RGB | None:
        return self._bg.get((cx, cy))
