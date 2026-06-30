from __future__ import annotations


def format_byte_size(size: int | float, units: tuple[str, ...] = ("B", "KB", "MB", "GB"), *, precision: int = 1) -> str:
    value = float(size)
    for unit in units:
        if value < 1024 or unit == units[-1]:
            return f"{int(value)} B" if unit == "B" else f"{value:.{precision}f} {unit}"
        value /= 1024
    return "--"
