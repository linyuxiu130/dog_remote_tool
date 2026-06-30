from __future__ import annotations

from pathlib import Path
import re

from dog_remote_tool.core.units import format_byte_size


def human_bytes(size: int) -> str:
    return format_byte_size(size, ("B", "KiB", "MiB", "GiB", "TiB"), precision=2)


def package_release_name(package: Path) -> str:
    name = package.name
    for suffix in (".tar.gz", ".zip", ".tgz"):
        if name.lower().endswith(suffix):
            return name[: -len(suffix)]
    return package.stem


def is_tar_gz(package: Path) -> bool:
    return [suffix.lower() for suffix in package.suffixes[-2:]] == [".tar", ".gz"]


def is_zip(package: Path) -> bool:
    return package.suffix.lower() == ".zip"


def infer_rk3588_motion_from_text(text: str) -> str:
    lower = text.lower()
    prefix_motion = infer_rk3588_motion_from_release_name(lower)
    if prefix_motion:
        return prefix_motion
    if "motion-control" not in lower:
        return ""
    if "-xgw" in lower or "_xgw_" in lower:
        return "wheel"
    if "-xg" in lower or "_xg_" in lower:
        return "point"
    return ""


def infer_rk3588_motion_from_release_name(name: str) -> str:
    release = package_release_name(Path(name)).lower()
    token = re.search(r"(?<!\d)(606|626)\d{6,}[a-z0-9]*", release)
    if not token:
        return ""
    return {"606": "point", "626": "wheel"}[token.group(1)]


def target_motion(target_key: str) -> str:
    if "_wheel_" in target_key:
        return "wheel"
    if "_point_" in target_key:
        return "point"
    return ""


def motion_label(motion: str) -> str:
    return {"point": "点足", "wheel": "轮足"}.get(motion, "未识别")
