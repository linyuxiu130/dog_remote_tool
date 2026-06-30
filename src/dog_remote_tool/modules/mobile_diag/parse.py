from __future__ import annotations

from dog_remote_tool.core.parsers import parse_key_values


def parse_performance_probe_output(text: str) -> dict[str, str]:
    return parse_key_values(text)


def probe_float(value: str | None) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except ValueError:
        return None


def format_probe_percent(value: str | None) -> str:
    if not value or value == "--":
        return "--"
    try:
        return f"{float(value):.1f}%"
    except ValueError:
        return f"{value}%"


def format_probe_temp(value: str | None, mark: bool = False) -> str:
    if not value or value == "--":
        return "--"
    suffix = " !" if mark else ""
    try:
        return f"{float(value):.1f}°C{suffix}"
    except ValueError:
        return f"{value}°C{suffix}"
