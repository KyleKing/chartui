# Spike 1: canvas look

`uv run python spikes/spike1_canvas.py` renders the four charts DESIGN.md names (flat
line with one spike, two converging series, a severity histogram, a min-max band with
median) at BLOCK, HALFBLOCK, QUADRANT, SEXTANT, OCTANT, and BRAILLE packing on the
bitmap `Canvas` in `spikes/canvas.py`, plus a linecast float-framebuffer reference for
each chart. Every page opens with a glyph-coverage probe line. All 28 frames (4 charts
x 7 renderers) are in `spikes/out/` as `.txt` (plain) and `.ansi` (with escape codes),
so they can be read with `cat` without rerunning.

## linecast as a reference

`linecast._framebuffer.Framebuffer`, `_color`, and `_theme` import and run standalone
with no network or app context. `_braille.py` was not needed for this spike (it builds
its own line-graph-specific bit layout, not a general Glyphs strategy). The float
framebuffer, `draw_curve` (Gaussian antialiasing), and `draw_fill` (gradient fills) all
worked directly.

## What the bitmap canvas loses

**Antialiased position, on the two converging series chart.** Compare
`two-converging-series-quadrant.txt` and `two-converging-series-linecast.txt`. Our
Bresenham line snaps to the nearest sub-pixel row and reads as a thin, slightly
staircased curve. linecast's `draw_curve` blends every sub-pixel within about 3 rows of
the true y-position by a Gaussian-falloff alpha, so the line can visually sit *between*
two sub-pixel rows. In real color this reads as a smooth curve with a soft edge; in the
plain-text dump it reads as a much thicker band, because even a faint 2% alpha blend is
enough to make a cell's two sub-pixel colors differ and trigger a half-block character.
Neither reading is wrong, they're different tradeoffs: crisp-but-stepped versus
smooth-but-fuzzed.

**Area fills carry zero information without color.** `min-max-band-with-median-*.txt`
for every glyph strategy shows almost nothing but the jagged median line. The band
itself is a `Canvas.rect(fill=...)` into the background layer only, per DESIGN.md's
model, so it never touches a bit. That's correct behavior for the bitmap canvas, and
it's also the honest answer to what a `NO_COLOR` terminal shows: a min-max band chart
degrades to just its median line. linecast's float framebuffer has the identical
problem for the same reason (background-layer fill, no bits): `min-max-band-with
-median-linecast.txt` is just as empty. This isn't a bitmap-vs-float difference, it's
inherent to any background-color fill, and worth flagging for phase 2's `AreaMark`: a
fill needs a secondary encoding (a border stroke, a light dither, or an outline glyph)
if it has to survive `NO_COLOR`.

**No translucent overlap.** Not exercised by these four datasets (none of them overlap
two fills), so this spike doesn't have direct evidence either way. Flagged as the one
DESIGN.md-named cost this spike did not test; the second and third spikes' charts don't
test it either, so it stays an open question for phase 2's multi-series area chart.

## Which glyph default holds up

**Strokes (line, the value-keyed spike line):** BRAILLE and OCTANT both render the
line legibly at 2x4 resolution. The value-keyed stroke works end to end: the flat
line's fg color measurably shifts from `(100,199,253)` at baseline toward
`(177,144,172)` near the spike in `flat-line-with-one-spike-quadrant.ansi`, confirming
`Canvas.resolve_value_colors` colors by the mean value under each cell as designed.
SEXTANT (2x3) is visibly coarser vertically than BRAILLE/OCTANT/QUADRANT at the same
cell height, which shows on the spike's near-vertical rise. BLOCK and HALFBLOCK are too
coarse for a 10-cell-tall line chart to read as a curve at all; DESIGN.md's fallback
order (declared default, else BLOCK) is right to treat BLOCK as a last resort, not a
stroke default.

