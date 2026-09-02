"""Spike 1: canvas look.

Renders the four tail-cw charts named in DESIGN.md's spike list with the bitmap Canvas
at BLOCK, HALFBLOCK, QUADRANT, SEXTANT, OCTANT, and BRAILLE packing, and against
linecast's float framebuffer as the antialiased reference. Prints every frame to the
terminal and writes each one to spikes/out/ as .ansi (with escape codes) and .txt
(plain), so the frames can be read back with `cat` without rerunning.

Run: uv run python spikes/spike1_canvas.py
"""

from __future__ import annotations

import sys
import time
from pathlib import Path
from typing import TYPE_CHECKING

sys.path.insert(0, str(Path(__file__).parent))

if TYPE_CHECKING:
    from collections.abc import Callable

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
from linecast._framebuffer import Framebuffer
from scale import LinearScale
from surface import canvas_to_segments, segments_to_ansi, segments_to_plain

OUT_DIR = Path(__file__).parent / 'out'

RGB = tuple[int, int, int]

COLOR_A = (100, 200, 255)
COLOR_B = (255, 180, 80)
COLOR_SPIKE = (255, 90, 90)
COLOR_BAND_FILL = (45, 60, 78)
COLOR_MEDIAN = (240, 240, 240)
SPIKE_GLOW_THRESHOLD = 0.5
SEVERITY_COLOR = {
    'muted': (120, 120, 120),
    'info': (100, 200, 255),
    'warning': (230, 180, 60),
    'error': (230, 90, 70),
    'critical': (200, 40, 40),
}


def lerp_rgb(a: RGB, b: RGB, t: float) -> RGB:
    t = max(0.0, min(1.0, t))
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))


def value_colormap(lo: float, hi: float, cold: RGB, hot: RGB) -> Callable[[float], RGB]:
    def _map(value: float) -> RGB:
        t = 0.0 if hi == lo else (value - lo) / (hi - lo)
        return lerp_rgb(cold, hot, t)

    return _map


# ---------------------------------------------------------------------------
# Chart builders: bitmap Canvas
# ---------------------------------------------------------------------------
def draw_line_series(canvas: Canvas, values: list[float], *, color: RGB | None, value_keyed: bool) -> None:
    sub_w, sub_h = canvas.sub_w, canvas.sub_h
    lo, hi = min(values), max(values)
    pad = (hi - lo) * 0.1 or 1.0
    x_scale = LinearScale((0, len(values) - 1), (0, sub_w - 1))
    y_scale = LinearScale((lo - pad, hi + pad), (sub_h - 1, 0))
    points = [(round(x_scale(i)), round(y_scale(v))) for i, v in enumerate(values)]
    for (x0, y0), (x1, y1), v0, v1 in zip(points[:-1], points[1:], values[:-1], values[1:], strict=True):
        canvas.line(x0, y0, x1, y1, color=None if value_keyed else color, value=(v0 + v1) / 2 if value_keyed else None)
    if value_keyed:
        canvas.resolve_value_colors(value_colormap(lo, hi, COLOR_A, COLOR_SPIKE))


def canvas_flat_line_with_spike(glyphs: Glyphs, width: int, height: int) -> Canvas:
    canvas = Canvas(width, height, glyphs)
    draw_line_series(canvas, flat_line_with_spike(width * glyphs.cols), color=COLOR_A, value_keyed=True)
    return canvas


def canvas_converging_series(glyphs: Glyphs, width: int, height: int) -> Canvas:
    canvas = Canvas(width, height, glyphs)
    a, b = converging_series(width * glyphs.cols)
    draw_line_series(canvas, a, color=COLOR_A, value_keyed=False)
    draw_line_series(canvas, b, color=COLOR_B, value_keyed=False)
    return canvas


