# Spikes

Throwaway experiments for chartui's design, one per numbered question in DESIGN.md's
"Spikes" section. Each writes its rendered frames to `spikes/out/` (gitignored) and its
conclusions to `spikes/FINDINGS-<n>.md`.

## Spike 1: canvas look

Run:

```sh
uv run python spikes/spike1_canvas.py
```

Draws the four tail-cw charts (flat line with one spike, two converging series, a
severity histogram, a min-max band with a median) on the bitmap canvas at all six glyph
strategies, plus a linecast float-framebuffer reference for each. Look at:

- the glyph-coverage probe line at the top of every page. If `octant=` shows a box, this
  font has no Unicode 16 coverage and every `*-octant.*` frame is unusable here
- `spikes/out/two-converging-series-{braille,quadrant,linecast}.ansi` for the
  bitmap-versus-float difference: Bresenham staircasing against a Gaussian-blended curve
- `spikes/out/*-braille.ansi` against `*-octant.ansi` for braille's inter-dot gaps
- `spikes/out/min-max-band-with-median-*.txt` for what a background-layer fill leaves
  behind with no color
- the printed timing table against the 16 ms budget

Full writeup: [`spikes/FINDINGS-1.md`](FINDINGS-1.md).

## Spike 2: layout and ticks

Run:

```sh
uv run python spikes/spike2_layout.py
```

Lays out the four tail-cw charts at 40/80/160 columns and ten-minutes/day/quarter time
spans, once with the one-pass frame and once with a fixed-point frame, and prints the
column-cost table comparing them. Look at:

- the printed column-cost table (also saved to `spikes/out/spike2-column-cost.txt`) for
  how many columns the one-pass frame gives up against the fixed-point one
- `spikes/out/*-onepass.txt` and `*-fixedpoint.txt` for the actual frames, especially the
  40-column ones, to judge whether the time-tick ladder reads
- `spikes/out/failure-*.txt` for the narrow-axis, month-boundary, and under-a-minute
  edge cases

Full writeup: [`spikes/FINDINGS-2.md`](FINDINGS-2.md).

## Spike 3: transitions

Run interactively:

```sh
uv run python spikes/spike3_transitions.py
```

Run non-interactively (plays every variant on a timer, for recording):

```sh
uv run python spikes/spike3_transitions.py --auto
```

Keys: `1`/`2`/`3` pick 5/10/20 frames, `t` toggles the tween on/off, `e` toggles linear
vs ease_out_cubic easing, `space` swaps to the other dataset, `q` quits. Look at:

- whether a tweened swap (`t` on, `space`) reads as motion or as a jittery jump,
  compared with an instant swap (`t` off, `space`)
- whether 20 frames looks smoother than 10, or indistinguishable
- whether `ease_out_cubic` (`e`) visibly decelerates into place versus `linear`'s
  constant speed
- the fading columns at the chart's edges (points present in only one dataset): do they
  read as entering/exiting, or just as noise
- the printed timing table (frame and transition times against the 16 ms/200 ms
  budgets) and the "observed swap timings" printed after quitting
- `spikes/out/transition-*.txt`/`.ansi` for static frames, and
  `spikes/out/spike3.gif` (from `spikes/spike3.tape`) for the recorded motion

Full writeup: [`spikes/FINDINGS-3.md`](FINDINGS-3.md).
