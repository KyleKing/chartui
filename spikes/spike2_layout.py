"""Spike 2: layout and ticks.

Lays out the four tail-cw charts at 40, 80, and 160 columns, with time axes spanning ten
minutes, a day, and a quarter, twice each: once with the one-pass Frame DESIGN.md
commits to, once with a fixed-point Frame that iterates layout and scale until the
gutter stops changing. Prints every frame and the column-cost table, and writes each
frame to spikes/out/ as .ansi and .txt.

Run: uv run python spikes/spike2_layout.py
"""

from __future__ import annotations

import datetime as dt
import itertools
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from canvas import Canvas
from data import (
    MinMaxBand,
    SeverityBucket,
    converging_series,
    flat_line_with_spike,
    minmax_band_with_median,
    severity_histogram,
)
from glyphs import GLYPHS, Glyphs
from layout import Frame, layout_fixed_point, layout_one_pass
from rich.segment import Segment
from scale import LinearScale, TimeScale
from surface import canvas_to_segments, segments_to_ansi, segments_to_plain

OUT_DIR = Path(__file__).parent / 'out'
CANONICAL_N = 200
HEIGHT = 14
WIDTHS = (40, 80, 160)
SPANS = {
    'ten minutes': dt.timedelta(minutes=10),
    'a day': dt.timedelta(days=1),
    'a quarter': dt.timedelta(days=91),
}
DOMAIN_START = dt.datetime(2026, 1, 15, 9, 0, 0, tzinfo=dt.UTC)

COLOR_A = (100, 200, 255)
COLOR_B = (255, 180, 80)
COLOR_MEDIAN = (240, 240, 240)
COLOR_BAND_FILL = (45, 60, 78)
SEVERITY_COLOR = {
    'muted': (120, 120, 120),
    'info': (100, 200, 255),
    'warning': (230, 180, 60),
    'error': (230, 90, 70),
    'critical': (200, 40, 40),
}


def resample(values: list[float], target_n: int) -> list[float]:
    n = len(values)
    if target_n <= 0:
        return []
    if n == 1 or target_n == 1:
        return [values[0]] * target_n
    out = []
    for x in range(target_n):
        t = x / (target_n - 1) * (n - 1)
        i = min(int(t), n - 2)
        frac = t - i
        out.append(values[i] + (values[i + 1] - values[i]) * frac)
    return out


class ChartSpec:
    def __init__(self, name: str, series_names: list[str]) -> None:
        self.name = name
        self.series_names = series_names

    def y_domain(self) -> tuple[float, float]:
        raise NotImplementedError

    def draw(self, canvas: Canvas, plot_width: int) -> None:
        raise NotImplementedError


class FlatLineSpike(ChartSpec):
    def __init__(self) -> None:
        super().__init__('flat line with one spike', ['value'])
        self.values = flat_line_with_spike(CANONICAL_N)

    def y_domain(self) -> tuple[float, float]:
        lo, hi = min(self.values), max(self.values)
        pad = (hi - lo) * 0.1 or 1.0
        return (lo - pad, hi + pad)

    def draw(self, canvas: Canvas, plot_width: int) -> None:
        values = resample(self.values, plot_width * canvas.glyphs.cols)
        _draw_line(canvas, values, self.y_domain(), COLOR_A)


class ConvergingSeries(ChartSpec):
    def __init__(self) -> None:
        super().__init__('two converging series', ['rising', 'falling'])
        self.a, self.b = converging_series(CANONICAL_N)

    def y_domain(self) -> tuple[float, float]:
        combined = self.a + self.b
        lo, hi = min(combined), max(combined)
        pad = (hi - lo) * 0.1 or 1.0
        return (lo - pad, hi + pad)

    def draw(self, canvas: Canvas, plot_width: int) -> None:
        domain = self.y_domain()
        _draw_line(canvas, resample(self.a, plot_width * canvas.glyphs.cols), domain, COLOR_A)
        _draw_line(canvas, resample(self.b, plot_width * canvas.glyphs.cols), domain, COLOR_B)