def canvas_severity_histogram(glyphs: Glyphs, width: int, height: int) -> Canvas:
    canvas = Canvas(width, height, glyphs)
    buckets: list[SeverityBucket] = severity_histogram()
    sub_w, sub_h = canvas.sub_w, canvas.sub_h
    max_count = max(b.count for b in buckets)
    gap = max(1, sub_w // (len(buckets) * 8))
    bar_w = (sub_w - gap * (len(buckets) - 1)) // len(buckets)
    x = 0
    for bucket in buckets:
        bar_h = round(bucket.count / max_count * (sub_h - 1))
        color = SEVERITY_COLOR[bucket.role]
        canvas.rect(x, sub_h - 1 - bar_h, x + bar_w - 1, sub_h - 1, fill=color, solid=color)
        x += bar_w + gap
    return canvas


def canvas_minmax_band(glyphs: Glyphs, width: int, height: int) -> Canvas:
    canvas = Canvas(width, height, glyphs)
    band: MinMaxBand = minmax_band_with_median(width * glyphs.cols)
    sub_w, sub_h = canvas.sub_w, canvas.sub_h
    lo = min(band.minimum)
    hi = max(band.maximum)
    pad = (hi - lo) * 0.1 or 1.0
    x_scale = LinearScale((0, len(band.minimum) - 1), (0, sub_w - 1))
    y_scale = LinearScale((lo - pad, hi + pad), (sub_h - 1, 0))
    for i in range(len(band.minimum)):
        x = round(x_scale(i))
        y_min = round(y_scale(band.minimum[i]))
        y_max = round(y_scale(band.maximum[i]))
        canvas.rect(x, y_max, x, y_min, fill=COLOR_BAND_FILL)
    draw_line_series(canvas, band.median, color=COLOR_MEDIAN, value_keyed=False)
    return canvas


CHART_BUILDERS = {
    'flat line with one spike': canvas_flat_line_with_spike,
    'two converging series': canvas_converging_series,
    'severity histogram': canvas_severity_histogram,
    'min-max band with median': canvas_minmax_band,
}


# ---------------------------------------------------------------------------
# Chart builders: linecast float framebuffer reference
# ---------------------------------------------------------------------------
def fb_line_series(fb: Framebuffer, values: list[float], color: RGB, sigma: float = 0.7) -> None:
    lo, hi = min(values), max(values)
    pad = (hi - lo) * 0.1 or 1.0
    y_scale = LinearScale((lo - pad, hi + pad), (fb.total_spy - 1, 0))
    n = len(values)
    curve_spy = []
    for x in range(fb.graph_w):
        t = x / max(1, fb.graph_w - 1) * (n - 1)
        i = min(int(t), n - 2) if n > 1 else 0
        frac = t - i
        v = values[i] + (values[i + 1] - values[i]) * frac if n > 1 else values[0]
        curve_spy.append(y_scale(v))
    fb.draw_curve(curve_spy, color, sigma=sigma)


def fb_flat_line_with_spike(width: int, height_cells: int) -> Framebuffer:
    fb = Framebuffer(width, height_cells)
    values = flat_line_with_spike(width)
    lo, hi = min(values), max(values)
    fb_line_series(fb, values, COLOR_A)
    for x in range(fb.graph_w):
        t = x / max(1, fb.graph_w - 1) * (len(values) - 1)
        v = values[min(round(t), len(values) - 1)]
        intensity = (v - lo) / (hi - lo) if hi != lo else 0.0
        if intensity > SPIKE_GLOW_THRESHOLD:
            y_scale = LinearScale((lo - (hi - lo) * 0.1, hi + (hi - lo) * 0.1), (fb.total_spy - 1, 0))
            fb.draw_radial(x, y_scale(v), COLOR_SPIKE, radius=3, peak_alpha=intensity)
    return fb


def fb_converging_series(width: int, height_cells: int) -> Framebuffer:
    fb = Framebuffer(width, height_cells)
    a, b = converging_series(width)
    fb_line_series(fb, a, COLOR_A)
    fb_line_series(fb, b, COLOR_B)
    return fb


def fb_severity_histogram(width: int, height_cells: int) -> Framebuffer:
    fb = Framebuffer(width, height_cells)
    buckets = severity_histogram()
    max_count = max(b.count for b in buckets)
    bar_w = width // len(buckets)
    bottom_spy = fb.total_spy - 1
    for bi, bucket in enumerate(buckets):
        top_frac = 1.0 - bucket.count / max_count
        top_spy = top_frac * (fb.total_spy - 1)
        lo_x, hi_x = bi * bar_w, min(width, (bi + 1) * bar_w - 1)
        curve_spy = [top_spy if lo_x <= x < hi_x else bottom_spy for x in range(width)]
        color = SEVERITY_COLOR[bucket.role]
        fb.draw_fill(curve_spy, fb.total_spy, lambda _t, c=color: c, aspect=1.0)
    return fb


def fb_minmax_band(width: int, height_cells: int) -> Framebuffer:
    fb = Framebuffer(width, height_cells)
    band = minmax_band_with_median(width)
    lo, hi = min(band.minimum), max(band.maximum)
    pad = (hi - lo) * 0.1 or 1.0
    y_scale = LinearScale((lo - pad, hi + pad), (fb.total_spy - 1, 0))
    n = len(band.minimum)

    def resample(series: list[float]) -> list[float]:
        out = []
        for x in range(fb.graph_w):
            t = x / max(1, fb.graph_w - 1) * (n - 1)
            i = min(int(t), n - 2) if n > 1 else 0
            frac = t - i
            out.append(series[i] + (series[i + 1] - series[i]) * frac if n > 1 else series[0])
        return out

    min_spy = [y_scale(v) for v in resample(band.minimum)]
    max_spy = [y_scale(v) for v in resample(band.maximum)]
    for x in range(fb.graph_w):
        top, bottom = max_spy[x], min_spy[x]
        for spy in range(max(0, round(top)), min(fb.total_spy, round(bottom) + 1)):
            fb.fb[spy][x] = COLOR_BAND_FILL
    fb_line_series(fb, band.median, COLOR_MEDIAN, sigma=0.5)
    return fb


FB_BUILDERS = {
    'flat line with one spike': fb_flat_line_with_spike,
    'two converging series': fb_converging_series,
    'severity histogram': fb_severity_histogram,
    'min-max band with median': fb_minmax_band,
}


# ---------------------------------------------------------------------------
# Glyph coverage probe
# ---------------------------------------------------------------------------
def probe_line() -> str:
    braille = chr(0x2800 | 0xFF)
    quadrant = GLYPHS['QUADRANT'].to_char(0b0110)
    sextant = GLYPHS['SEXTANT'].to_char(0b101010)
    octant = GLYPHS['OCTANT'].to_char(0b10110100)
    halfblock = GLYPHS['HALFBLOCK'].to_char(0b01)
    fullblock = GLYPHS['BLOCK'].to_char(1)
    labels = [
        ('braille', braille),
        ('quadrant', quadrant),
        ('sextant', sextant),
        ('octant', octant),
        ('half-block', halfblock),
        ('full block', fullblock),
    ]
    return '  '.join(f'{name}={glyph}' for name, glyph in labels)


# ---------------------------------------------------------------------------
# Rendering and output
# ---------------------------------------------------------------------------
def write_frame(name: str, plain: str, ansi: str) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / f'{name}.txt').write_text(plain + '\n')
    (OUT_DIR / f'{name}.ansi').write_text(ansi)


