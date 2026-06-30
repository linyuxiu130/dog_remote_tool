from __future__ import annotations


def format_seconds(value: float | int | None, *, none_text: str = "-", always_hours: bool = True, rounded: bool = False) -> str:
    if value is None:
        return none_text
    total = max(0, int(round(value) if rounded else value))
    hours, remainder = divmod(total, 3600)
    minutes, seconds = divmod(remainder, 60)
    if always_hours or hours:
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}" if always_hours else f"{hours}:{minutes:02d}:{seconds:02d}"
    return f"{minutes:02d}:{seconds:02d}"
