from __future__ import annotations

from PyQt5.QtCore import QItemSelectionModel, QModelIndex, QSize, Qt, pyqtSignal
from PyQt5.QtGui import QFontMetrics
from PyQt5.QtWidgets import QAbstractItemView, QListView

from dog_remote_tool.modules import file_manager
from dog_remote_tool.ui.pages.file_manager.icon_delegate import FileIconDelegate
from dog_remote_tool.ui.pages.file_manager.view_drop import LocalDropMixin
from dog_remote_tool.ui.pages.file_manager.view_models import ROLE_ITEM, RemoteFileIconModel


class RemoteFileIconView(LocalDropMixin, QListView):
    files_dropped = pyqtSignal(list, str)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("RemoteFileIconView")
        self.file_model = RemoteFileIconModel(self)
        self.setModel(self.file_model)
        self._enable_drop()
        self.setViewMode(QListView.IconMode)
        self.setMovement(QListView.Static)
        self.setResizeMode(QListView.Adjust)
        self.setWrapping(True)
        self.setSpacing(8)
        self.setUniformItemSizes(True)
        self.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.setIconSize(QSize(88, 88))
        self.setWordWrap(True)
        self.setTextElideMode(Qt.ElideNone)
        self.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._icon_delegate = FileIconDelegate(self)
        self.setGridSize(QSize(self._icon_delegate.cell_width, self._icon_delegate.cell_height))
        self.setItemDelegate(self._icon_delegate)
        selection = self.selectionModel()
        if selection:
            selection.selectionChanged.connect(lambda _selected, _deselected: self._sync_selected_grid_height())

    def populate(self, items: list[file_manager.RemoteFileItem], selected_paths: set[str], pending_names: set[str]) -> bool:
        self.setUpdatesEnabled(False)
        try:
            self.file_model.set_items(items)
            matched_pending = False
            selection = self.selectionModel()
            if selection:
                selection.clearSelection()
            for item in items:
                if item.path in selected_paths or item.name in pending_names:
                    row = self.file_model.row_for_path(item.path)
                    if row < 0:
                        continue
                    model_index = self.file_model.index(row, 0)
                    if selection:
                        selection.select(model_index, QItemSelectionModel.Select)
                    self.scrollTo(model_index)
                    matched_pending = matched_pending or item.name in pending_names
            self._sync_selected_grid_height()
            return matched_pending
        finally:
            self.setUpdatesEnabled(True)

    def selected_remote_items(self) -> list[file_manager.RemoteFileItem]:
        result: list[file_manager.RemoteFileItem] = []
        selection = self.selectionModel()
        if selection is None:
            return result
        for model_index in selection.selectedIndexes():
            item = model_index.data(ROLE_ITEM)
            if isinstance(item, file_manager.RemoteFileItem):
                result.append(item)
        return result

    def item_at_position(self, pos) -> QModelIndex | None:
        index = self.indexAt(pos)
        return index if index.isValid() else None

    def select_item_at(self, pos) -> None:
        index = self.indexAt(pos)
        if index.isValid() and not self.selectionModel().isSelected(index):
            self.clearSelection()
            self.selectionModel().select(index, QItemSelectionModel.Select)

    def drop_target_dir(self, pos) -> str:
        index = self.indexAt(pos)
        item = index.data(ROLE_ITEM) if index.isValid() else None
        if isinstance(item, file_manager.RemoteFileItem) and item.kind == "dir":
            return item.path
        return self.current_path

    def find_item_by_path(self, path: str) -> QModelIndex | None:
        row = self.file_model.row_for_path(path)
        if row < 0:
            return None
        return self.file_model.index(row, 0)

    def update_item(self, updated: file_manager.RemoteFileItem) -> None:
        self.file_model.update_item(updated)
        self._sync_selected_grid_height()

    def _sync_selected_grid_height(self) -> None:
        metrics = QFontMetrics(self.font())
        line_count = self._selected_line_count(metrics)
        new_height = self._icon_delegate.height_for_lines(line_count, metrics)
        if new_height == self._icon_delegate.cell_height:
            return
        self._icon_delegate.cell_height = new_height
        self.setGridSize(QSize(self._icon_delegate.cell_width, new_height))
        self.doItemsLayout()
        self.viewport().update()

    def _selected_line_count(self, metrics: QFontMetrics) -> int:
        line_count = self._icon_delegate.max_lines
        selection = self.selectionModel()
        indexes = selection.selectedIndexes() if selection is not None else []
        for model_index in indexes:
            lines = self._icon_delegate._wrapped_lines(str(model_index.data(Qt.DisplayRole) or ""), metrics, None)
            line_count = max(line_count, len(lines))
        return line_count
