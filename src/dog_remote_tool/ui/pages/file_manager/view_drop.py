from __future__ import annotations

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QAbstractItemView

from dog_remote_tool.ui.pages.file_manager.drag_drop import accept_local_paths_or_ignore, local_paths_from_event


class LocalDropMixin:
    def _enable_drop(self) -> None:
        self.setAcceptDrops(True)
        self.setDragEnabled(False)
        self.setDragDropMode(QAbstractItemView.DragDrop)
        self.setDefaultDropAction(Qt.CopyAction)
        self.current_path = ""

    def dragEnterEvent(self, event) -> None:
        accept_local_paths_or_ignore(event)

    def dragMoveEvent(self, event) -> None:
        accept_local_paths_or_ignore(event)

    def dropEvent(self, event) -> None:
        paths = local_paths_from_event(event)
        if paths:
            self.files_dropped.emit(paths, self.drop_target_dir(event.pos()))
            event.acceptProposedAction()
        else:
            event.ignore()

    def set_current_path(self, path: str) -> None:
        self.current_path = path

    def drop_target_dir(self, _pos) -> str:
        return self.current_path
