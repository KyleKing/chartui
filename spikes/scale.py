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


MINUTE, HOUR, DAY, WEEK = 60, 3600, 86400, 604800
MONTH_APPROX = 30 * DAY  # only for the ladder's "does it fit" test; ticks still land on calendar month boundaries
TICK_LABEL_WIDTH_ESTIMATE = 8
MIN_LADDER_TICKS = 2

_LADDER: tuple[tuple[str, int], ...] = (
    ('1min', MINUTE),
    ('5min', 5 * MINUTE),
    ('15min', 15 * MINUTE),
    ('30min', 30 * MINUTE),
    ('1h', HOUR),
    ('3h', 3 * HOUR),
    ('6h', 6 * HOUR),
    ('12h', 12 * HOUR),
    ('1day', DAY),
    ('1week', WEEK),
    ('1month', MONTH_APPROX),
)


def _floor_minutes(t: dt.datetime, step: int) -> dt.datetime:
    return t.replace(minute=(t.minute // step) * step, second=0, microsecond=0)


def _floor_hours(t: dt.datetime, step: int) -> dt.datetime:
    return t.replace(hour=(t.hour // step) * step, minute=0, second=0, microsecond=0)


def _floor_day(t: dt.datetime) -> dt.datetime:
    return t.replace(hour=0, minute=0, second=0, microsecond=0)


def _floor_week(t: dt.datetime) -> dt.datetime:
    day0 = _floor_day(t)
    return day0 - dt.timedelta(days=day0.weekday())


def _floor_month(t: dt.datetime) -> dt.datetime:
    return t.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


def _add_month(t: dt.datetime, months: int = 1) -> dt.datetime:
    total = t.month - 1 + months
    return t.replace(year=t.year + total // 12, month=total % 12 + 1)


def _calendar_ticks(start: dt.datetime, end: dt.datetime, unit: str) -> list[dt.datetime]:
    if unit.endswith('min'):
        step_n = int(unit.removesuffix('min'))
        cur = _floor_minutes(start, step_n)
        step = dt.timedelta(minutes=step_n)
    elif unit in {'1h', '3h', '6h', '12h'}:
        step_n = int(unit.removesuffix('h'))
        cur = _floor_hours(start, step_n)
        step = dt.timedelta(hours=step_n)
    elif unit == '1day':
        cur, step = _floor_day(start), dt.timedelta(days=1)
    elif unit == '1week':
        cur, step = _floor_week(start), dt.timedelta(weeks=1)
    else:
        cur, step = _floor_month(start), None
    if cur < start:
        cur = _add_month(cur, 1) if step is None else cur + step
    ticks = []
    while cur <= end:
        ticks.append(cur)
        cur = _add_month(cur, 1) if step is None else cur + step
    return ticks


def _format_tick(tick: dt.datetime, prev: dt.datetime | None) -> str:
    if prev is None:
        if tick.second or tick.microsecond:
            return tick.strftime('%Y-%m-%d %H:%M:%S')
        return tick.strftime('%Y-%m-%d %H:%M' if tick.hour or tick.minute else '%Y-%m-%d')
    if tick.year != prev.year:
        return tick.strftime('%Y-%m-%d')
    if (tick.month, tick.day) != (prev.month, prev.day):
        return tick.strftime('%b %d')
    if (tick.hour, tick.minute) != (prev.hour, prev.minute):
        return tick.strftime('%H:%M')
    return tick.strftime('%H:%M:%S')


def time_ticks(
    domain: tuple[dt.datetime, dt.datetime], plot_width: int, label_width: int = TICK_LABEL_WIDTH_ESTIMATE
) -> list[tuple[dt.datetime, str]]:
    """Pick the coarsest ladder unit whose tick count fits plot_width, then format each tick against its neighbour."""
    start, end = domain
    span = (end - start).total_seconds()
    if span <= 0:
        return []
    max_ticks = plot_width // (label_width + 1)
    if max_ticks <= 0:
        return []
    chosen = _LADDER[-1][0]
    for unit, seconds in _LADDER:
        if span / seconds <= max_ticks:
            chosen = unit
            break
    ticks_dt = _calendar_ticks(start, end, chosen)
    if len(ticks_dt) < MIN_LADDER_TICKS:
        ticks_dt = [start, end]
    if len(ticks_dt) > max_ticks:
        stride = math.ceil(len(ticks_dt) / max_ticks)
        ticks_dt = ticks_dt[::stride]
    labeled = []
    prev = None
    for tick in ticks_dt:
        labeled.append((tick, _format_tick(tick, prev)))
        prev = tick
    return labeled
