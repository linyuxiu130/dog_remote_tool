from __future__ import annotations

import re
from pathlib import Path


def firmware_version_from_name(name: str) -> str:
    match = re.search(r"(?i)(?:^|[_-])v(\d+(?:\.\d+){0,3})(?=[_.-]|$)", name)
    if match:
        return f"v{match.group(1)}"
    return ""


def package_version(path: str) -> str:
    if not path:
        return ""
    name = Path(path).expanduser().name
    match = re.search(r"(?<![A-Za-z0-9])v?(\d+(?:\.\d+){1,3})(?![A-Za-z0-9])", name, re.IGNORECASE)
    if not match:
        return ""
    return f"v{match.group(1)}"
