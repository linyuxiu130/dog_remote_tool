from __future__ import annotations

import json
import re
import tarfile
import zipfile
from pathlib import Path

from dog_remote_tool.modules.ota.package_utils import is_tar_gz, is_zip


def read_zip_package_info(zf: zipfile.ZipFile) -> dict:
    names = ["package_info.json"]
    names.extend(
        sorted(
            info.filename
            for info in zf.infolist()
            if not info.is_dir() and info.filename.endswith("/package_info.json")
        )
    )
    for name in names:
        try:
            raw = zf.read(name)
            return json.loads(raw.decode("utf-8"))
        except (KeyError, OSError, UnicodeDecodeError, json.JSONDecodeError):
            continue
    return {}


def _first_nx_zip_system_member(package: Path, zf: zipfile.ZipFile) -> zipfile.ZipInfo | None:
    image_pattern = zip_system_image_regex(package, zf)
    members = [info for info in zf.infolist() if not info.is_dir()]
    candidates: list[zipfile.ZipInfo] = []
    if image_pattern:
        candidates = [info for info in members if image_pattern.search(info.filename)]
    if not candidates:
        candidates = [
            info
            for info in members
            if info.filename.lower().endswith((".tar.gz", ".tgz")) and "ota" in info.filename.lower()
        ]
    return candidates[0] if candidates else None


def _inspect_nx_tar_stream(stream) -> int:
    with tarfile.open(fileobj=stream, mode="r|gz") as tf:
        for member in tf:
            if member.name.lstrip("./") == "ota_package.tar":
                return int(member.size)
    raise ValueError("NX 升级包结构异常: 未找到 ota_package.tar")


def nx_system_image_member(package: Path) -> str:
    if is_zip(package):
        try:
            with zipfile.ZipFile(package) as zf:
                info = _first_nx_zip_system_member(package, zf)
                if info:
                    return info.filename
        except zipfile.BadZipFile as exc:
            raise ValueError(f"ZIP 升级包格式异常: {exc}") from exc
        raise ValueError("NX ZIP 升级包结构异常: 未找到系统 OTA 包")
    return "ota_package.tar"


def nx_system_archive_size(package: Path) -> int:
    if is_zip(package):
        try:
            with zipfile.ZipFile(package) as zf:
                info = _first_nx_zip_system_member(package, zf)
                if info:
                    return int(info.file_size)
        except zipfile.BadZipFile as exc:
            raise ValueError(f"ZIP 升级包格式异常: {exc}") from exc
        raise ValueError("NX ZIP 升级包结构异常: 未找到系统 OTA 包")
    return package.stat().st_size


def inspect_nx_package(package: Path) -> int:
    if is_zip(package):
        try:
            with zipfile.ZipFile(package) as zf:
                info = _first_nx_zip_system_member(package, zf)
                if not info:
                    raise ValueError("NX ZIP 升级包结构异常: 未找到系统 OTA 包")
                with zf.open(info) as stream:
                    return _inspect_nx_tar_stream(stream)
        except (EOFError, tarfile.TarError) as exc:
            raise ValueError(f"NX ZIP 升级包结构异常: {exc}") from exc
        except zipfile.BadZipFile as exc:
            raise ValueError(f"ZIP 升级包格式异常: {exc}") from exc
    if not is_tar_gz(package):
        raise ValueError("NX 升级包结构异常: 未找到 ota_package.tar")
    try:
        with package.open("rb") as stream:
            return _inspect_nx_tar_stream(stream)
    except EOFError as exc:
        raise ValueError("升级包 gzip 流截断，请重新下载或传输") from exc
    except tarfile.TarError as exc:
        raise ValueError(f"升级包格式异常: {exc}") from exc


def zip_system_image_regex(package: Path, zf: zipfile.ZipFile) -> re.Pattern[str] | None:
    try:
        data = read_zip_package_info(zf)
        image_regex = data.get("system", {}).get("image_regex", "")
        return re.compile(image_regex) if image_regex else None
    except (AttributeError, re.error):
        return None


def inspect_rk3588_zip_package(package: Path) -> tuple[str, int]:
    try:
        with zipfile.ZipFile(package) as zf:
            image_pattern = zip_system_image_regex(package, zf)
            members = [info for info in zf.infolist() if not info.is_dir()]
            candidates = []
            if image_pattern:
                candidates = [info for info in members if image_pattern.search(info.filename)]
            if not candidates:
                candidates = [info for info in members if info.filename.lower().endswith(".img")]
            for info in candidates:
                with zf.open(info) as stream:
                    head = stream.read(4)
                if head == b"RKFW":
                    return info.filename, int(info.file_size)
    except zipfile.BadZipFile as exc:
        raise ValueError(f"ZIP 升级包格式异常: {exc}") from exc
    raise ValueError("3588 ZIP 升级包结构异常: 未找到 RKFW image")


def inspect_rk3588_package(package: Path) -> tuple[str, int]:
    if is_zip(package):
        return inspect_rk3588_zip_package(package)
    try:
        with tarfile.open(package, "r:gz") as tf:
            for member in tf:
                if not member.isfile() or not member.name.lower().endswith(".img"):
                    continue
                stream = tf.extractfile(member)
                head = stream.read(4) if stream else b""
                if head == b"RKFW":
                    return member.name, int(member.size)
    except EOFError as exc:
        raise ValueError("升级包 gzip 流截断，请重新下载或传输") from exc
    except tarfile.TarError as exc:
        raise ValueError(f"升级包格式异常: {exc}") from exc
    raise ValueError("3588 升级包结构异常: 未找到 RKFW image")


def inspect_tools_package(tools: Path) -> None:
    try:
        with tarfile.open(tools, "r:bz2") as tf:
            for index, member in enumerate(tf):
                if index > 500:
                    break
                if member.name.endswith("Linux_for_Tegra/tools/ota_tools/version_upgrade/nv_ota_start.sh"):
                    return
    except tarfile.TarError as exc:
        raise ValueError(f"OTA 工具包格式异常: {exc}") from exc
    raise ValueError("OTA 工具包结构异常: 未找到 nv_ota_start.sh")