def render_and_show(canvas: Canvas) -> str:
    rows = canvas_to_segments(canvas)
    plain = segments_to_plain(rows)
    ansi = segments_to_ansi(rows, canvas.width_cells)
    print(ansi, end='')
    return plain


def slugify(text: str) -> str:
    return text.lower().replace(' ', '-')


def main() -> None:
    print(probe_line())
    print()

    width, height = 60, 10
    for chart_name, builder in CHART_BUILDERS.items():
        print(f'=== {chart_name} ===')
        for glyph_name in ('BLOCK', 'HALFBLOCK', 'QUADRANT', 'SEXTANT', 'OCTANT', 'BRAILLE'):
            glyphs = GLYPHS[glyph_name]
            canvas = builder(glyphs, width, height)
            print(f'--- {glyph_name} ---')
            plain = render_and_show(canvas)
            rows = canvas_to_segments(canvas)
            write_frame(f'{slugify(chart_name)}-{glyph_name.lower()}', plain, segments_to_ansi(rows, width))
        print('--- linecast reference (float framebuffer) ---')
        fb = FB_BUILDERS[chart_name](width, height)
        lines = fb.render()
        for line in lines:
            print(line)
        plain_ref = '\n'.join(line for line in lines)
        write_frame(f'{slugify(chart_name)}-linecast', plain_ref, '\n'.join(lines))
        print()

    # ------------------------------------------------------------------
    # Timing: 120x40 focused chart, four series of 500 points, budget 16ms
    # ------------------------------------------------------------------
    print('=== timing (120x40, 4 series x 500 points) ===')
    rng_series = []
    for seed in range(4):
        a, _b = converging_series(500, seed=100 + seed)
        rng_series.append(a)

    def build_perf_canvas(glyph_name: str) -> float:
        glyphs = GLYPHS[glyph_name]
        start = time.perf_counter()
        canvas = Canvas(120, 40, glyphs)
        for series in rng_series:
            draw_line_series(canvas, series, color=COLOR_A, value_keyed=False)
        rows = canvas_to_segments(canvas)
        segments_to_plain(rows)
        return (time.perf_counter() - start) * 1000

    for glyph_name in ('BRAILLE', 'QUADRANT', 'OCTANT'):
        elapsed_ms = build_perf_canvas(glyph_name)
        print(f'{glyph_name}: {elapsed_ms:.2f} ms (budget 16 ms)')


if __name__ == '__main__':
    main()
