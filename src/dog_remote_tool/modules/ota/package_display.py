from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from dog_remote_tool.modules.ota import deb_deploy
from dog_remote_tool.modules.ota import flash as ota_flash
from dog_remote_tool.modules.ota.manifest import manifest_summary
from dog_remote_tool.modules.ota.manifest_reader import package_manifest
from dog_remote_tool.modules.ota.package_classifier import package_motion
from dog_remote_tool.modules.ota.package_locator import default_nx_tools, latest_local as backend_latest_local, latest_package_for_family
from dog_remote_tool.modules.ota import package_mcu
from dog_remote_tool.modules.ota import package_utils as ota_package_utils
from dog_remote_tool.modules.ota.package_utils import human_bytes, package_release_name
from dog_remote_tool.modules.ota import package_versions


MCU_DISPLAY_SLOTS = package_mcu.MCU_DISPLAY_SLOTS
mcu_display_slots = package_mcu.mcu_display_slots
mcu_slot_for_name = package_mcu.mcu_slot_for_name
_firmware_version_from_name = package_versions.firmware_version_from_name
package_version = package_versions.package_version
_LIGHT_SMALL_ARCHIVE_MAX_BYTES = 512 * 1024 * 1024


def target_motion(target_key: str) -> str:
    return ota_package_utils.target_motion(target_key)


def latest_local(pattern: str) -> str:
    package = backend_latest_local(pattern)
    return str(package) if package else ""


def latest_package(family: str) -> str:
    package = latest_package_for_family(family)
    return str(package) if package else ""


def _is_direct_small_package(package: Path) -> bool:
    return deb_deploy.is_deploy_dir(package) or deb_deploy.is_deb_file(package) or deb_deploy.is_whl_file(package)


def package_type(path: str) -> str:
    if not path:
        return ""
    package = Path(path).expanduser()
    if deb_deploy.is_deploy_dir(package):
        return "deb_deploy"
    if deb_deploy.is_deb_file(package):
        return "deb_package"
    if deb_deploy.is_whl_file(package):
        return "whl_package"
    if not package.is_file():
        return ""
    flash_hint = ota_flash.flash_type_hint(package)
    if flash_hint:
        return flash_hint
    try:
        return _ui_package_manifest(package).family
    except ValueError:
        flash_hint = ota_flash.flash_type_hint(package, inspect=True)
        if flash_hint:
            return flash_hint
        if deb_deploy.is_small_package_archive(package):
            return "small_deploy_archive"
        return ""


def package_type_hint(path: str) -> str:
    if not path:
        return ""
    package = Path(path).expanduser()
    name = package.name.lower()
    if deb_deploy.is_deploy_dir(package):
        return "deb_deploy"
    if deb_deploy.is_deb_file(package):
        return "deb_package"
    if deb_deploy.is_whl_file(package):
        return "whl_package"
    flash_hint = ota_flash.flash_type_hint(package)
    if flash_hint:
        return flash_hint
    suffixes = "".join(package.suffixes[-2:]).lower()
    if suffixes != ".tar.gz" and package.suffix.lower() != ".zip":
        return ""
    if any(token in name for token in ("rk3588", "3588")):
        return "rk3588"
    if any(token in name for token in ("orin", "_nx", "-nx", "nx_")):
        return "nx"
    if package.is_file() and package.stat().st_size <= _LIGHT_SMALL_ARCHIVE_MAX_BYTES:
        if deb_deploy.is_small_package_archive(package):
            return "small_deploy_archive"
    return ""


def package_light_summary(path: str) -> str:
    if not path:
        return "未选择升级包"
    package = Path(path).expanduser()
    if _is_direct_small_package(package):
        deb_summary = deb_deploy.deb_light_summary(package)
        return deb_summary + "；小包部署会走远端安装，不执行系统 OTA/线刷"
    if not package.is_file():
        return "文件不存在"
    parts = [f"大小：{human_bytes(package.stat().st_size)}"]
    family = package_type_hint(path)
    if family == "small_deploy_archive":
        deb_summary = deb_deploy.deb_light_summary(package)
        if deb_summary:
            return deb_summary + "；小包部署会走远端安装，不执行系统 OTA/线刷"
    if family:
        family_label = {
            "nx": "NX",
            "rk3588": "3588",
            "s100_flash": "S100 线刷",
            "orin_flash": "Orin NX 线刷",
            "line_flash": "线刷",
            "deb_deploy": "小包部署目录",
            "deb_package": "Debian 小包",
            "whl_package": "Python wheel 小包",
            "small_deploy_archive": "小包压缩包",
        }.get(family, family)
        parts.append(f"文件名识别：{family_label} 包")
    else:
        suffixes = "".join(package.suffixes[-2:]).lower()
        if suffixes == ".tar.gz" or package.suffix.lower() == ".zip":
            parts.append("结构：待升级前完整校验")
        else:
            parts.append("结构：未识别后缀")
    if family in {"s100_flash", "orin_flash", "line_flash"}:
        parts.append("线刷执行前会检查本机 USB 刷写入口并解压到本机缓存目录")
    else:
        parts.append("完整固件清单会在执行升级时校验并写入日志")
    return "；".join(parts)


def package_motion_type(path: str) -> str:
    if not path:
        return ""
    package = Path(path).expanduser()
    if not package.is_file():
        return ""
    return package_motion(package)


