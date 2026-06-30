from __future__ import annotations

import re


ANSI_PATTERN = re.compile(
    r"\x1B\][^\x07\x1b]*(?:\x07|\x1B\\)|"
    r"\x1B\[[0-?]*[ -/]*[@-~]|"
    r"\x1B[()][A-Za-z0-9]|"
    r"\x1B(?:[=>78]|c)|"
    r"␛\[[0-9;]*[A-Za-z]"
)
CONTROL_PATTERN = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def strip_ansi(text: str) -> str:
    return ANSI_PATTERN.sub("", text)


def strip_control_chars(text: str) -> str:
    return CONTROL_PATTERN.sub("", text)


def compact_lines(text: str, limit: int = 240) -> str:
    compact = text.strip().replace("\n", "；")
    return compact[:limit] + "..." if len(compact) > limit else compact


def last_nonempty_line(text: str) -> str:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    return lines[-1] if lines else ""
