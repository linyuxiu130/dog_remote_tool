from __future__ import annotations

from dog_remote_tool.core.profiles import ProductProfile
from dog_remote_tool.core.text import strip_ansi as _strip_ansi
from dog_remote_tool.modules.device_status import launch_labels as _launch_labels
from dog_remote_tool.modules.device_status import models as _models
from dog_remote_tool.modules.device_status import package_labels as _package_labels
from dog_remote_tool.modules.device_status import parser as _parser


PackageInfo = _models.PackageInfo
LaunchItem = _models.LaunchItem
DeviceStatus = _models.DeviceStatus
parse_probe_output = _parser.parse_probe_output
parse_launch_items = _parser.parse_launch_items


def package_summary(packages: tuple[PackageInfo, ...]) -> str:
    parts = [f"{label}: {name} {version}" for label, name, version in core_package_items(packages) if version != "未发现"]
    if parts:
        return "；".join(parts[:8])
    return "未发现机器人业务进程"


def core_package_items(packages: tuple[PackageInfo, ...], profile: ProductProfile | None = None) -> list[tuple[str, str, str]]:
    by_name = {package.name: package.version for package in packages}
    items: list[tuple[str, str, str]] = []
    groups = package_groups_for_profile(profile)
    for label, names in groups:
        found_name = ""
        found_version = ""
        for name in names:
            version = by_name.get(name)
            if version:
                found_name = name
                found_version = version
                break
        if found_version:
            items.append((label, found_name, found_version))
        else:
            items.append((label, names[0], "未发现"))
    return items


def package_groups_for_profile(profile: ProductProfile | None) -> tuple[tuple[str, tuple[str, ...]], ...]:
    if profile and profile.key == "xg1_nx":
        return _package_labels.XG1_NX_PACKAGE_GROUPS
    if profile and profile.key == "xg3588":
        return _package_labels.XG3588_PACKAGE_GROUPS
    if profile and profile.platform == "RK3588":
        return _package_labels.BASE_PACKAGE_GROUPS
    if profile and profile.platform == "S100":
        return _package_labels.S100_PACKAGE_GROUPS
    return _package_labels.NX_PACKAGE_GROUPS


def package_detail(packages: tuple[PackageInfo, ...]) -> str:
    if not packages:
        return "未读取到相关 dpkg 小包。"
    return "\n".join(f"{package.name}\t{package.version}" for package in packages)


def launch_summary(items: tuple[LaunchItem, ...], raw_launch: str) -> str:
    if not raw_launch:
        return "robot-launch 无输出"
    if "robot-launch not found" in raw_launch:
        return "未安装 robot-launch"
    if not items:
        return "未解析到 robot-launch 任务"
    running = sum(1 for item in items if item.status == "running")
    stopped = sum(1 for item in items if item.status == "stopped")
    errored = [item.name for item in items if item.status not in {"running", "stopped"}]
    text = f"robot-launch 进程：{running} 个运行 / {stopped} 个停止"
    if errored:
        text += "，异常 " + "、".join(errored[:4])
    return text


def launch_detail(items: tuple[LaunchItem, ...], raw_launch: str) -> str:
    if items:
        return "\n".join(
            f"{item.name}\t{launch_note_label(item.name)}\t{item.status}\tpid={item.pid or '-'}\tuptime={item.uptime or '-'}"
            for item in items
        )
    return raw_launch or "无 robot-launch 状态。"


def launch_note_label(name: str) -> str:
    return _launch_labels.LAUNCH_NOTE_LABELS.get(_normalize_launch_name(name), "服务")


def launch_note_detail(name: str) -> str:
    key = _normalize_launch_name(name)
    return _launch_labels.LAUNCH_NOTE_DETAILS.get(key, f"{name} 的 robot-launch 服务。")


def _normalize_launch_name(name: str) -> str:
    return name.strip().lower().replace(" ", "_")


def strip_ansi(text: str) -> str:
    return _strip_ansi(text)
