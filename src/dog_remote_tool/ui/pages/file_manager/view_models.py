from __future__ import annotations

from datetime import datetime

from PyQt5.QtCore import QAbstractListModel, QAbstractTableModel, QModelIndex, Qt

from dog_remote_tool.modules import file_manager
from dog_remote_tool.ui.pages.file_manager.helpers import kind_label, owner_label
from dog_remote_tool.ui.pages.file_manager.view_helpers import icon_for_item_kind, item_at, replace_item_by_path, row_for_path


ROLE_ITEM = Qt.UserRole


class RemoteFileIconModel(QAbstractListModel):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.items: list[file_manager.RemoteFileItem] = []
        self._icons: dict[str, object] = {}

    def rowCount(self, parent=QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self.items)

    def data(self, index: QModelIndex, role=Qt.DisplayRole):
        if not index.isValid():
            return None
        item = self.item_at(index.row())
        if item is None:
            return None
        if role == Qt.DisplayRole:
            return item.name
        if role == Qt.DecorationRole:
            return self._icon_for_item(item)
        if role == ROLE_ITEM:
            return item
        if role == Qt.ToolTipRole:
            return item.path
        return None

    def set_items(self, items: list[file_manager.RemoteFileItem]) -> None:
        self.beginResetModel()
        self.items = list(items)
        self.endResetModel()

    def item_at(self, row: int) -> file_manager.RemoteFileItem | None:
        return item_at(self.items, row)

    def update_item(self, updated: file_manager.RemoteFileItem) -> bool:
        row = replace_item_by_path(self.items, updated)
        if row < 0:
            return False
        model_index = self.index(row, 0)
        self.dataChanged.emit(model_index, model_index, [Qt.DisplayRole, Qt.DecorationRole, ROLE_ITEM])
        return True

    def row_for_path(self, path: str) -> int:
        return row_for_path(self.items, path)

    def _icon_for_item(self, item: file_manager.RemoteFileItem):
        return icon_for_item_kind(item.kind, self._icons)


class RemoteFileTableModel(QAbstractTableModel):
    HEADERS = ("名称", "类型", "大小", "修改时间", "权限", "所有者")

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.items: list[file_manager.RemoteFileItem] = []
        self._icons: dict[str, object] = {}

    def rowCount(self, parent=QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self.items)

    def columnCount(self, parent=QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self.HEADERS)

    def data(self, index: QModelIndex, role=Qt.DisplayRole):
        if not index.isValid():
            return None
        item = self.item_at(index.row())
        if item is None:
            return None
        column = index.column()
        if role == ROLE_ITEM:
            return item
        if role == Qt.DisplayRole:
            if column == 0:
                return item.name
            if column == 1:
                return kind_label(item.kind)
            if column == 2:
                return file_manager.format_size(item.size, item.kind)
            if column == 3:
                return datetime.fromtimestamp(item.mtime).strftime("%Y-%m-%d %H:%M:%S") if item.mtime else "-"
            if column == 4:
                return item.mode or "-"
            if column == 5:
                return owner_label(item)
        if role == Qt.DecorationRole and column == 0:
            return self._icon_for_item(item)
        if role == Qt.ToolTipRole:
            if column == 0:
                return item.path
            if column == 2 and item.kind == "dir":
                return "右键选择“计算大小”后显示目录总大小。"
        if role == Qt.UserRole + 2:
            if column == 0:
                return item.name.lower()
            if column == 1:
                return kind_label(item.kind)
            if column == 2:
                return item.size
            if column == 3:
                return item.mtime
            if column == 4:
                return item.mode
            if column == 5:
                return owner_label(item).lower()
        return None

    def headerData(self, section: int, orientation: Qt.Orientation, role=Qt.DisplayRole):
        if orientation == Qt.Horizontal and role == Qt.DisplayRole and 0 <= section < len(self.HEADERS):
            return self.HEADERS[section]
        return None

    def sort(self, column: int, order: Qt.SortOrder = Qt.AscendingOrder) -> None:
        if not 0 <= column < len(self.HEADERS):
            return
        reverse = order == Qt.DescendingOrder
        self.layoutAboutToBeChanged.emit()
        dirs = [item for item in self.items if item.kind == "dir"]
        others = [item for item in self.items if item.kind != "dir"]
        dirs.sort(key=lambda item: self._sort_value(item, column), reverse=reverse)
        others.sort(key=lambda item: self._sort_value(item, column), reverse=reverse)
        self.items[:] = dirs + others
        self.layoutChanged.emit()

    def set_items(self, items: list[file_manager.RemoteFileItem]) -> None:
        self.beginResetModel()
        self.items = list(items)
        self.endResetModel()

    def item_at(self, row: int) -> file_manager.RemoteFileItem | None:
        return item_at(self.items, row)

    def update_item(self, updated: file_manager.RemoteFileItem) -> bool:
        row = replace_item_by_path(self.items, updated)
        if row < 0:
            return False
        top_left = self.index(row, 0)
        bottom_right = self.index(row, self.columnCount() - 1)
        self.dataChanged.emit(top_left, bottom_right, [Qt.DisplayRole, ROLE_ITEM, Qt.UserRole + 2])
        return True

    def row_for_path(self, path: str) -> int:
        return row_for_path(self.items, path)

    def _sort_value(self, item: file_manager.RemoteFileItem, column: int):
        if column == 0:
            return item.name.lower()
        if column == 1:
            return kind_label(item.kind)
        if column == 2:
            return item.size
        if column == 3:
            return item.mtime
        if column == 4:
            return item.mode
        if column == 5:
            return owner_label(item).lower()
        return item.name.lower()

    def _icon_for_item(self, item: file_manager.RemoteFileItem):
        return icon_for_item_kind(item.kind, self._icons)
