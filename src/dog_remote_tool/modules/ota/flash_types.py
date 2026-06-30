from __future__ import annotations

from dataclasses import dataclass


S100_FLASH_TARGET_KEYS = ("xg2_s100", "zg_surround_s100")


@dataclass(frozen=True)
class FlashTarget:
    key: str
    label: str
    family: str
    accepted_types: tuple[str, ...]
    host: str = ""
    user: str = ""
    password: str = ""
