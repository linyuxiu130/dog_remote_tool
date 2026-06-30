from __future__ import annotations

from pathlib import Path

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from dog_remote_tool.ui.pages.file_manager.drag_drop import accept_local_paths_or_ignore, event_has_local_paths, local_paths_from_event


class LocalPathList(QListWidget):
    paths_dropped = pyqtSignal(list)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.setDragDropMode(QAbstractItemView.DropOnly)
        self.setAlternatingRowColors(True)

    def dragEnterEvent(self, event) -> None:
        accept_local_paths_or_ignore(event)

    def dragMoveEvent(self, event) -> None:
        accept_local_paths_or_ignore(event)

    def dropEvent(self, event) -> None:
        paths = local_paths_from_event(event)
        if paths:
            self.paths_dropped.emit(paths)
            event.acceptProposedAction()
        else:
            event.ignore()

    def _has_local_paths(self, event) -> bool:
        return event_has_local_paths(event)


class UploadDialog(QDialog):
    def __init__(self, remote_path: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("ToolDialog")
        self.setWindowTitle("上传")
        self.setMinimumSize(620, 420)
        self.setModal(True)
        self._paths: list[str] = []

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 16)
        layout.setSpacing(12)

        title = QLabel("上传到远端目录")
        title.setObjectName("DialogTitle")
        layout.addWidget(title)

        remote = QLabel(remote_path)
        remote.setObjectName("PathBadge")
        remote.setTextInteractionFlags(Qt.TextSelectableByMouse)
        layout.addWidget(remote)

        hint = QLabel("拖入本地文件或目录，也可以使用下方按钮添加。")
        hint.setObjectName("Muted")
        layout.addWidget(hint)

        self.list_widget = LocalPathList()
        self.list_widget.setMinimumHeight(210)
        self.list_widget.paths_dropped.connect(self.add_paths)
        layout.addWidget(self.list_widget, 1)

        tools = QHBoxLayout()
        add_files = QPushButton("添加文件")
        add_files.setObjectName("SoftPrimary")
        add_files.clicked.connect(self.pick_files)
        add_dir = QPushButton("添加目录")
        add_dir.clicked.connect(self.pick_directory)
        clear = QPushButton("清空")
        clear.clicked.connect(self.clear_paths)
        tools.addWidget(add_files)
        tools.addWidget(add_dir)
        tools.addWidget(clear)
        tools.addStretch(1)
        layout.addLayout(tools)

        footer = QFrame()
        footer.setObjectName("DialogFooter")
        footer_layout = QHBoxLayout(footer)
        footer_layout.setContentsMargins(0, 10, 0, 0)
        self.count_label = QLabel("未选择")
        self.count_label.setObjectName("Muted")
        cancel = QPushButton("取消")
        cancel.clicked.connect(self.reject)
        self.upload_btn = QPushButton("上传")
        self.upload_btn.setObjectName("Primary")
        self.upload_btn.clicked.connect(self.accept)
        footer_layout.addWidget(self.count_label)
        footer_layout.addStretch(1)
        footer_layout.addWidget(cancel)
        footer_layout.addWidget(self.upload_btn)
        layout.addWidget(footer)
        self._sync_state()

    def pick_files(self) -> None:
        dialog = QFileDialog(self, "选择要上传的文件", str(Path.home()))
        dialog.setFileMode(QFileDialog.ExistingFiles)
        dialog.setOption(QFileDialog.DontUseNativeDialog, True)
        if dialog.exec_() == QDialog.Accepted:
            self.add_paths(dialog.selectedFiles())

    def pick_directory(self) -> None:
        dialog = QFileDialog(self, "选择要上传的目录", str(Path.home()))
        dialog.setFileMode(QFileDialog.Directory)
        dialog.setOption(QFileDialog.ShowDirsOnly, True)
        dialog.setOption(QFileDialog.DontUseNativeDialog, True)
        if dialog.exec_() == QDialog.Accepted:
            self.add_paths(dialog.selectedFiles())

    def add_paths(self, paths: list[str]) -> None:
        for path in paths:
            normalized = str(Path(path).expanduser())
            if normalized and normalized not in self._paths:
                self._paths.append(normalized)
        self._sync_state()

    def clear_paths(self) -> None:
        self._paths = []
        self._sync_state()

    def paths(self) -> list[str]:
        return list(self._paths)

    def _sync_state(self) -> None:
        self.list_widget.clear()
        for path in self._paths:
            item = QListWidgetItem(path)
            item.setToolTip(path)
            self.list_widget.addItem(item)
        count = len(self._paths)
        self.count_label.setText(f"已选择 {count} 项" if count else "未选择")
        self.upload_btn.setEnabled(count > 0)