**Fills (the severity histogram bars):** QUADRANT, SEXTANT, and OCTANT all render solid
bars cleanly when the bar also sets bits (`Canvas.rect(fill=..., solid=...)`), because a
bar chart needs to survive `NO_COLOR`, unlike a translucent area fill. OCTANT's bar
edges are marginally cleaner than QUADRANT's at the same width because the finer
vertical grid rounds the bar height with less error, but the difference is a couple of
sub-pixels and would not be visible at typical dashboard cell heights.

**Braille's visible gaps** (DESIGN.md's "2x4 with visible gaps"): not something a
plain-text or headless-ANSI check can confirm; a braille cell's dot spacing is baked
into the font glyph, not the canvas. Flagged as unverified below.

## Unverified / needs a real terminal

- **Octant rendering in WezTerm.** This is exactly the risk DESIGN.md calls out. The
  probe line's `octant=` character (and the exotic corner-octant characters that appear
  in the flat-line and band frames) will be tofu (a missing-glyph box) on any font
  without Unicode 16 Symbols for Legacy Computing Supplement coverage. Check the probe
  line first: if the octant glyph shows a box, none of the OCTANT frames in
  `spikes/out/` will render correctly and QUADRANT is the practical ceiling in that
  terminal today.
- **Braille's inter-dot gap versus octant's gapless fill**, the visual difference
  DESIGN.md predicts octants exist to fix. Only visible by eye, side by side, in a real
  terminal at a realistic cell size.
- **Color fidelity and the value-keyed gradient's contrast** against the user's actual
  background. This spike used a fixed dark-terminal default `(220,220,220)` foreground
  and did not implement `_theme.py`'s contrast-floor walk (out of scope for spike 1 per
  DESIGN.md's phase plan); the gradient exists and moves as intended, but its
  readability against a specific theme is unverified.
- **Truecolor-to-256/16 downgrade.** Every `.ansi` file here was captured with
  `color_system='truecolor'` forced. A terminal running at 256 or 16 colors will look
  different; this spike didn't exercise `_color.py`'s downgrade path.

## Performance against the DESIGN.md budget

Full render (`Canvas` build with 4 series of 500 points, line-drawing, to Segments, to
plain string) at 120x40, matching DESIGN.md's benchmark shape:

| Glyphs | best of 5 runs |
| --- | --- |
| BLOCK | 20.0 ms |
| HALFBLOCK | 19.2 ms |
| QUADRANT | 21.8 ms |
| SEXTANT | 21.3 ms |
| OCTANT | 22.6 ms |
| BRAILLE | 23.1 ms |

Budget is 16 ms. Every strategy overshoots by roughly 1.2-1.4x, and the overshoot is
close to uniform across glyph choices, which says the cost here is not glyph-specific
packing (`to_char` is O(1) table lookups everywhere) but the spike's per-bit dict
lookups in `Canvas` (`_fg`, `_bg`, `_value_sum` keyed by `(cx, cy)` tuples) and
constructing a `rich.Segment` + `Style` + `Color.from_rgb` object per cell in
`canvas_to_segments`. Neither is how phase 1 would build this: a real `Canvas` should
back bits and per-cell color with flat arrays indexed by `cy * width + cx`, and a real
`Surface` should reuse `Style` objects for repeated colors rather than allocating one
per cell. This spike's numbers are a ceiling, not a verdict on the bitmap model itself.

## Recommendation

The bitmap canvas is the right default for phase 2. Its two real costs against
linecast's float raster, sub-pixel-precise antialiasing on strokes and translucent
overlap, are both plausible-but-unproven for tail-cw's actual charts: none of the four
sample datasets needed overlapping fills, and the antialiasing difference reads as
"smoother" rather than "necessary" even in the linecast reference frames captured here.
Ship BRAILLE as the stroke default and QUADRANT as the fill default, per DESIGN.md's
existing table, with OCTANT as an opt-in upgrade for both once terminal probing (phase
4) can detect font support; the probe line here is the seed for that detector. Budget
work (flat arrays over dicts, cached `Style` objects) is real but separable from the
canvas-vs-float decision and belongs to phase 1's `canvas.py`, not this spike.
