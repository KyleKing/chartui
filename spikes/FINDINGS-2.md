# Spike 2: layout and ticks

`uv run python spikes/spike2_layout.py` lays out the four tail-cw charts (flat line with
one spike, two converging series, a severity histogram, a min-max band with median) at
40, 80, and 160 columns, with x-domains spanning ten minutes, a day, and a quarter, each
twice: once through `layout_one_pass` (DESIGN.md's committed algorithm) and once through
`layout_fixed_point` (iterate the legend/direct-label decision against the width it
actually produces, capped at 5 iterations). All 72 combination frames plus 3 failure-case
frames are in `spikes/out/` as `.txt` (plain) and `.ansi` (with escape codes); the raw
column-cost table is also at `spikes/out/spike2-column-cost.txt`.

`spikes/layout.py` adds `Frame` and the two layout functions. `spikes/scale.py` adds
`time_ticks` and its calendar ladder (1, 5, 15, 30 min; 1, 3, 6, 12 h; 1 day; 1 week; 1
month). `nice_ticks` was left as spike 1 wrote it: it already walks the 1/2/5 progression
and needed no change. No other spike file was touched.

## What "one-pass" and "fixed-point" mean here

Both compute the left gutter identically, from `nice_ticks` over the y-domain: it does
not depend on plot width, so there is nothing to iterate there. The place a real
chicken-and-egg exists is the legend: DESIGN.md reserves a legend column "only when
direct labelling failed," but whether direct labelling fits depends on the final plot
width, which depends on whether a legend was reserved.

- **One-pass** resolves this without ever checking width: any chart with more than one
  named series gets a legend column, unconditionally. This is the literal reading of
  "avoids a fixed-point loop" — the decision needs no scale information at all.
- **Fixed-point** checks a real predicate (`candidate_width - reserve >= 10`) against
  the width its own previous iteration produced, updates the candidate, and repeats
  until the width stops moving (cap 5).

## The column-cost table

| chart | width | span | one-pass | fixed | given up | iterations | ticks (1p/fp) |
| --- | ---: | --- | ---: | ---: | ---: | ---: | --- |
| flat line with one spike | 40/80/160 | all three | equal | equal | **0** | 2 | equal |
| two converging series | 40/80/160 | all three | 1 less | — | **1** | 2 | equal |
| severity histogram | 40/80/160 | all three | equal | equal | **0** | 1 | equal |
| min-max band with median | 40/80/160 | all three | 1 less | — | **1** | 2 | equal |

Full table (36 rows, one per chart x width x span) is in `spikes/out/spike2-column-cost.txt`.

## Does the pessimism ever cost a visible column?

Yes, but by a small and constant margin. Every multi-series chart (two converging
series, min-max band with median) gives up exactly **one column**, at every width from
40 to 160. It is not "a column at narrow widths that disappears once there's room" — the
fixed-point check finds direct labelling fits (`MIN_DATA_WIDTH = 10`) at every width
tested here, so the one-pass legend is unconditionally the wrong call in this whole
matrix; the size of the loss is just the gap between an inline label's reserve (name
length + 1) and an outside legend's reserve (name length + 2). Single-series and
label-free charts (flat line, severity histogram) never pay anything, because the
one-pass rule only fires on series count.

The more interesting result is what this says about the one-pass rule itself: "reserve a
legend for any chart with more than one series" is a cruder heuristic than DESIGN.md's
"only when direct labelling failed" implies, and a *single* width-aware check (`width -
left_gutter - reserve >= MIN_DATA_WIDTH`, computed once, no loop) would have matched the
fixed-point answer in every case tested here, since the direct/legend decision turned out
to be monotonic in width (once the reserve is subtracted, adding a legend only shrinks
the candidate further, so a single evaluation and the converged fixed point agree). That
version needs no iteration and gives up nothing. Whether that shortcut still holds once
labels.py's actual placement pass (retry-shortened labels, real collision detection with
tick marks) enters the picture is unverified here.

## Fixed-point convergence

Every fixed-point case in this matrix converged in 1 or 2 iterations; none hit the cap
of 5. When `reserve == 0` (no series names, or one series), it converges in 1 iteration
because `direct_label` is always `True` regardless of width. When there is a real
legend/inline choice, it took 2: the first iteration checks against a candidate width
with no reservation at all, the second re-checks against the width the first iteration's
decision actually produces, and that is enough to stabilize because the decision is
monotonic (a narrower candidate can only make direct labelling less likely to fit, never
more). Iteration count was not sensitive to width or span in this data. This is itself a
finding: the fixed point is cheap to run when it does run, so DESIGN.md's stated reason
to avoid it (implementation complexity and a philosophical preference for one pass, not
runtime cost) is the real argument, not performance.

