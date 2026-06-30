from __future__ import annotations

import os
import re
from datetime import datetime

from dog_remote_tool.core.durations import format_seconds
from dog_remote_tool.core.profiles import ProductProfile
from dog_remote_tool.modules import bag
from dog_remote_tool.ui.pages.bag import record_metadata, topic_helpers


record_context = record_metadata.record_context
empty_record_context = record_metadata.empty_record_context
record_info = record_metadata.record_info
topic_display_name = topic_helpers.topic_display_name
topic_tooltip = topic_helpers.topic_tooltip
topic_name_exists = topic_helpers.topic_name_exists
editable_topic_list = topic_helpers.editable_topic_list
normalize_topic_values = topic_helpers.normalize_topic_values
set_config_topics = topic_helpers.set_config_topics


def compact_middle(text: str, limit: int = 36) -> str:
    if len(text) <= limit:
        return text
    left = max(8, limit - 13)
    return f"{text[:left]}...{text[-8:]}"


def format_transfer_eta(seconds: float) -> str:
    return format_seconds(seconds, always_hours=False, rounded=True)


def pull_local_base(include_bag: bool, local_dir_text: str) -> str:
    return (local_dir_text.strip() or bag.DEFAULT_LOCAL_BAG_DIR) if include_bag else bag.DEFAULT_LOCAL_LOG_DIR


def pull_confirm_detail(include_bag: bool, remote_paths: list[str]) -> str:
    return "\n".join(remote_paths) if include_bag else "仅拉取当前产品匹配到的日志目录"


def pull_progress_value(percent: float) -> int:
    return max(0, min(100, int(round(percent))))


def should_reset_transfer_timer(label: str, progress_value: int, previous_label: str, current_progress_value: int) -> bool:
    return label != previous_label or progress_value < current_progress_value


def pull_progress_texts(label: str, progress_value: int, speed: str, elapsed: float) -> tuple[str, str, str, str]:
    short_label = label.replace("正在拉取Bag包", "拉取Bag").replace("正在拉取Log", "拉取Log")
    eta_text = "预计 --"
    if progress_value > 0 and elapsed >= 1.0:
        eta_seconds = elapsed * (100 - progress_value) / progress_value
        eta_text = f"预计 {format_transfer_eta(eta_seconds)}"
    return short_label, f"{progress_value}%", f"速度 {speed or '--'}", eta_text


def pull_result_log_lines(result: dict, product: str) -> list[str]:
    validation = result.get("validation", {})
    lines = [
        "=" * 50,
        f"保存位置: {result.get('target_dir')}",
    ]
    if result.get("summary_file"):
        lines.append(f"说明文件: {result.get('summary_file')}")
    lines.extend(
        [
            f"Bag包: {'成功' if result.get('bag_success') else '失败'}",
            f"Log文件: {'成功' if result.get('log_success') else '失败'}",
        ]
    )
    if result.get("calibration_attempted") or product == "nxl2":
        lines.append(f"标定文件: {'成功' if result.get('calibration_success') else '未保存'}")
    lines.append(f"[录制结果检查] {validation.get('summary', '')}")
    lines.extend(f"[录制结果检查] {detail}" for detail in validation.get("details", []))
    if result.get("deleted"):
        lines.append(f"远端Bag自动删除成功: {len(result['deleted'])} 个")
    if result.get("delete_failed"):
        lines.append(f"远端Bag自动删除失败: {len(result['delete_failed'])} 个")
    lines.append("=" * 50)
    return lines


def pull_finished_message(result: dict) -> str:
    validation = result.get("validation", {})
    summary_line = f"\n说明文件: {result.get('summary_file')}" if result.get("summary_file") else ""
    return f"保存位置: {result.get('target_dir')}{summary_line}\n\n录制结果检查: {validation.get('summary', '')}"


