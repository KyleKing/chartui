# Spikes

Throwaway experiments for chartui's design, one per numbered question in DESIGN.md's
"Spikes" section. Each writes its rendered frames to `spikes/out/` (gitignored) and its
conclusions to `spikes/FINDINGS-<n>.md`.

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
