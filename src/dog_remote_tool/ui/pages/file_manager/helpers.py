from __future__ import annotations

import json
import re
from datetime import datetime

from dog_remote_tool.modules import file_manager
from dog_remote_tool.ui.pages.file_manager import favorites


TRANSFER_PERCENT_PATTERN = re.compile(r"(?<!\d)(\d{1,3})%")
DEFAULT_REMOTE_FAVORITES = favorites.DEFAULT_REMOTE_FAVORITES
favorite_storage_key = favorites.favorite_storage_key
default_favorites = favorites.default_favorites
stored_favorites = favorites.stored_favorites
short_path_label = favorites.short_path_label


def names_summary(names: list[str], limit: int = 5) -> str:
    shown = "、".join(names[:limit])
    if len(names) > limit:
        shown += f" 等 {len(names)} 项"
    return shown


def overwrite_confirm_message(action: str, names: list[str]) -> str:
    return f"{action}目标已存在：{names_summary(names)}\n是否覆盖？"


def transfer_progress_percent(text: str) -> int | None:
    matches = TRANSFER_PERCENT_PATTERN.findall(text)
    if not matches:
        return None
    return max(0, min(100, int(matches[-1])))


def visible_items(
    items: list[file_manager.RemoteFileItem],
    show_hidden: bool,
    max_render_items: int,
) -> list[file_manager.RemoteFileItem]:
    visible: list[file_manager.RemoteFileItem] = []
    for item in items:
        if not show_hidden and item.name.startswith("."):
            continue
        visible.append(item)
        if len(visible) >= max_render_items:
            break
    return visible


def visible_counts(
    items: list[file_manager.RemoteFileItem],
    show_hidden: bool,
    max_render_items: int,
) -> tuple[int, int, int]:
    if show_hidden:
        filtered_count = len(items)
        hidden_count = 0
    else:
        filtered_count = sum(1 for item in items if not item.name.startswith("."))
        hidden_count = len(items) - filtered_count
    rendered_count = min(filtered_count, max_render_items)
    omitted_count = max(0, filtered_count - rendered_count)
    return rendered_count, hidden_count, omitted_count


def items_signature(items: list[file_manager.RemoteFileItem]) -> str:
    return json.dumps(
        [(item.name, item.kind, item.size, int(item.mtime), item.mode, item.owner, item.group) for item in items],
        ensure_ascii=False,
        separators=(",", ":"),
    )


def kind_label(kind: str) -> str:
    return {
        "dir": "目录",
        "file": "文件",
        "link": "链接",
        "other": "其他",
    }.get(kind, kind)


def owner_label(item: file_manager.RemoteFileItem) -> str:
    if item.owner and item.group:
        return f"{item.owner}:{item.group}"
    return item.owner or item.group or "-"


def selected_detail_text(items: list[file_manager.RemoteFileItem]) -> str:
    if not items:
        return "未选择项目"
    if len(items) > 1:
        dirs = sum(1 for item in items if item.kind == "dir")
        files = sum(1 for item in items if item.kind == "file")
        return f"已选择 {len(items)} 项，目录 {dirs} 个，文件 {files} 个"
    item = items[0]
    modified = datetime.fromtimestamp(item.mtime).strftime("%Y-%m-%d %H:%M:%S") if item.mtime else "-"
    return (
        f"{item.path}    {kind_label(item.kind)}    {file_manager.format_size(item.size, item.kind)}    "
        f"{modified}    {item.mode or '-'}    {owner_label(item)}"
    )


def is_under_home(path: str, home: str) -> bool:
    normalized_home = file_manager.clean_remote_path(home, home).rstrip("/")
    value = file_manager.clean_remote_path(path, home)
    return value == normalized_home or value.startswith(normalized_home + "/")


def breadcrumb_segments(path: str, home: str, max_parts: int = 5) -> tuple[bool, list[tuple[str, str]]]:
    normalized = file_manager.clean_remote_path(path, home)
    parts = [part for part in normalized.split("/") if part]
    cumulative: list[tuple[str, str]] = []
    current = "/"
    for part in parts:
        current = file_manager.child_path(current, part)
        cumulative.append((part, current))
    shown = cumulative[-max_parts:]
    return len(cumulative) > len(shown), shown
