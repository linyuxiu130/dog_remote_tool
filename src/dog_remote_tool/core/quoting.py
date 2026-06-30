from __future__ import annotations

import shlex


def quote(value: str) -> str:
    return shlex.quote(value)


def yaml_string(value: str) -> str:
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'