## Does the time-tick ladder read?

Unverified by eye (see below), but two things are checkable from the plain-text output:

**The ladder picks reasonable units.** Ten minutes at 160 columns lands on 1-minute
ticks; a day at 160 columns lands on 3-hour ticks; a quarter at any width lands on
1-week ticks; at 40 columns every span collapses to 2-3 ticks total. The
coarsest-form-that-distinguishes-its-neighbour formatting works as designed: within a
day only `HH:MM` shows, crossing a day shows `Mon DD`, crossing a year shows the full
date. Visible directly in `spikes/out/*-onepass.txt`'s bottom row.

**The first tick's label can collide with the second.** This spike's `time_ticks` sizes
`max_ticks` off a flat per-tick label-width estimate (`TICK_LABEL_WIDTH_ESTIMATE = 8`),
but the *first* tick is deliberately formatted fuller (it has no previous tick to
distinguish itself from, e.g. `2026-01-15 09:00` at 16 characters) than every tick after
it (`09:05` at 5 characters). At high tick density the first label's real width exceeds
the per-tick budget the density calculation assumed, and it overwrites the start of the
second tick's label. Reproduced in
`spikes/out/two-converging-series-160col-ten-minutes-onepass.txt` (`09:009:01` on the
axis row) and `.../-a-day-onepass.txt`. This is the case that broke first: dense,
short-format ticks following a long first tick, not the coarse end of the ladder. A real
implementation needs to budget the first tick's width separately from the steady-state
tick width, or run collision detection (labels.py, phase 2) before this ships.

## Failure cases

- **Axis too narrow for any label** (width 8): `time_ticks` returns `[]` cleanly,
  `plot_width` clamps to 0, and `render_frame` degrades to an axis with no ticks rather
  than raising. See `spikes/out/failure-narrow-axis-onepass.txt`.
- **Domain straddling a month boundary** (Jan 20 to Feb 10, 80 columns): ticks land on
  `2026-01-26`, `Feb 02`, `Feb 09` — correct weekly ticks crossing the month cleanly,
  because `_calendar_ticks`' day/week arithmetic uses `timedelta` and never touches
  `_add_month`'s calendar-aware rollover for this span. The `_add_month` path itself
  (used only when the ladder picks whole months) was exercised separately by the
  "a quarter" span across all charts and widths, and also crosses months correctly
  (`Feb 01`, `Mar 01`, `Apr 01` at 40 columns). See
  `spikes/out/failure-month-boundary-onepass.txt`.
- **Domain under a minute** (45 seconds): the finest ladder unit (1 minute) finds no
  minute boundary inside the domain, `_calendar_ticks` returns fewer than 2 ticks, and
  `time_ticks` falls back to labelling the two domain endpoints directly at
  second-level precision (`2026-01-20 12:00`, `12:00:45`). Degrades to exactly 2 ticks
  rather than 0 or a crash. See `spikes/out/failure-under-a-minute-onepass.txt`.

## Unverified / needs a real terminal or a human eye

- **Whether the tick ladder "reads"** in the way a person scanning a real terminal would
  judge it, as opposed to what the plain-text dump can confirm mechanically (unit choice,
  calendar correctness, degradation behavior). Look at `spikes/out/*-onepass.txt` for
  each width/span pair, particularly the 40-column frames, where 2-3 ticks is all the
  ladder allows.
- **Whether the first-tick collision described above is visually confusing** in a real
  terminal versus just visible as garbled text in the plain dump used here. Look at
  `two-converging-series-160col-ten-minutes-onepass.txt`'s bottom row.
- **Whether reserving only one column (the measured pessimism cost) is perceptible** at
  a glance versus only provable by diffing the two frames side by side. Compare
  `two-converging-series-40col-a-day-onepass.txt` against
  `...-fixedpoint.txt` (the fixed-point frame is one column wider and drops the legend
  in favor of inline labels, which are not actually drawn by this spike since
  labels.py doesn't exist yet — the frame only reserves the space).

## Recommendation for DESIGN.md

Keep the one-pass frame, but tighten its legend heuristic: check `width - left_gutter -
reserve >= MIN_DATA_WIDTH` once, using the chart's own width rather than series count
alone, instead of defaulting to "any multi-series chart gets a legend." That single
check matched the fixed point in every case this spike ran, at zero cost and zero
iterations, which is a better fit for DESIGN.md's stated preference for one pass than
the cruder series-count rule this spike used to manufacture a measurable difference.
Separately, budget the first x-tick's label width on its own term in `time_ticks` (it is
always the fullest-format label on the axis), not the same per-tick estimate used for
every tick after it, before this ships past a spike.
