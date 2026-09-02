"""Spike 3: transitions.

A Textual app that swaps between two datasets on a keypress, with and without the
`interpolate` tween in spikes/transition.py, at 5, 10, and 20 frames. Settles whether
the tween reads as motion or as noise at terminal frame rates, and what frame count and
easing to fix in DESIGN.md.

Run interactively: uv run python spikes/spike3_transitions.py
Run non-interactively (for VHS): uv run python spikes/spike3_transitions.py --auto

Keys: 1/2/3 pick 5/10/20 frames, t toggles the tween on/off, e toggles linear vs
ease_out_cubic, space swaps to the other dataset, q quits.
"""

from __future__ import annotations

import argparse
import asyncio
import operator
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from canvas import Canvas
from data import flat_line_with_spike
from glyphs import GLYPHS, Glyphs
from rich.segment import Segment
from rich.style import Style
from rich.text import Text
from scale import LinearScale
from surface import canvas_to_segments, segments_to_ansi, segments_to_plain
from textual.app import App, ComposeResult
from textual.widgets import Static
from transition import EASINGS, EasingFn, Point, TweenPoint, interpolate

OUT_DIR = Path(__file__).parent / 'out'

RGB = tuple[int, int, int]
COLOR_LINE = (100, 200, 255)
COLOR_FADE = (230, 120, 60)

DEMO_WIDTH, DEMO_HEIGHT = 64, 12
PERF_WIDTH, PERF_HEIGHT = 120, 40
FRAME_COUNTS = (5, 10, 20)
TRANSITION_BUDGET_MS = 200.0
FRAME_BUDGET_MS = 16.0


def _series(n: int, seed: int, *, shift: int = 0, offset: float = 0.0) -> list[Point]:
    values = flat_line_with_spike(n, seed=seed)
    return [(float(i + shift), v + offset) for i, v in enumerate(values)]


def demo_before() -> list[Point]:
    return _series(40, seed=10)


def demo_after() -> list[Point]:
    return _series(40, seed=11, shift=8, offset=60.0)


def perf_before() -> list[Point]:
    return _series(500, seed=20)


def perf_after() -> list[Point]:
    return _series(500, seed=21, shift=40, offset=60.0)


def lerp_rgb(a: RGB, b: RGB, t: float) -> RGB:
    t = max(0.0, min(1.0, t))
    return (
        round(a[0] + (b[0] - a[0]) * t),
        round(a[1] + (b[1] - a[1]) * t),
        round(a[2] + (b[2] - a[2]) * t),
    )


def _point_coords(points: list[TweenPoint], sub_w: int, sub_h: int) -> list[tuple[int, int]]:
    xs, ys = [p.x for p in points], [p.y for p in points]
    lo, hi = min(ys), max(ys)
    pad = (hi - lo) * 0.1 or 1.0
    x_scale = LinearScale((min(xs), max(xs)), (0, sub_w - 1))
    y_scale = LinearScale((lo - pad, hi + pad), (sub_h - 1, 0))
    return [(round(x_scale(p.x)), round(y_scale(p.y))) for p in points]


def build_transition_canvas(points: list[TweenPoint], width: int, height: int, glyphs: Glyphs) -> Canvas:
    canvas = Canvas(width, height, glyphs)
    coords = _point_coords(points, canvas.sub_w, canvas.sub_h)
    for i in range(len(points) - 1):
        if points[i].alpha >= 1.0 and points[i + 1].alpha >= 1.0:
            (x0, y0), (x1, y1) = coords[i], coords[i + 1]
            canvas.line(x0, y0, x1, y1, color=COLOR_LINE)
    for (x, _y), point in zip(coords, points, strict=True):
        if point.alpha < 1.0:
            cx = x // glyphs.cols
            fade = lerp_rgb((30, 30, 30), COLOR_FADE, point.alpha)
            for cy in range(canvas.height_cells):
                canvas.fill_cell(cx, cy, fade)
    return canvas


def rows_to_text(rows: list[list[Segment]]) -> Text:
    text = Text()
    for i, row in enumerate(rows):
        if i:
            text.append('\n')
        for seg in row:
            text.append(seg.text, seg.style or Style())
    return text


def render_points(points: list[TweenPoint], width: int, height: int) -> tuple[str, str, Text]:
    canvas = build_transition_canvas(points, width, height, GLYPHS['BRAILLE'])
    rows = canvas_to_segments(canvas)
    return segments_to_plain(rows), segments_to_ansi(rows, width), rows_to_text(rows)


