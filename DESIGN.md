# chartui

A terminal charting library for Rich and Textual apps, built for
[tail-cw](https://github.com/kyleking/tail-cw) first and for extract_finances once it has
screens that need charts.

Status: design. Nothing is built yet. Three spikes come before the first real module.

## The problem

tail-cw draws CloudWatch metrics: compact sparkline cells in a dashboard grid, a focused
chart per widget, a severity-coloured log-volume histogram, and a trace waterfall. It
uses [plotext](https://github.com/piccolomo/plotext) through
[textual-plotext](https://github.com/Textualize/textual-plotext) for the focused chart
and hand-written Rich block characters for everything else.

plotext gives breadth (scatter, line, bar, histogram, candlestick, heatmap, confusion
matrix, box, pie, subplots) and almost nothing else. It has no theme integration, so a
chart is whatever palette plotext was told about and it does not follow a Textual theme
switch. It draws the legend inside the plot area over the data. Its tick placement
divides the range into a fixed count rather than choosing round numbers. Its braille is
monochrome per cell, so a curve cannot be inked by the value beneath it. It has no
concept of a label that would collide with something already drawn, and no cursor.

None of that is a plotext defect. It is a plotting library, and these are presentation
concerns that belong to whatever is composing the screen. Today tail-cw solves them in
each widget, badly, and only for the one chart in front of it.

extract_finances draws nothing today. Its
[revisit plan](../extract_finances/plans/revisit-2026-09-01.md) defers every chart to
this library, so it is a second consumer in intent and not yet in code. Its chart types
below are candidates, and none ships until a screen in that app needs it.

## What good looks like

[linecast](https://github.com/ashuttl/linecast) is the reference for visual quality. It
is a weather CLI, so none of its domain code transfers. What makes it look better than
anything tail-cw draws today is that it spends all three channels a terminal cell offers
instead of one:

- the background colour carries the fill, one value per cell
- the glyph is shape, at 2x4 the resolution of the cell, and carries the stroke
- the foreground colour inks that glyph, and can be keyed to the value under it

plotext spends the glyph channel and stops. Two of linecast's ideas transfer directly.
`_theme.py` walks a colour toward a pole until it clears a contrast floor against the
actual background, using 2.0 for chart ink rather than the 4.5 WCAG text floor.
`_color.py` degrades truecolour to xterm-256 and to ANSI-16 while refusing to let a muted
colour gain saturation on the way down, and honours `NO_COLOR`. Both are under a hundred
lines and get rewritten here with attribution (MIT, © 2025 Andrew Shuttleworth).

linecast's float framebuffer, with alpha blending and Gaussian-antialiased curves, does
not transfer. tail-cw's own
[graph-rendering plan](../tail-cw/plans/graph-rendering-2026-09-01.md) reached the same
conclusion: Textual already composites, and a float raster in pure Python is the wrong
cost for a widget that repaints on every cursor move. The canvas here is a bitmap, and
the spike below decides whether that loses anything visible.

## Prior art and what each one settles

[ratatui](https://ratatui.rs/) (Rust) is the architectural reference. Its `Canvas`
widget separates the drawing surface from the pixel-packing strategy, exposed as a
`Marker`: `Dot`, `Block`, `Bar`, `Braille`, and since Unicode 16, `Octant`. The same
drawing code renders at four resolutions, and the caller picks based on what the
terminal can show. [ratatui-plt](https://lib.rs/crates/ratatui-plt) builds 58 plot types
on that one surface, which is the proof that the split is the right one. Its crosshair
is a mouse-position overlay with a coordinate readout, not a data cursor.

[textual-plot](https://davidfokkema.github.io/textual-plot/) is the closest Python
neighbour. It offers `BRAILLE`, `QUADRANT`, `HALFBLOCK`, and full-block hi-res modes,
mouse zoom and pan, tick placement at round 1/2/5 intervals, and pluggable axis
formatters. It posts a `ScaleChanged` message and has no way to read the value under
the cursor. It is narrower than plotext by design (line, scatter, errorbar, bar) and
better engineered for the parts it covers. If it grows theming, label placement, and a
cursor, most of the case for chartui goes away, so watch it.

Octants (U+1CD00–U+1CDE5, Unicode 16.0) give the same 2x4 subdivision as braille with no
inter-dot gaps, so a fill reads as solid rather than as dots, and the
[proposal](https://www.unicode.org/charts/PDF/Unicode-16.0/U160-1CC00.pdf) exists
specifically to replace braille for terminal graphics. Font support is the catch:
Cascadia Code shipped them in
[2404.23](https://devblogs.microsoft.com/commandline/cascadia-code-2404-23/), and other
fonts and terminals are still catching up
([wezterm #6494](https://github.com/wezterm/wezterm/issues/6494)). This is a reason for
the glyph strategy to be swappable, not a reason to skip octants.

On labelling, the visualization literature is one-sided. Direct labelling beats a legend
whenever it fits, because a legend makes the reader look away from the data and match
colours back
([Practical Reporting](https://www.practicalreporting.com/blog/2024/9/17/avoid-legends-footnotes-and-other-forms-of-indirect-labeling-in-your-charts-whenever-possible),
[PolicyViz](https://policyviz.com/2024/01/11/graph-labeling-strategies/)). The standard
placement is at the right end of each line. The named caveat is that direct labels get
messy when series converge, which is exactly the case the placement pass has to handle.

For the placement algorithm itself, the
[Vega-Lite label layout paper](https://arxiv.org/html/2405.10953) is the one to copy. It
keeps an occupancy bitmap of everything already drawn, generates candidate positions per
label in preference order, takes the first candidate whose bounding box hits no set bits,
and ORs the placed label back into the bitmap. Greedy, deterministic, linear in label
count, and 22% faster than force-based methods on 3,320 points. Simulated annealing
places more labels and is far too slow for a widget that re-renders on resize.

Nobody has published a keyboard data cursor for a terminal chart in Python. That part is
designed from scratch below.

## Architecture

Six stages, each a pure function of the one before it. This is the grammar-of-graphics
split ([Wickham's layered grammar](http://vita.had.co.nz/papers/layered-grammar.pdf))
with the pieces a terminal cannot use (facets, most stats, non-Cartesian coords) left
out.

```
Series      what to draw            list[float] | list[(x, y)] | list[Span]
  |
Scale       domain -> unit          LinearScale, TimeScale, LogScale, BandScale
  |                                 nice_ticks, time_ticks, fitted_ylim, resample
Layout      size -> frame           gutters for ticks, title, legend; the plot rect
  |
Mark        unit -> primitives      LineMark, AreaMark, BarMark, HeatMark, SpanMark
  |
Canvas      primitives -> bits      sub-cell bitmap, one colour per cell, fill layer
  |
Surface     bits -> cells           char + fg + bg grid, occupancy bitmap, datum map
  |
Backend     cells -> output         rich.Segment
```

Three extension points, and nothing else needs to be one.

**`Mark` is the protocol for a chart type.** It receives scaled data and a `Canvas` and
draws primitives. A new chart is a new `Mark` with no core change, which is the single
lesson worth taking from ggplot2's extension story. `Mark` declares its label requests
(series name, extrema, annotations, cursor readout) rather than drawing text itself, so
everything competing for space goes through one placement pass. It also declares which
glyph family it wants by default: braille for strokes (line, scatter), blocks for fills
(area, bar, heat, span).

**`Glyphs` is the protocol for pixel packing.** It declares its sub-cell resolution and
turns a bit block into a character.

| Glyphs | Sub-cells | Note |
| --- | --- | --- |
| `BLOCK` | 1x1 | works everywhere, including a pipe |
| `HALFBLOCK` | 1x2 | `▄` with fg and bg, two colours per cell |
| `QUADRANT` | 2x2 | widest support above half-block |
| `SEXTANT` | 2x3 | Unicode 13, good support |
| `OCTANT` | 2x4 | Unicode 16, best resolution, newest fonts |
| `BRAILLE` | 2x4 | 2x4 with visible gaps, universal support |

Selection: an explicit config override wins for every mark, else each mark's declared
default, else `BLOCK`. Octants replace both braille and blocks when the caller opts in.
Terminal probing is phase 4.

**`Palette` is the protocol for colour.** The library owns the mechanism (a role resolves
to a theme variable, and the result is walked to clear a contrast floor against the real
background) and the app owns the vocabulary. tail-cw's roles are errors, latency,
traffic, saturation, and availability. Neither the roles nor the keyword inference
belong here. The background is an explicit argument. Textual passes its theme
background, and the Rich adapter defaults to dark and documents that a light-terminal
CLI must pass its own.

### The canvas is a bitmap

`Canvas` holds one bit per sub-pixel, one foreground colour per cell, and a separate
fill layer of one background colour per cell. No alpha, no antialiasing. A line is
Bresenham into bits, a fill is a rect into the background layer, and a value-keyed
stroke sets the cell colour from the mean of the values that lit it. This is ratatui's
model, and it keeps a 120x40 render at 2x4 packing to one pass over 76,800 bits in pure
Python.

The cost is the linecast look: no gradient fills, no glow, no translucent overlap
between series. Whether any tail-cw chart misses those is what the first spike answers.

### Layout

The frame is decided before any mark draws, in one pass. Tick labels are formatted at
the scale's full domain, the widest y label sets the left gutter, one row goes to the x
axis, one to the title, and the legend (only when direct labelling failed) takes a
column on the right. The plot rect is what remains. This is slightly pessimistic (a
gutter sized for a label that placement later shortens) and avoids a fixed-point loop
between scale and layout. The second spike measures whether that pessimism ever costs a
visible column.

Time ticks are modelled from the start, because every tail-cw x axis is time. `nice_ticks`
handles numbers with the 1/2/5 progression. `time_ticks` picks from a ladder of
calendar units (1, 5, 15, 30 min; 1, 3, 6, 12 h; 1 day; 1 week; 1 month) and formats
each tick at the coarsest form that distinguishes it from its neighbour. Neither emits
more ticks than the axis has room for.

### Labels, legends, and overlap

In a browser the occupancy bitmap has to be rasterized as a separate pass. In a terminal
the cell grid *is* the bitmap, at a few thousand cells, so exact collision detection is
free. That is the one place a TUI chart library has it easier than a web one.

Placement runs once, after all marks have drawn, over requests sorted by priority:

1. axis tick labels, which set the frame and are placed first
2. the cursor readout, when a cursor is set
3. direct series labels at the right end of each line, then above-right, then
   below-right
4. extrema callouts (peak and trough values)
5. annotations (thresholds, events, today)

Each request carries text, an anchor cell, a candidate ordering, and a minimum
acceptable form. A request that cannot be placed at full length is retried shortened
(with the cut marked, never silently clipped), and only then dropped. A label never
covers a mark. The occupancy bitmap includes every drawn cell, so a dense chart loses
its direct labels and the outside legend carries the names. The pass returns
placements, so it is a pure function testable by asserting no two placements share a
cell.

The legend goes outside the plot area. plotext drawing its legend over the data is a
defect worth not repeating.

### Cursor

The cursor is one x index into the data, and nothing else. The app is stateless about
it: the widget holds the index and passes it to the chart on each render.

- `h` and `l` move one point, and a count prefix jumps that many (`5l`), vim-style
- `H` and `L` jump to the trough and peak of the emphasised series, `0` and `$` to the
  ends
- `j` and `k` change which series the readout emphasises when there are several
- a mouse click or hover sets the same index from the column under the pointer

Rendering a cursor draws a vertical rule at the cursor column and, for each series, the
point nearest that x. The readout is one label request per series (or one for the
emphasised series when space is short) so the placement pass keeps it clear of ticks
and other labels. `Surface` keeps a datum map (cell to series index and point index) so
the widget can turn a mouse position into an index without re-scaling.

No zoom and no pan. If a chart needs a narrower window the app filters its data and
renders again.

### Transitions

The app is stateless, so a filter change (a date range, a category, a log query) arrives
as a whole new dataset. The widget keeps the series it last drew, and on new data it
tweens each point with a matching x toward its new value over a few frames using
Textual's animator, then forgets the old series. Points with no match fade in or out
via the fill layer. The library's part is one pure function, `interpolate(a, b, t)`,
over two series keyed by x.

Ten frames in under 200 ms is the budget, which is another reason the canvas is a
bitmap. The third spike decides whether the tween reads as motion or as noise at
terminal frame rates.

## Chart types

tail-cw, in phase order:

- sparkline, the one-row compact cell, with column aggregation rather than
  point-sampling
- line and area, single and multi-series, with an optional value-keyed stroke
- histogram, with a per-bucket category colour (severity)
- span, for the trace waterfall. The waterfall stays a table in tail-cw, and chartui
  draws the bar column: a `SpanMark` over a `TimeScale` shared by every row, so the
  bars align and the cursor rule crosses all of them
- bar: vertical and horizontal

extract_finances, candidates until a screen needs them:

- calendar heatmap of daily spend, the chart no terminal library does well
- diverging bars around a zero axis, stacked and grouped bars
- scatter, matrix heatmap, ridgeline or small multiples

Explicitly not shipping: pie and donut, because a terminal renders arcs badly and a
stacked proportion bar says the same thing in one row. Candlestick, box plots, confusion
matrices, and 3D, because plotext already has them and chartui should not compete on
breadth. An app that needs one of those keeps calling plotext.

## Performance

Every design choice here defaults to the faster option and names what it gives up. The
budgets, measured on a 120x40 focused chart with four series of 500 points:

| Operation | Budget |
| --- | --- |
| full render, data to Segments | 16 ms |
| cursor move (relabel and repaint) | 4 ms |
| one transition frame | 16 ms |

The canvas is a bitmap rather than a float raster to hit these. Layout is one pass
rather than a fixed point. The Textual widget uses the line API (`render_line`) rather
than a Rich renderable so a cursor move repaints one column band. Scales cache their
tick lists per domain and width. Anything slower than budget gets profiled before a
numpy accelerator is considered, and numpy stays optional if it ever arrives.

## Spikes

Three throwaway experiments before phase 1, each a script under `spikes/` that prints
sample charts to a real terminal. They exist to settle a question by looking, and they
get deleted once the answer is in this document.

1. **Canvas look.** The same four tail-cw charts (a flat line with one spike, two
   converging series, a severity histogram, a min-max band with a median) drawn with a
   bitmap canvas and with a float raster, at braille, quadrant, and octant packing.
   Decides whether the bitmap loses anything a reader would notice, and which glyph
   defaults hold up.
2. **Layout and ticks.** The one-pass frame against a fixed-point frame on the same
   charts at 40, 80, and 160 columns, with time axes spanning ten minutes, a day, and a
   quarter. Decides whether the pessimistic gutter costs a column and whether the tick
   ladder reads.
3. **Transitions.** A widget that swaps between two datasets on a keypress, with and
   without the tween, at 5, 10, and 20 frames. Decides whether motion helps in a
   terminal and what frame count to fix.

## Package layout

```
chartui/
  __init__.py    version only. No re-exports: a facade would load every module for one import
  color.py       RGB, hex, luminance, contrast_ratio, ensure_contrast, lerp, interp_stops,
                 truecolor -> 256 -> 16 downgrade, NO_COLOR
  scale.py       LinearScale, TimeScale, LogScale, BandScale, nice_ticks, time_ticks,
                 fitted_ylim, resample(values, width, aggregate)
  layout.py      Frame: gutters, plot rect, legend column
  glyphs.py      Glyphs protocol, the six implementations, capability detection
  canvas.py      Canvas: set_bit, line, rect, fill layer, per-cell colour
  surface.py     Surface: char/fg/bg grid, occupancy bitmap, datum map, composite
  labels.py      LabelRequest, place_labels(surface, requests) -> list[Placement]
  legend.py      direct labelling, fallback legend layout
  cursor.py      nearest_index, cursor rule, readout requests
  transition.py  interpolate(a, b, t)
  theme.py       Palette protocol, role resolution, contrast floor
  marks/         line.py area.py bar.py spark.py hist.py span.py heat.py scatter.py
  chart.py       assembly: Chart(size, scales, marks, cursor) -> Surface
  rich_.py       Rich renderable
  textual_.py    Textual widget, line API, behind the [textual] extra
```

Dependencies: stdlib only for everything above `rich_`. `rich` for the Rich adapter,
which both apps already have. `textual` as an extra. No numpy: the data volumes are
terminal-sized and a hard numpy dependency would cost more than it buys. No plain-ANSI
backend: there is no consumer without Rich.

Python floor: 3.13, matching both apps.

Both apps consume it by path until the API stops moving:

```toml
chartui = { path = "../chartui", editable = true }
```

then by version from PyPI once it settles, the same shape as
[corallium](https://github.com/kyleking/corallium). The name `chartui` is free on PyPI.

## Testing

Every stage is a pure function, which is the whole reason for the split.

- scales: property tests on the invariants (a domain endpoint maps to a unit endpoint,
  `nice_ticks` and `time_ticks` return ticks inside the domain and no more than fit,
  resampling preserves the extremes)
- glyphs: exhaustive round-trip over every bit pattern for each strategy
- canvas and marks: golden text snapshots through
  [syrupy](https://github.com/syrupy-project/syrupy), already in the ecosystem
- labels: assert no two placements share a cell, no placement covers a mark, and that
  priority order is respected when space runs out
- cursor: nearest index is stable under resampling, and the readout is placed before
  series labels
- colour: assert the contrast floor is met against real light and dark theme
  backgrounds, and that the 256 and 16 downgrades never increase saturation
- performance: the three budgets above as benchmarks that fail the build when exceeded
  by half again

Colour is the one thing snapshots cannot settle. A VHS capture of tail-cw under
`NO_COLOR` rendered a faulted row as a blank line while the same view in tmux showed it
correctly, so anything colour-dependent gets confirmed in a real terminal.

## Phases

**Spikes.** The three above, in order. Each ends by editing this document.

**Phase 1, primitives.** `color`, `scale` (including `time_ticks`), `layout`, `glyphs`,
`surface`, and the block sparkline. Port `ensure_contrast`, `resample`, `fitted_ylim`,
and the role mechanism out of `tail_cw/charts/`. tail-cw switches to it with no visible
change, which is the proof the extraction is faithful.

**Phase 2, the canvas and the core marks.** `canvas`, `labels`, `legend`, `cursor`, and
line, area, and histogram. tail-cw's focused chart moves off plotext and gains the
cursor.

**Phase 3, spans and transitions.** `SpanMark` for the waterfall bar column,
`transition`, and bar. tail-cw's waterfall and log histogram move over. extract_finances
draws its first chart if it has a screen by then.

**Phase 4, polish and publish.** Octant support, terminal capability probing, docs, and
0.1.0 to PyPI.

Phase 1 is worth doing even if the rest never happens, because it deletes duplicated
maths from tail-cw. Phase 2 is where the visual quality and the cursor arrive.

## Open questions

- The waterfall's tree column, service column, and row selection stay in tail-cw. Is a
  shared `TimeScale` plus a per-row `SpanMark` enough of a contract, or does the cursor
  rule crossing every row need chartui to own the whole row set?
- With several series at different x sampling, the readout shows the nearest point per
  series. Should the rule snap to the emphasised series' x, or stay at the pointer
  column?
- How much of linecast to vendor with attribution versus rewrite. `_braille.py` has
  zero imports and could be vendored nearly verbatim. `_color.py` and `_theme.py` are
  short enough to rewrite.
- extract_finances' first screen decides which candidate chart comes first. Revisit
  once its skeleton has a view that wants one.
