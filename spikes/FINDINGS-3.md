# Spike 3: transitions

`uv run python spikes/spike3_transitions.py` runs a Textual app that swaps between two
sample datasets (a 40-point `flat_line_with_spike` series, offset and shifted) on a
keypress, with and without the `interpolate` tween from `spikes/transition.py`, at 5,
10, and 20 frames. `--auto` plays every combination on a timer instead of waiting for
keys, so it can be recorded and run headless. Representative frames are in
`spikes/out/` as `transition-*.txt` / `.ansi`, and `spikes/out/spike3.gif` is a VHS
recording of the `--auto` run (`spikes/spike3.tape`).

## Why Textual, not rich.live

DESIGN.md's fallback ("an interactive rich.live loop reading single keypresses is an
acceptable substitute") wasn't needed. A Textual `App` with two `Static` widgets, one
async action per keybinding, and `await asyncio.sleep(interval)` between frames inside
the action handler was enough to drive a fixed frame count on a timer, both for
interactive keypresses and for `--auto`. This is the honest test DESIGN.md asks for:
real Textual widgets, real `Static.update()` calls, no fakery.

One divergence from production: DESIGN.md's real widget would use Textual's `Animator`
class to tween a reactive attribute continuously against wall-clock time. `Animator`
doesn't give a way to say "stop me at exactly frame 7 of 10" without hooking its
callback, and the spike's question is specifically about frame *count*, so the spike
drives frames with its own counted loop (`for i in range(frame_count)`) instead. This
is a fair substitute for measuring the count/easing question, not for measuring
`Animator`'s own scheduling overhead, which is unverified here.

## Timing

Measured on the DESIGN.md performance section's shape (120x40, but a single 500-point
series rather than four, since a transition tweens one series's points): `interpolate`
plus canvas build plus `canvas_to_segments` plus `segments_to_plain`, best-of-7 runs,
no `segments_to_ansi` (that's display encoding, not the render-to-Segments budget).

| Frames | Easing | avg/frame | worst/frame | transition total |
| --- | --- | --- | --- | --- |
| 1 (no tween) | - | 23-32 ms | - | - |
| 5 | linear | ~55 ms | ~78 ms | ~275 ms (OVER 200 ms) |
| 5 | ease_out_cubic | ~52 ms | ~83 ms | ~260 ms (OVER 200 ms) |
| 10 | linear | ~56 ms | ~85 ms | ~560 ms (OVER 200 ms) |
| 10 | ease_out_cubic | ~53 ms | ~71 ms | ~535 ms (OVER 200 ms) |
| 20 | linear | ~56 ms | ~73-136 ms | ~1100-1400 ms (OVER 200 ms) |
| 20 | ease_out_cubic | ~54 ms | ~90-145 ms | ~1085-1385 ms (OVER 200 ms) |

Numbers varied run to run on this machine (concurrent agent load), roughly 20-60 ms for
a single redraw across runs. The pattern held in every run: every frame count, at every
easing, blows both the 16 ms/frame and 200 ms/transition budgets, and total time scales
almost exactly linearly with frame count (10 frames costs ~2x 5 frames, 20 costs ~2x
10), because per-frame cost is roughly constant regardless of how much the data moved.

**Spike 1's finding holds.** Spike 1 measured 19-23 ms for a full 120x40 render (four
500-point series) and blamed dict-keyed cell storage (`Canvas._fg`/`_bg`, tuple keys)
plus one `rich.Segment` + `Style` + `Color.from_rgb` allocation per cell in
`canvas_to_segments`, over all 4,800 cells regardless of how sparse the data is. This
spike's single-series baseline (23-32 ms) lands in the same range as spike 1's
four-series number, which confirms the cost is per-cell, not per-series: `interpolate`
itself is cheap (a dict build and a sort over a few hundred points), and the bottleneck
is entirely the existing render pipeline. A real `Canvas`/`Surface` built on flat arrays
and reused `Style` objects (per FINDINGS-1's recommendation) is the fix, and it would
help transitions and full renders equally.

**This changes the answer about frame count.** At today's spike-code render cost, no
frame count fits the 200 ms budget with headroom, and even 5 frames is marginal. The
budget assumes a `Canvas`/`Surface` that hits the 16 ms/frame target; once that's true
(phase 1's flat-array rewrite), 10 frames costs 10 x 16 ms = 160 ms, comfortably under
200 ms, and 20 frames costs 320 ms, over budget. So the frame-count decision is
conditional on the render-cost fix landing first: **10 frames** is the number that fits
the budget once phase 1 ships; this spike cannot recommend a frame count against
today's unoptimized render cost because nothing fits it.

## Does the tween read as motion or as noise

**Unverified — needs a human to watch `spikes/out/spike3.gif` or run the app
interactively.** What to look for:

- At 5 frames, does the line's movement between the two levels look like a jump with
  one halfway stop, or a continuous slide? Compare against the "no tween" swap, which
  should look like a clean instant cut.
- At 20 frames, does the extra frame count buy visibly smoother motion, or is it
  indistinguishable from 10 given how fast terminal repaints happen?
- `ease_out_cubic` should visibly decelerate into the final position; `linear` should
  move at constant speed. Toggle with `e` (or watch the `--auto` cycle, which holds
  frame count fixed and toggles tween on/off, not easing, so the GIF alone won't show
  the linear/ease_out_cubic difference — that's an interactive-only check with `e`).
- Whether the fading columns (the ones present in only one dataset) read as a
  meaningful "entering/exiting" cue or just as visual noise at the chart's edges.

## What happens to points with no match

`interpolate(a, b, t, ease)` keys both series by `x` (a `dict[x, y]` union). A point
present in both series tweens its `y` linearly (or eased) between the two values, with
`alpha=1.0`. A point present in only `a` keeps `a`'s value and gets `alpha = 1 - eased(t)`
(fading out); a point present only in `b` keeps `b`'s value and gets `alpha = eased(t)`
(fading in). `interpolate` itself makes no drawing decision: it's a pure function
returning `TweenPoint(x, y, alpha)`, and the spike script's `build_transition_canvas`
is the caller that decides alpha-1.0 points get connected by a stroke and sub-1.0 points
get a background tint scaled by alpha instead, per DESIGN.md's "fade via the fill
layer" rule for unmatched points. This split (pure tween vs. rendering the alpha) is
what `chartui/transition.py` should keep in phase 3: the library returns points and
alphas, the mark decides how to draw partial alpha.

## Recommendation for DESIGN.md

- Keep `interpolate(a, b, t, ease)` as designed: pure, keyed by x, returning an alpha
  alongside y so the caller can fade unmatched points via the fill layer rather than
  tweening them from/to a fabricated value.
- Ship both `linear` and `ease_out_cubic` (or a similar ease-out curve) as built-in
  easings; which one reads better is a by-eye call, marked unverified above.
- Fix **10 frames**, contingent on phase 1's flat-array `Canvas`/`Surface` rewrite
  landing before phase 3 ships transitions: at spike-code render cost, no frame count
  meets budget, so 10 is a bet on the fix rather than a number this spike proved safe
  today. Add a note to phase 3 (or to the performance benchmarks) that ships as a
  regression test: 10 frames at budget-rate rendering must complete under 200 ms, so a
  render-cost regression is caught before it silently pushes transitions over budget
  again.
- The motion-vs-noise question itself needs a person watching `spikes/out/spike3.gif`
  (or running the app) before DESIGN.md's Transitions section can claim it "reads as
  motion." This spike built the honest instrument; it didn't settle the perceptual
  question, which is not something a script can answer for itself.
