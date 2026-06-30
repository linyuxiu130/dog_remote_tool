from __future__ import annotations

from PyQt5.QtCore import QItemSelectionModel, QModelIndex, Qt, pyqtSignal
from PyQt5.QtWidgets import QAbstractItemView, QHeaderView, QTableView

from dog_remote_tool.modules import file_manager
from dog_remote_tool.ui.pages.file_manager.view_drop import LocalDropMixin
from dog_remote_tool.ui.pages.file_manager.view_models import ROLE_ITEM, RemoteFileTableModel


class RemoteFileTreeView(LocalDropMixin, QTableView):
    files_dropped = pyqtSignal(list, str)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("RemoteFileTreeView")
        self._enable_drop()
        self.file_model = RemoteFileTableModel(self)
        self.setModel(self.file_model)
        self.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.setAlternatingRowColors(True)
        self.setSortingEnabled(True)
        self.verticalHeader().setVisible(False)
        self.verticalHeader().setDefaultSectionSize(28)
        header = self.horizontalHeader()
        header.setStretchLastSection(True)
        header.setSectionResizeMode(0, QHeaderView.Interactive)
        header.setSectionResizeMode(1, QHeaderView.Interactive)
        header.setSectionResizeMode(2, QHeaderView.Interactive)
        header.setSectionResizeMode(3, QHeaderView.Interactive)
        header.setSectionResizeMode(4, QHeaderView.Interactive)
        header.setSectionResizeMode(5, QHeaderView.Stretch)
        self.setColumnWidth(0, 560)
        self.setColumnWidth(1, 76)
        self.setColumnWidth(2, 96)
        self.setColumnWidth(3, 150)
        self.setColumnWidth(4, 112)
        header.setSortIndicator(0, Qt.AscendingOrder)

    def populate(self, items: list[file_manager.RemoteFileItem], selected_paths: set[str], pending_names: set[str]) -> bool:
        self.setUpdatesEnabled(False)
        sorting_enabled = self.isSortingEnabled()
        sort_section = self.horizontalHeader().sortIndicatorSection()
        sort_order = self.horizontalHeader().sortIndicatorOrder()
        if sorting_enabled:
            self.setSortingEnabled(False)
        try:
            self.file_model.set_items(items)
            if sorting_enabled:
                self.setSortingEnabled(True)
                self.sortByColumn(sort_section, sort_order)
            matched_pending = False
            selection = self.selectionModel()
            if selection:
                selection.clearSelection()
            for item in items:
                if item.path in selected_paths or item.name in pending_names:
                    row = self.file_model.row_for_path(item.path)
                    if row < 0:
                        continue
                    row_index = self.file_model.index(row, 0)
                    if selection:
                        selection.select(row_index, QItemSelectionModel.Select | QItemSelectionModel.Rows)
                    self.scrollTo(row_index)
                    matched_pending = matched_pending or item.name in pending_names
            return matched_pending
        finally:
            if sorting_enabled and not self.isSortingEnabled():
                self.setSortingEnabled(True)
            self.setUpdatesEnabled(True)

    def selected_remote_items(self) -> list[file_manager.RemoteFileItem]:
        result: list[file_manager.RemoteFileItem] = []
        selection = self.selectionModel()
        if selection is None:
            return result
        for index in selection.selectedRows():
            item = self.item_data(index)
            if item:
                result.append(item)
        return result

    def item_at_position(self, pos) -> QModelIndex | None:
        index = self.indexAt(pos)
        return index if index.isValid() else None

    def select_item_at(self, pos) -> None:
        index = self.indexAt(pos)
        if index.isValid() and not self.selectionModel().isRowSelected(index.row(), QModelIndex()):
            self.clearSelection()
            self.selectRow(index.row())

    def drop_target_dir(self, pos) -> str:
        item = self.item_data(self.indexAt(pos))
        if item and item.kind == "dir":
            return item.path
        return self.current_path

    def item_data(self, index: QModelIndex | None) -> file_manager.RemoteFileItem | None:
        if index is None or not index.isValid():
            return None
        item = index.data(ROLE_ITEM)
        return item if isinstance(item, file_manager.RemoteFileItem) else None

    def find_item_by_path(self, path: str) -> QModelIndex | None:
        row = self.file_model.row_for_path(path)
        if row < 0:
            return None
        return self.file_model.index(row, 0)

    def update_item(self, updated: file_manager.RemoteFileItem) -> None:
        self.file_model.update_item(updated)