def package_summary(path: str) -> str:
    if not path:
        return ""
    package = Path(path).expanduser()
    if _is_direct_small_package(package):
        deb_summary = deb_deploy.deb_light_summary(package)
        return deb_summary
    if not package.is_file():
        return ""
    if ota_flash.flash_type_hint(package):
        rows = ota_flash.flash_detail_rows(str(package))
        return "；".join(f"{title}: {value}" for title, value in rows[:6])
    try:
        return manifest_summary(_ui_package_manifest(package))
    except ValueError:
        rows = ota_flash.flash_detail_rows(str(package))
        if rows:
            return "；".join(f"{title}: {value}" for title, value in rows[:6])
        if deb_deploy.is_small_package_archive(package):
            return deb_deploy.deb_light_summary(package)
        return ""


def package_firmware_summary(path: str) -> str:
    if not path:
        return ""
    package = Path(path).expanduser()
    if not package.is_file():
        return ""
    if ota_flash.flash_type_hint(package):
        return ""
    try:
        manifest = _ui_package_manifest(package)
    except ValueError:
        if ota_flash.flash_type_hint(package):
            return ""
        return ""
    parts: list[str] = []
    for module in manifest.modules:
        if not module.firmware:
            continue
        version = module.version or _firmware_version_from_name(Path(module.firmware).name)
        label = module.name or Path(module.firmware).stem
        if version:
            parts.append(f"{label}: {version}")
        else:
            parts.append(f"{label}: {Path(module.firmware).name}")
    if not parts:
        return ""
    suffix = "" if len(parts) <= 10 else f"；另 {len(parts) - 10} 个"
    return "目标固件：" + "；".join(parts[:10]) + suffix


def package_detail_rows(path: str) -> list[tuple[str, str]]:
    if not path:
        return []
    package = Path(path).expanduser()
    if _is_direct_small_package(package):
        deb_rows = deb_deploy.deb_detail_rows(package)
        return deb_rows
    if not package.is_file():
        return [("包状态", "文件不存在")]
    if ota_flash.flash_type_hint(package):
        return ota_flash.flash_detail_rows(str(package))
    try:
        manifest = _ui_package_manifest(package)
    except ValueError:
        rows = ota_flash.flash_detail_rows(str(package))
        if rows:
            return rows
        if deb_deploy.is_small_package_archive(package):
            deb_rows = deb_deploy.deb_detail_rows(package)
            if deb_rows:
                return deb_rows
        return [("包状态", "未识别 OTA/线刷包结构")]
    rows: list[tuple[str, str]] = [
        ("包设备版本", package_release_name(package)),
        ("包类型", {"nx": "NX 包", "rk3588": "3588 包"}.get(manifest.family, manifest.family or "未知")),
    ]
    if manifest.system_image:
        rows.append(("系统镜像", f"{Path(manifest.system_image).name} ({human_bytes(manifest.system_size)})"))
    for module in manifest.modules[:12]:
        if not module.firmware:
            continue
        version = module.version or _firmware_version_from_name(Path(module.firmware).name)
        value = version or Path(module.firmware).name
        rows.append((f"固件 · {module.name or Path(module.firmware).stem}", value))
    if len(manifest.modules) > 12:
        rows.append(("固件", f"另 {len(manifest.modules) - 12} 个模块"))
    return rows


def package_selection_detail_rows(path: str) -> list[tuple[str, str]]:
    if not path:
        return []
    package = Path(path).expanduser()
    if _is_direct_small_package(package):
        return deb_deploy.deb_detail_rows(package)
    if not package.is_file():
        return [("包状态", "文件不存在")]
    package_type = package_type_hint(path)
    type_label = {
        "nx": "NX 包",
        "rk3588": "3588 包",
        "s100_flash": "S100 线刷包",
        "orin_flash": "Orin NX 线刷包",
        "line_flash": "线刷包",
        "small_deploy_archive": "小包压缩包",
    }.get(package_type, "待校验")
    rows = [
        ("包设备版本", package_release_name(package)),
        ("包类型", type_label),
        ("包大小", human_bytes(package.stat().st_size)),
    ]
    if package_type == "small_deploy_archive":
        return deb_deploy.deb_detail_rows(package) or rows
    rows.append(("完整清单", "预检/升级时在后台校验并写入日志"))
    return rows


def package_mcu_target_versions(path: str, target_key: str) -> dict[str, str]:
    if not path:
        return {}
    package = Path(path).expanduser()
    if not package.is_file():
        return {}
    if ota_flash.flash_type_hint(package):
        return {}
    try:
        manifest = _ui_package_manifest(package)
    except ValueError:
        if ota_flash.flash_type_hint(package):
            return {}
        return {}
    return package_mcu.mcu_target_versions_from_manifest(manifest)


def _ui_package_manifest(package: Path):
    resolved = package.expanduser().resolve()
    stat = resolved.stat()
    return _cached_ui_package_manifest(str(resolved), stat.st_size, stat.st_mtime_ns)


@lru_cache(maxsize=8)
def _cached_ui_package_manifest(path: str, size: int, mtime_ns: int):
    del size, mtime_ns
    return package_manifest(Path(path))


def default_tools_path() -> str:
    tools = default_nx_tools()
    if tools:
        return str(tools)
    return latest_local("ota_tools*.tbz2")


def flash_type_label(package_type: str) -> str:
    return ota_flash.flash_type_label(package_type)
