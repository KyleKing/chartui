"""interpolate(a, b, t): pure tween over two series keyed by x.

A point present in both series tweens its y value. A point present in only one series
gets alpha < 1 instead of a value tween, so the caller fades it via the fill layer
rather than snapping or sliding it in from nowhere.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

Point = tuple[float, float]
EasingFn = Callable[[float], float]


def linear(t: float) -> float:
    return t


def ease_out_cubic(t: float) -> float:
    return 1.0 - (1.0 - t) ** 3


EASINGS: dict[str, EasingFn] = {'linear': linear, 'ease_out_cubic': ease_out_cubic}


@dataclass(frozen=True)
class TweenPoint:
    x: float
    y: float
    alpha: float


def interpolate(a: list[Point], b: list[Point], t: float, ease: EasingFn = linear) -> list[TweenPoint]:
    eased = ease(max(0.0, min(1.0, t)))
    a_map, b_map = dict(a), dict(b)
    points = []
    for x in sorted(a_map.keys() | b_map.keys()):
        in_a, in_b = x in a_map, x in b_map
        if in_a and in_b:
            points.append(TweenPoint(x, a_map[x] + (b_map[x] - a_map[x]) * eased, 1.0))
        elif in_a:
            points.append(TweenPoint(x, a_map[x], 1.0 - eased))
        else:
            points.append(TweenPoint(x, b_map[x], eased))
    return points
