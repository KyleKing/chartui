"""Turns Canvas bits + colours into rich Segments or a printable string."""

from __future__ import annotations

from io import StringIO

from canvas import Canvas
from rich.color import Color
from rich.console import Console
from rich.segment import Segment
from rich.style import Style
from rich.text import Text

DEFAULT_FG = (220, 220, 220)


def canvas_to_segments(canvas: Canvas, default_fg: tuple[int, int, int] = DEFAULT_FG) -> list[list[Segment]]:
    rows = []
    for cy in range(canvas.height_cells):
        row = []
        for cx in range(canvas.width_cells):
            char = canvas.cell_char(cx, cy)
            fg = canvas.cell_fg(cx, cy) or default_fg
            bg = canvas.cell_bg(cx, cy)
            style = Style(color=Color.from_rgb(*fg), bgcolor=Color.from_rgb(*bg) if bg else None)
            row.append(Segment(char, style))
        rows.append(row)
    return rows


def segments_to_plain(rows: list[list[Segment]]) -> str:
    return '\n'.join(''.join(seg.text for seg in row) for row in rows)


def _row_to_text(row: list[Segment]) -> Text:
    text = Text()
    for seg in row:
        text.append(seg.text, seg.style)
    return text


def segments_to_ansi(rows: list[list[Segment]], width: int) -> str:
    buf = StringIO()
    console = Console(file=buf, force_terminal=True, color_system='truecolor', width=width + 2, legacy_windows=False)
    for row in rows:
        console.print(_row_to_text(row))
    return buf.getvalue()
