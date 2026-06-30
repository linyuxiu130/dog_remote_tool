from __future__ import annotations

import re
import tarfile
import zipfile
from pathlib import Path

from dog_remote_tool.modules.ota.inspect import (
    inspect_nx_package,
    inspect_rk3588_package,
    inspect_rk3588_zip_package,
    nx_system_image_member,
    read_zip_package_info,
)
from dog_remote_tool.modules.ota.package_classifier import package_family
from dog_remote_tool.modules.ota.package_utils import is_zip
from dog_remote_tool.modules.ota.types import OtaFirmwareModule, OtaPackageManifest


def parse_simple_yaml_modules(text: str) -> list[OtaFirmwareModule]:
    modules: list[OtaFirmwareModule] = []
    current_name = ""
    current: dict[str, str] = {}

    def flush() -> None:
        nonlocal current_name, current
        if current_name and current.get("type") == "bin" and current.get("source"):
            modules.append(
                OtaFirmwareModule(
                    current_name,
                    current["source"],
                    version=current.get("version", ""),
                    runnable=False,
                )
            )
        current_name = ""
        current = {}

    for raw in text.splitlines():
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        if raw[:1].strip() and raw.rstrip().endswith(":"):
            flush()
            current_name = raw.strip()[:-1]
            continue
        if not current_name or ":" not in raw:
            continue
        key, value = raw.split(":", 1)
        current[key.strip()] = value.strip().strip('"').strip("'")
    flush()
    return modules


def first_matching_zip_member(zf: zipfile.ZipFile, pattern: str) -> str:
    try:
        compiled = re.compile(pattern)
    except re.error:
        return ""
    for info in zf.infolist():
        if not info.is_dir() and compiled.search(info.filename):
            return info.filename
    return ""


def zip_manifest(package: Path) -> OtaPackageManifest:
    system_image, system_size = inspect_rk3588_zip_package(package)
    modules: list[OtaFirmwareModule] = []
    with zipfile.ZipFile(package) as zf:
        data = read_zip_package_info(zf)
        for item in data.get("modules", []):
            name = str(item.get("name", "")).strip()
            firmware = first_matching_zip_member(zf, str(item.get("package_regex", "")))
            tool = first_matching_zip_member(zf, str(item.get("tool_regex", "")))
            if name or firmware or tool:
                modules.append(OtaFirmwareModule(name or firmware, firmware, tool=tool, runnable=bool(firmware and tool)))
    return OtaPackageManifest(package.name, "rk3588", system_image, system_size, tuple(modules))


def nx_zip_manifest(package: Path) -> OtaPackageManifest:
    system_image = nx_system_image_member(package)
    payload_size = inspect_nx_package(package)
    modules: list[OtaFirmwareModule] = []
    with zipfile.ZipFile(package) as zf:
        data = read_zip_package_info(zf)
        for item in data.get("modules", []):
            name = str(item.get("name", "")).strip()
            firmware = first_matching_zip_member(zf, str(item.get("package_regex", "")))
            tool = first_matching_zip_member(zf, str(item.get("tool_regex", "")))
            if name or firmware or tool:
                modules.append(OtaFirmwareModule(name or firmware, firmware, tool=tool, runnable=bool(firmware and tool)))
    return OtaPackageManifest(package.name, "nx", system_image, payload_size, tuple(modules))


def tar_rk3588_manifest(package: Path) -> OtaPackageManifest:
    system_image, system_size = inspect_rk3588_package(package)
    modules: list[OtaFirmwareModule] = []
    try:
        with tarfile.open(package, "r:gz") as tf:
            for member in tf:
                if not member.isfile() or not member.name.lower().endswith((".yaml", ".yml")):
                    continue
                stream = tf.extractfile(member)
                if not stream:
                    continue
                modules.extend(parse_simple_yaml_modules(stream.read(512 * 1024).decode("utf-8", errors="ignore")))
    except (EOFError, tarfile.TarError, OSError):
        modules = []
    return OtaPackageManifest(package.name, "rk3588", system_image, system_size, tuple(modules))


def package_manifest(package: Path) -> OtaPackageManifest:
    family = package_family(package)
    if family == "nx":
        if is_zip(package):
            return nx_zip_manifest(package)
        payload_size = inspect_nx_package(package)
        return OtaPackageManifest(package.name, family, "ota_package.tar", payload_size)
    if family == "rk3588" and is_zip(package):
        return zip_manifest(package)
    if family == "rk3588":
        return tar_rk3588_manifest(package)
    raise ValueError("未识别 OTA 包结构")
