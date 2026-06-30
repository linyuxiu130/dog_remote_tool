from __future__ import annotations

import tarfile
import zipfile
from pathlib import Path

from dog_remote_tool.modules.ota.inspect import inspect_nx_package, inspect_rk3588_package
from dog_remote_tool.modules.ota.package_utils import (
    infer_rk3588_motion_from_release_name,
    infer_rk3588_motion_from_text,
    is_tar_gz,
    is_zip,
)


def looks_like_orin_flash_package(package: Path) -> bool:
    if not is_tar_gz(package):
        return False
    try:
        with tarfile.open(package, "r:gz") as tf:
            for index, member in enumerate(tf):
                if index > 1200:
                    break
                name = member.name.lstrip("./").lower()
                if name in {"bootloader/flashcmd.txt", "bootloader/flash_win.bat"}:
                    return True
                if name == "bootloader/system.img":
                    return True
    except (EOFError, tarfile.TarError, OSError):
        return False
    return False


def package_family(package: Path) -> str:
    if is_zip(package):
        try:
            inspect_nx_package(package)
            return "nx"
        except ValueError:
            pass
        try:
            inspect_rk3588_package(package)
            return "rk3588"
        except ValueError:
            return ""
    if not is_tar_gz(package):
        return ""
    if looks_like_orin_flash_package(package):
        return ""
    try:
        inspect_nx_package(package)
        return "nx"
    except ValueError:
        pass
    try:
        inspect_rk3588_package(package)
        return "rk3588"
    except ValueError:
        pass
    return ""


def package_motion(package: Path) -> str:
    if package_family(package) != "rk3588":
        return ""
    release_motion = infer_rk3588_motion_from_release_name(package.name)
    if release_motion:
        return release_motion
    try:
        if is_zip(package):
            with zipfile.ZipFile(package) as zf:
                for info in zf.infolist():
                    name = info.filename.lower()
                    if name.endswith(".img"):
                        continue
                    if info.is_dir() or not name.endswith((".yaml", ".yml")):
                        continue
                    with zf.open(info) as stream:
                        text = stream.read(256 * 1024).decode("utf-8", errors="ignore")
                    motion = infer_rk3588_motion_from_text(text)
                    if motion:
                        return motion
            return ""
        with tarfile.open(package, "r:gz") as tf:
            for member in tf:
                name = member.name.lower()
                if name.endswith(".img"):
                    continue
                if not member.isfile() or not name.endswith((".yaml", ".yml")):
                    continue
                stream = tf.extractfile(member)
                if not stream:
                    continue
                text = stream.read(256 * 1024).decode("utf-8", errors="ignore")
                motion = infer_rk3588_motion_from_text(text)
                if motion:
                    return motion
    except (EOFError, tarfile.TarError, OSError, zipfile.BadZipFile):
        return ""
    return ""
