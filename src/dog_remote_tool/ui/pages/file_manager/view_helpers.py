from __future__ import annotations

from PyQt5.QtWidgets import QApplication, QStyle

from dog_remote_tool.modules import file_manager


def item_at(items: list[file_manager.RemoteFileItem], row: int) -> file_manager.RemoteFileItem | None:
    if 0 <= row < len(items):
        return items[row]
    return None


def row_for_path(items: list[file_manager.RemoteFileItem], path: str) -> int:
    for row, item in enumerate(items):
        if item.path == path:
            return row
    return -1


def replace_item_by_path(items: list[file_manager.RemoteFileItem], updated: file_manager.RemoteFileItem) -> int:
    row = row_for_path(items, updated.path)
    if row < 0:
        return -1
    items[row] = updated
    return row


def icon_for_item_kind(kind: str, cache: dict[str, object]):
    cached = cache.get(kind)
    if cached is not None:
        return cached
    style = QApplication.style()
    if kind == "dir":
        icon = style.standardIcon(QStyle.SP_DirIcon)
    elif kind == "link":
        icon = style.standardIcon(QStyle.SP_FileLinkIcon)
    else:
        icon = style.standardIcon(QStyle.SP_FileIcon)
    cache[kind] = icon
    return icon
