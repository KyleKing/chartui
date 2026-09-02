"""Frame: gutters, plot rect, legend column.

Two ways to reach a Frame: `layout_one_pass` follows DESIGN.md's committed algorithm
(format ticks once, decide the legend defensively, never recheck against the final plot
width). `layout_fixed_point` iterates the same decision against the width it actually
produces, capped at `max_iterations`, so the two can be compared.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

from scale import nice_ticks, time_ticks

TITLE_GUTTER = 1
XAXIS_GUTTER = 1
MIN_DATA_WIDTH = 10


@dataclass
class Frame:
    width: int
    height: int
    left_gutter: int
    right_gutter: int
    top_gutter: int
    bottom_gutter: int
    plot_x: int
    plot_y: int
    plot_width: int
    plot_height: int
    direct_label: bool
    label_reserve: int
    y_ticks: list[tuple[float, str]]
    x_ticks: list[tuple[dt.datetime, str]]
    iterations: int


def _y_tick_labels(y_domain: tuple[float, float]) -> list[tuple[float, str]]:
    return [(v, f'{v:g}') for v in nice_ticks(*y_domain)]


def _left_gutter(y_ticks: list[tuple[float, str]]) -> int:
    return max((len(label) for _, label in y_ticks), default=0) + 1


def _label_reserve(series_names: list[str]) -> int:
    return max(len(name) for name in series_names) + 1 if series_names else 0


def _direct_fits(candidate_width: int, reserve: int) -> bool:
    return reserve == 0 or candidate_width - reserve >= MIN_DATA_WIDTH


def layout_one_pass(
    width: int,
    height: int,
    y_domain: tuple[float, float],
    x_domain: tuple[dt.datetime, dt.datetime],
    series_names: list[str],
) -> Frame:
    y_ticks = _y_tick_labels(y_domain)
    left_gutter = _left_gutter(y_ticks)
    reserve = _label_reserve(series_names)
    direct_label = len(series_names) <= 1
    right_gutter = 0 if direct_label else max(len(name) for name in series_names) + 2
    label_reserve = reserve if direct_label and series_names else 0
    plot_width = max(0, width - left_gutter - right_gutter - label_reserve)
    plot_height = max(0, height - TITLE_GUTTER - XAXIS_GUTTER)
    return Frame(
        width,
        height,
        left_gutter,
        right_gutter,
        TITLE_GUTTER,
        XAXIS_GUTTER,
        left_gutter,
        TITLE_GUTTER,
        plot_width,
        plot_height,
        direct_label,
        label_reserve,
        y_ticks,
        time_ticks(x_domain, plot_width),
        iterations=1,
    )


def layout_fixed_point(
    width: int,
    height: int,
    y_domain: tuple[float, float],
    x_domain: tuple[dt.datetime, dt.datetime],
    series_names: list[str],
    *,
    max_iterations: int = 5,
) -> Frame:
    y_ticks = _y_tick_labels(y_domain)
    left_gutter = _left_gutter(y_ticks)
    reserve = _label_reserve(series_names)
    candidate_width = max(0, width - left_gutter)
    direct_label, right_gutter, label_reserve = True, 0, 0
    iterations = 0
    for i in range(1, max_iterations + 1):
        iterations = i
        direct_label = len(series_names) <= 1 or _direct_fits(candidate_width, reserve)
        right_gutter = 0 if direct_label else max(len(name) for name in series_names) + 2
        label_reserve = reserve if direct_label and series_names else 0
        new_width = max(0, width - left_gutter - right_gutter - label_reserve)
        if new_width == candidate_width:
            break
        candidate_width = new_width
    plot_height = max(0, height - TITLE_GUTTER - XAXIS_GUTTER)
    return Frame(
        width,
        height,
        left_gutter,
        right_gutter,
        TITLE_GUTTER,
        XAXIS_GUTTER,
        left_gutter,
        TITLE_GUTTER,
        candidate_width,
        plot_height,
        direct_label,
        label_reserve,
        y_ticks,
        time_ticks(x_domain, candidate_width),
        iterations,
    )
