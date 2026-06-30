from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from PyQt5.QtWidgets import QWidget


@dataclass(frozen=True)
class PageSpec:
    title: str
    factory: Callable[[], QWidget]
    required_capability: str = ""
