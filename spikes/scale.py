"""Minimal LinearScale/TimeScale and nice_ticks, only as much as the spikes need."""

from __future__ import annotations

import datetime as dt
import math
from dataclasses import dataclass


@dataclass
class LinearScale:
    domain: tuple[float, float]
    unit_range: tuple[float, float] = (0.0, 1.0)

    def __call__(self, value: float) -> float:
        d0, d1 = self.domain
        u0, u1 = self.unit_range
        if d1 == d0:
            return u0
        return u0 + (value - d0) / (d1 - d0) * (u1 - u0)


@dataclass
class TimeScale:
    domain: tuple[dt.datetime, dt.datetime]
    unit_range: tuple[float, float] = (0.0, 1.0)

    def __call__(self, value: dt.datetime) -> float:
        d0, d1 = self.domain
        u0, u1 = self.unit_range
        span = (d1 - d0).total_seconds()
        if span == 0:
            return u0
        return u0 + (value - d0).total_seconds() / span * (u1 - u0)


def nice_ticks(lo: float, hi: float, count: int = 5) -> list[float]:
    if lo == hi:
        return [lo]
    span = hi - lo
    raw_step = span / max(1, count)
    magnitude = 10 ** math.floor(math.log10(raw_step))
    for step in (1, 2, 5, 10):
        candidate = step * magnitude
        if candidate >= raw_step:
            nice_step = candidate
            break
    else:
        nice_step = 10 * magnitude
    start = math.floor(lo / nice_step) * nice_step
    ticks = []
    tick = start
    while tick <= hi + nice_step * 1e-9:
        if tick >= lo - nice_step * 1e-9:
            ticks.append(round(tick, 10))
        tick += nice_step
    return ticks
