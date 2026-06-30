from __future__ import annotations


def parse_key_values(output: str) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw in output.splitlines():
        if "=" not in raw:
            continue
        key, value = raw.split("=", 1)
        values[key.strip()] = value.strip()
    return values


def parse_key_value_fields(text: str, *, separator: str | None = None) -> dict[str, str]:
    values: dict[str, str] = {}
    parts = text.split(separator) if separator is not None else text.split()
    for part in parts:
        if "=" not in part:
            continue
        key, value = part.split("=", 1)
        values[key] = value
    return values
