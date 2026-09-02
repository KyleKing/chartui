"""Deterministic sample datasets for the four tail-cw charts named in spike 1.

Every generator seeds its own random.Random so the output is identical across runs and
across spikes 1, 2, and 3.
"""

from __future__ import annotations

import random
from dataclasses import dataclass


def flat_line_with_spike(n: int = 60, seed: int = 1) -> list[float]:
    rng = random.Random(seed)
    spike_at = n * 2 // 3
    return [100.0 + rng.uniform(-2, 2) + (400.0 if i == spike_at else 0.0) for i in range(n)]


def converging_series(n: int = 60, seed: int = 2) -> tuple[list[float], list[float]]:
    rng = random.Random(seed)
    a, b = [], []
    for i in range(n):
        t = i / (n - 1)
        a.append(80.0 - 50.0 * t + rng.uniform(-1.5, 1.5))
        b.append(20.0 + 50.0 * t + rng.uniform(-1.5, 1.5))
    return a, b


@dataclass(frozen=True)
class SeverityBucket:
    label: str
    count: int
    role: str


def severity_histogram(seed: int = 3) -> list[SeverityBucket]:
    rng = random.Random(seed)
    labels_roles = [
        ('DEBUG', 'muted'),
        ('INFO', 'info'),
        ('WARN', 'warning'),
        ('ERROR', 'error'),
        ('CRITICAL', 'critical'),
    ]
    base_counts = [420, 260, 95, 38, 6]
    return [
        SeverityBucket(label, max(1, count + rng.randint(-5, 5)), role)
        for (label, role), count in zip(labels_roles, base_counts, strict=True)
    ]


@dataclass(frozen=True)
class MinMaxBand:
    minimum: list[float]
    maximum: list[float]
    median: list[float]


def minmax_band_with_median(n: int = 60, seed: int = 4) -> MinMaxBand:
    rng = random.Random(seed)
    minimum, maximum, median = [], [], []
    level = 50.0
    for _ in range(n):
        level += rng.uniform(-3, 3)
        spread = rng.uniform(5, 15)
        minimum.append(level - spread)
        maximum.append(level + spread)
        median.append(level + rng.uniform(-spread * 0.3, spread * 0.3))
    return MinMaxBand(minimum, maximum, median)