class SeverityHistogram(ChartSpec):
    def __init__(self) -> None:
        super().__init__('severity histogram', [])
        self.buckets: list[SeverityBucket] = severity_histogram()

    def y_domain(self) -> tuple[float, float]:
        return (0.0, max(b.count for b in self.buckets) * 1.05)

    def draw(self, canvas: Canvas, _plot_width: int) -> None:
        sub_w, sub_h = canvas.sub_w, canvas.sub_h
        max_count = max(b.count for b in self.buckets)
        gap = max(1, sub_w // (len(self.buckets) * 8))
        bar_w = max(1, (sub_w - gap * (len(self.buckets) - 1)) // len(self.buckets))
        x = 0
        for bucket in self.buckets:
            bar_h = round(bucket.count / max_count * (sub_h - 1))
            color = SEVERITY_COLOR[bucket.role]
            canvas.rect(x, sub_h - 1 - bar_h, x + bar_w - 1, sub_h - 1, fill=color, solid=color)
            x += bar_w + gap


class MinMaxBandMedian(ChartSpec):
    def __init__(self) -> None:
        super().__init__('min-max band with median', ['min', 'max', 'median'])
        self.band: MinMaxBand = minmax_band_with_median(CANONICAL_N)

    def y_domain(self) -> tuple[float, float]:
        lo, hi = min(self.band.minimum), max(self.band.maximum)
        pad = (hi - lo) * 0.1 or 1.0
        return (lo - pad, hi + pad)

    def draw(self, canvas: Canvas, plot_width: int) -> None:
        domain = self.y_domain()
        y_scale = LinearScale(domain, (canvas.sub_h - 1, 0))
        n = plot_width * canvas.glyphs.cols
        minimum = resample(self.band.minimum, n)
        maximum = resample(self.band.maximum, n)
        for x in range(n):
            y_min, y_max = round(y_scale(minimum[x])), round(y_scale(maximum[x]))
            canvas.rect(x, y_max, x, y_min, fill=COLOR_BAND_FILL)
        _draw_line(canvas, resample(self.band.median, n), domain, COLOR_MEDIAN)


def _draw_line(canvas: Canvas, values: list[float], y_domain: tuple[float, float], color: tuple[int, int, int]) -> None:
    x_scale = LinearScale((0, len(values) - 1), (0, canvas.sub_w - 1))
    y_scale = LinearScale(y_domain, (canvas.sub_h - 1, 0))
    points = [(round(x_scale(i)), round(y_scale(v))) for i, v in enumerate(values)]
    for (x0, y0), (x1, y1) in itertools.pairwise(points):
        canvas.line(x0, y0, x1, y1, color=color)


CHARTS: list[ChartSpec] = [FlatLineSpike(), ConvergingSeries(), SeverityHistogram(), MinMaxBandMedian()]


def _y_row_labels(frame: Frame, y_domain: tuple[float, float], glyphs: Glyphs) -> dict[int, str]:
    sub_h = frame.plot_height * glyphs.rows
    y_scale = LinearScale(y_domain, (sub_h - 1, 0))
    labels: dict[int, str] = {}
    for value, text in frame.y_ticks:
        cy = min(max(round(y_scale(value)) // glyphs.rows, 0), frame.plot_height - 1)
        labels[cy] = text
    return labels


def _x_axis_row(frame: Frame, x_domain: tuple[dt.datetime, dt.datetime], glyphs: Glyphs) -> str:
    chars = [' '] * frame.width
    if frame.plot_width <= 0:
        return ''.join(chars)
    x_scale = TimeScale(x_domain, (0, frame.plot_width * glyphs.cols - 1))
    for tick, text in frame.x_ticks:
        column = frame.plot_x + round(x_scale(tick)) // glyphs.cols
        for offset, ch in enumerate(text):
            pos = column + offset
            if frame.plot_x <= pos < frame.plot_x + frame.plot_width:
                chars[pos] = ch
    return ''.join(chars)


def render_frame(
    frame: Frame, chart: ChartSpec, x_domain: tuple[dt.datetime, dt.datetime], glyphs: Glyphs, title: str
) -> tuple[str, str]:
    canvas = Canvas(max(frame.plot_width, 1), frame.plot_height, glyphs)
    if frame.plot_width > 0:
        chart.draw(canvas, frame.plot_width)
    canvas_rows = canvas_to_segments(canvas)
    row_labels = _y_row_labels(frame, chart.y_domain(), glyphs)

    rows: list[list[Segment]] = [[Segment(title.ljust(frame.width)[: frame.width])]]
    for cy in range(frame.plot_height):
        label = row_labels.get(cy, '')
        left = Segment(label.rjust(max(frame.left_gutter - 1, 0)) + ' ' if frame.left_gutter else '')
        canvas_segs = canvas_rows[cy] if frame.plot_width > 0 else []
        legend = ''
        if frame.right_gutter and cy < len(chart.series_names):
            legend = chart.series_names[cy].ljust(frame.right_gutter)[: frame.right_gutter]
        elif frame.right_gutter:
            legend = ' ' * frame.right_gutter
        reserve = ' ' * frame.label_reserve
        rows.append([left, *canvas_segs, Segment(reserve), Segment(legend)])
    rows.append([Segment(_x_axis_row(frame, x_domain, glyphs))])

    plain = segments_to_plain(rows)
    ansi = segments_to_ansi(rows, frame.width)
    return plain, ansi


def write_frame(name: str, plain: str, ansi: str) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / f'{name}.txt').write_text(plain + '\n')
    (OUT_DIR / f'{name}.ansi').write_text(ansi)


def slugify(text: str) -> str:
    return text.lower().replace(' ', '-')


def glyphs_for(chart: ChartSpec) -> Glyphs:
    return GLYPHS['QUADRANT'] if chart.name == 'severity histogram' else GLYPHS['BRAILLE']


def run_case(chart: ChartSpec, width: int, span_name: str, span: dt.timedelta) -> tuple[Frame, Frame, str, str]:
    x_domain = (DOMAIN_START, DOMAIN_START + span)
    y_domain = chart.y_domain()
    one_pass = layout_one_pass(width, HEIGHT, y_domain, x_domain, chart.series_names)
    fixed = layout_fixed_point(width, HEIGHT, y_domain, x_domain, chart.series_names)
    glyphs = glyphs_for(chart)
    title = f'{chart.name} | {width}col | {span_name}'
    for frame, mode in ((one_pass, 'onepass'), (fixed, 'fixedpoint')):
        plain, ansi = render_frame(frame, chart, x_domain, glyphs, f'{title} | {mode}')
        write_frame(f'{slugify(chart.name)}-{width}col-{slugify(span_name)}-{mode}', plain, ansi)
    return one_pass, fixed, x_domain[0].isoformat(), x_domain[1].isoformat()


def print_and_return_table_row(chart: ChartSpec, width: int, span_name: str, one_pass: Frame, fixed: Frame) -> dict:
    return {
        'chart': chart.name,
        'width': width,
        'span': span_name,
        'onepass_plot_width': one_pass.plot_width,
        'fixed_plot_width': fixed.plot_width,
        'columns_given_up': fixed.plot_width - one_pass.plot_width,
        'fixed_iterations': fixed.iterations,
        'onepass_x_ticks': len(one_pass.x_ticks),
        'fixed_x_ticks': len(fixed.x_ticks),
    }


def print_frame_pair(chart: ChartSpec, width: int, span_name: str, span: dt.timedelta) -> dict:
    one_pass, fixed, _start, _end = run_case(chart, width, span_name, span)
    print(f'=== {chart.name} | {width}col | {span_name} ===')
    print(
        f'one-pass: plot_width={one_pass.plot_width} legend={one_pass.right_gutter} '
        f'direct_label={one_pass.direct_label} x_ticks={[t for _, t in one_pass.x_ticks]}'
    )
    print(
        f'fixed-point ({fixed.iterations} iter): plot_width={fixed.plot_width} legend={fixed.right_gutter} '
        f'direct_label={fixed.direct_label} x_ticks={[t for _, t in fixed.x_ticks]}'
    )
    print()
    return print_and_return_table_row(chart, width, span_name, one_pass, fixed)


def print_table(rows: list[dict]) -> str:
    header = (
        f'{"chart":<26} {"width":>5} {"span":<12} {"one-pass":>8} {"fixed":>6} '
        f'{"given up":>8} {"iters":>5} {"ticks (1p/fp)":>13}'
    )
    body = [
        f'{row["chart"]:<26} {row["width"]:>5} {row["span"]:<12} {row["onepass_plot_width"]:>8} '
        f'{row["fixed_plot_width"]:>6} {row["columns_given_up"]:>8} {row["fixed_iterations"]:>5} '
        f'{row["onepass_x_ticks"]:>5}/{row["fixed_x_ticks"]:<5}'
        for row in rows
    ]
    table = '\n'.join([header, '-' * len(header), *body])
    print(table)
    return table


def failure_cases() -> None:
    print('=== failure case: axis too narrow for any label ===')
    chart = FlatLineSpike()
    x_domain = (DOMAIN_START, DOMAIN_START + dt.timedelta(days=1))
    frame = layout_one_pass(8, HEIGHT, chart.y_domain(), x_domain, chart.series_names)
    print(f'width=8: plot_width={frame.plot_width} x_ticks={frame.x_ticks}')
    plain, ansi = render_frame(frame, chart, x_domain, glyphs_for(chart), 'narrow axis | onepass')
    write_frame('failure-narrow-axis-onepass', plain, ansi)
    print()

    print('=== failure case: domain straddles a month boundary ===')
    x_domain = (dt.datetime(2026, 1, 20, tzinfo=dt.UTC), dt.datetime(2026, 2, 10, tzinfo=dt.UTC))
    frame = layout_one_pass(80, HEIGHT, chart.y_domain(), x_domain, chart.series_names)
    print(f'ticks: {[t for _, t in frame.x_ticks]}')
    plain, ansi = render_frame(frame, chart, x_domain, glyphs_for(chart), 'month boundary | onepass')
    write_frame('failure-month-boundary-onepass', plain, ansi)
    print()

    print('=== failure case: domain under a minute ===')
    x_domain = (dt.datetime(2026, 1, 20, 12, 0, 0, tzinfo=dt.UTC), dt.datetime(2026, 1, 20, 12, 0, 45, tzinfo=dt.UTC))
    frame = layout_one_pass(80, HEIGHT, chart.y_domain(), x_domain, chart.series_names)
    print(f'ticks: {[t for _, t in frame.x_ticks]}')
    plain, ansi = render_frame(frame, chart, x_domain, glyphs_for(chart), 'under a minute | onepass')
    write_frame('failure-under-a-minute-onepass', plain, ansi)
    print()


def main() -> None:
    rows = []
    for chart in CHARTS:
        for width in WIDTHS:
            for span_name, span in SPANS.items():
                rows.append(print_frame_pair(chart, width, span_name, span))

    print('=== column-cost table ===')
    table = print_table(rows)
    print()

    failure_cases()

    (OUT_DIR / 'spike2-column-cost.txt').write_text(table + '\n')


if __name__ == '__main__':
    main()
