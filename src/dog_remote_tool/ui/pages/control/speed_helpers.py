from __future__ import annotations


def stepped_slider_value(value: int, delta: int, step: int, minimum: int, maximum: int) -> int:
    next_value = value + delta
    next_value = round(next_value / step) * step
    return max(minimum, min(maximum, next_value))