def unsafe_remote_bag_paths(paths: list[str], profile: ProductProfile) -> list[str]:
    return [path for path in paths if not bag.BagBackend.is_safe_remote_bag_path(path, profile)]


def delete_confirm_message(paths: list[str]) -> str:
    return "此操作不可恢复。\n\n" + "\n".join(paths)


def delete_finished_message(deleted: list, failed: list) -> tuple[bool, str]:
    if failed:
        return True, f"已删除 {len(deleted)} 个，失败 {len(failed)} 个。\n\n" + "\n".join(failed)
    return False, f"已删除远端Bag目录 {len(deleted)} 个"


def known_remote_bag_size_text(paths: list[str], remote_bag_items: list[dict]) -> str:
    if not paths:
        return "--"
    sizes = {
        str(item.get("path") or ""): int(item.get("size") or 0)
        for item in remote_bag_items
        if int(item.get("size") or 0) > 0
    }
    if not all(path in sizes for path in paths):
        return ""
    return bag.format_size(sum(sizes[path] for path in paths))


def default_remote_bag_path(product: str, profile_home: str) -> str:
    return "/opt/data" if product == "nxl2" else profile_home


def remote_bag_display_names(paths: list[str], limit: int = 36) -> list[str]:
    return [compact_middle(os.path.basename(path.rstrip("/")) or path, limit) for path in paths]


def current_bag_label_state(paths: list[str]) -> tuple[str, str, bool]:
    if not paths:
        return "无", "", False
    names = remote_bag_display_names(paths)
    if len(names) == 1:
        text = names[0]
    else:
        suffix = "..." if len(names) > 2 else ""
        text = f"{len(names)} 个Bag: {', '.join(names[:2])}{suffix}"
    return text, "\n".join(paths), True


def active_remote_bag_paths(remote_bag_items: list[dict], selected_paths: list[str] | None = None) -> list[str]:
    selected = set(selected_paths or [])
    paths = []
    for item in remote_bag_items:
        path = str(item.get("path") or "")
        if not path or int(item.get("active") or 0) <= 0:
            continue
        if selected_paths is not None and path not in selected:
            continue
        paths.append(path)
    return paths


def started_at_from_remote_bag_paths(paths: list[str]) -> datetime | None:
    started_values: list[datetime] = []
    for path in paths:
        name = os.path.basename(path.rstrip("/"))
        match = re.match(r"^(?:rosbag2_)?(?:xg|zg|air|l2)_(\d{8}_\d{6})$", name, re.IGNORECASE)
        if not match:
            continue
        try:
            started_values.append(datetime.strptime(match.group(1), "%Y%m%d_%H%M%S"))
        except ValueError:
            continue
    return min(started_values) if started_values else None


def remote_scan_dirs(save_path: str, default_path: str, profile_home: str) -> list[str]:
    scan_dirs: list[str] = []
    for path in (save_path, default_path, profile_home):
        normalized = path.rstrip("/") or "/" if path else ""
        if normalized and normalized not in scan_dirs:
            scan_dirs.append(normalized)
    return scan_dirs or [profile_home]


def remote_disk_text(disk: dict | None) -> str:
    if not disk:
        return "可用空间: 未知"
    return f"可用空间: {bag.format_size(disk['available'])} / {bag.format_size(disk['total'])}"


def remote_bag_status_text(items: list[dict]) -> str:
    active_count = sum(1 for item in items if int(item.get("active") or 0) > 0)
    suffix = f"，{active_count} 个录制中" if active_count else ""
    return f"{len(items)} 个Bag{suffix}"


def remote_bag_table_row(item: dict) -> tuple[bool, list[str], str]:
    active = int(item.get("active") or 0) > 0
    path = str(item.get("path") or "")
    return (
        active,
        [
            "录制中" if active else "已停止",
            str(item.get("mtime") or ""),
            bag.format_size(int(item.get("size") or 0)),
            str(item.get("name") or ""),
            path,
        ],
        path,
    )
