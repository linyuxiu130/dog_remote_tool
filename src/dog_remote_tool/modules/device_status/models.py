from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PackageInfo:
    name: str
    version: str


@dataclass(frozen=True)
class LaunchItem:
    index: str
    name: str
    status: str
    pid: str = ""
    uptime: str = ""


@dataclass(frozen=True)
class DeviceStatus:
    hostname: str
    release_version: str
    packages: tuple[PackageInfo, ...]
    launch_items: tuple[LaunchItem, ...]
    raw_launch: str
    error: str = ""