def render_to_segments(points: list[TweenPoint], width: int, height: int) -> str:
    """The render_line-equivalent cost: build to Segments and flatten, no ansi encoding."""
    canvas = build_transition_canvas(points, width, height, GLYPHS['BRAILLE'])
    rows = canvas_to_segments(canvas)
    return segments_to_plain(rows)


def full_alpha_points(series: list[Point]) -> list[TweenPoint]:
    return [TweenPoint(x, y, 1.0) for x, y in series]


def slugify(text: str) -> str:
    return text.lower().replace(' ', '-').replace('_', '-')


def write_frame(name: str, plain: str, ansi: str) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / f'{name}.txt').write_text(plain + '\n')
    (OUT_DIR / f'{name}.ansi').write_text(ansi)


def write_representative_frames() -> None:
    before, after = demo_before(), demo_after()
    plain, ansi, _ = render_points(full_alpha_points(before), DEMO_WIDTH, DEMO_HEIGHT)
    write_frame('transition-notween-before', plain, ansi)
    plain, ansi, _ = render_points(full_alpha_points(after), DEMO_WIDTH, DEMO_HEIGHT)
    write_frame('transition-notween-after', plain, ansi)
    for frame_count in FRAME_COUNTS:
        for ease_name, ease_fn in EASINGS.items():
            for i in (0, frame_count // 2, frame_count - 1):
                t = i / (frame_count - 1) if frame_count > 1 else 1.0
                points = interpolate(before, after, t, ease=ease_fn)
                plain, ansi, _ = render_points(points, DEMO_WIDTH, DEMO_HEIGHT)
                name = f'transition-tween-f{frame_count}-{slugify(ease_name)}-frame{i}'
                write_frame(name, plain, ansi)


def _run_sequence(
    before: list[Point], after: list[Point], frame_count: int, ease_fn: EasingFn
) -> tuple[list[float], float]:
    frame_times = []
    start = time.perf_counter()
    for i in range(frame_count):
        t = i / (frame_count - 1) if frame_count > 1 else 1.0
        frame_start = time.perf_counter()
        points = interpolate(before, after, t, ease=ease_fn)
        render_to_segments(points, PERF_WIDTH, PERF_HEIGHT)
        frame_times.append((time.perf_counter() - frame_start) * 1000)
    return frame_times, (time.perf_counter() - start) * 1000


def measure_timings(repeats: int = 5) -> dict[tuple[int, str], dict[str, object]]:
    before, after = perf_before(), perf_after()
    results: dict[tuple[int, str], dict[str, object]] = {}
    for frame_count in FRAME_COUNTS:
        for ease_name, ease_fn in EASINGS.items():
            runs = [_run_sequence(before, after, frame_count, ease_fn) for _ in range(repeats)]
            frame_times, total_ms = min(runs, key=operator.itemgetter(1))
            results[frame_count, ease_name] = {'frame_times': frame_times, 'total_ms': total_ms}
    single_times = []
    for _ in range(repeats):
        single_start = time.perf_counter()
        render_to_segments(full_alpha_points(after), PERF_WIDTH, PERF_HEIGHT)
        single_times.append((time.perf_counter() - single_start) * 1000)
    results[0, 'notween'] = {'frame_times': [min(single_times)], 'total_ms': None}
    return results


def print_timing_table(results: dict[tuple[int, str], dict[str, object]]) -> None:
    print(
        f'=== timing ({PERF_WIDTH}x{PERF_HEIGHT}, 500-point series, budgets {FRAME_BUDGET_MS} ms/frame, '
        f'{TRANSITION_BUDGET_MS} ms/transition) ==='
    )
    notween = results[0, 'notween']['frame_times'][0]
    print(f'no tween, single redraw: {notween:.2f} ms')
    for (frame_count, ease_name), stats in sorted(results.items()):
        if frame_count == 0:
            continue
        frame_times = stats['frame_times']
        total_ms = stats['total_ms']
        avg = sum(frame_times) / len(frame_times)
        worst = max(frame_times)
        over_frame_budget = 'OVER' if worst > FRAME_BUDGET_MS else 'ok'
        over_total_budget = 'OVER' if total_ms > TRANSITION_BUDGET_MS else 'ok'
        print(
            f'{frame_count:>2} frames, {ease_name:<14} avg {avg:6.2f} ms  worst {worst:6.2f} ms ({over_frame_budget})'
            f'  total {total_ms:7.2f} ms ({over_total_budget})'
        )


class TransitionApp(App[None]):
    CSS = """
    #status { height: 2; padding: 0 1; }
    #chart { padding: 0 1; }
    """
    BINDINGS = [  # noqa: RUF012
        ('1', 'set_frames(5)', '5 frames'),
        ('2', 'set_frames(10)', '10 frames'),
        ('3', 'set_frames(20)', '20 frames'),
        ('t', 'toggle_tween', 'toggle tween'),
        ('e', 'toggle_easing', 'toggle easing'),
        ('space', 'swap', 'swap dataset'),
        ('q', 'quit', 'quit'),
    ]

    def __init__(self, *, auto: bool = False) -> None:
        super().__init__()
        self.auto = auto
        self.frame_count = 10
        self.tween_enabled = True
        self.easing_name = 'linear'
        self.showing_after = False
        self.before, self.after = demo_before(), demo_after()
        self.transition_log: list[tuple[int, bool, str, float, float]] = []

    def compose(self) -> ComposeResult:
        yield Static(id='status')
        yield Static(id='chart')

    def on_mount(self) -> None:
        self._show(full_alpha_points(self.before))
        self._update_status()
        if self.auto:
            self.run_worker(self._auto_run(), exclusive=True)

    def _show(self, points: list[TweenPoint]) -> None:
        _, _, text = render_points(points, DEMO_WIDTH, DEMO_HEIGHT)
        self.query_one('#chart', Static).update(text)

    def _update_status(self) -> None:
        state = 'after' if self.showing_after else 'before'
        tween = f'tween {self.easing_name} x{self.frame_count}' if self.tween_enabled else 'no tween (instant)'
        help_text = '1/2/3 frames  t tween  e ease  space swap  q quit'
        self.query_one('#status', Static).update(f'showing: {state}  |  {tween}  |  {help_text}')

    def action_set_frames(self, count: int) -> None:
        self.frame_count = count
        self._update_status()

    def action_toggle_tween(self) -> None:
        self.tween_enabled = not self.tween_enabled
        self._update_status()

    def action_toggle_easing(self) -> None:
        names = list(EASINGS)
        self.easing_name = names[(names.index(self.easing_name) + 1) % len(names)]
        self._update_status()

    async def action_swap(self) -> None:
        src, dst = (self.after, self.before) if self.showing_after else (self.before, self.after)
        ease_fn = EASINGS[self.easing_name]
        frame_count = self.frame_count if self.tween_enabled else 1
        interval = (TRANSITION_BUDGET_MS / 1000) / frame_count if self.tween_enabled else 0.0
        start = time.perf_counter()
        worst_ms = 0.0
        for i in range(frame_count):
            t = i / (frame_count - 1) if frame_count > 1 else 1.0
            frame_start = time.perf_counter()
            points = interpolate(src, dst, t, ease=ease_fn) if self.tween_enabled else full_alpha_points(dst)
            self._show(points)
            worst_ms = max(worst_ms, (time.perf_counter() - frame_start) * 1000)
            if interval:
                await asyncio.sleep(interval)
        total_ms = (time.perf_counter() - start) * 1000
        self.showing_after = not self.showing_after
        self.transition_log.append((frame_count, self.tween_enabled, self.easing_name, worst_ms, total_ms))
        self._update_status()

    async def _auto_run(self) -> None:
        await asyncio.sleep(1.0)
        for frame_count in FRAME_COUNTS:
            self.frame_count = frame_count
            for tween_enabled in (False, True):
                self.tween_enabled = tween_enabled
                self._update_status()
                await asyncio.sleep(0.4)
                await self.action_swap()
                await asyncio.sleep(0.6)
        self.exit()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--auto', action='store_true', help='play every variant on a timer instead of waiting for keys')
    args = parser.parse_args()

    print('=== spike 3: transitions ===')
    write_representative_frames()
    print_timing_table(measure_timings(repeats=3))

    app = TransitionApp(auto=args.auto)
    app.run()

    if app.transition_log:
        print('\n=== observed swap timings (this run, demo-scale dataset) ===')
        for frame_count, tween, easing, worst_ms, total_ms in app.transition_log:
            label = f'{easing} x{frame_count}' if tween else 'no tween'
            print(f'{label:<20} worst frame {worst_ms:6.2f} ms  total {total_ms:7.2f} ms')


if __name__ == '__main__':
    main()
