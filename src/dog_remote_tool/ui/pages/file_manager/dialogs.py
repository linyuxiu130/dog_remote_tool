from __future__ import annotations

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QFont, QKeySequence
from PyQt5.QtWidgets import (
    QApplication,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QShortcut,
    QVBoxLayout,
    QWidget,
)

from dog_remote_tool.ui.pages.file_manager.upload_dialog import LocalPathList as _LocalPathList
from dog_remote_tool.ui.pages.file_manager.upload_dialog import UploadDialog as _UploadDialog


LocalPathList = _LocalPathList
UploadDialog = _UploadDialog


class NameDialog(QDialog):
    def __init__(
        self,
        title: str,
        label: str,
        initial: str = "",
        helper: str = "",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("ToolDialog")
        self.setWindowTitle(title)
        self.setMinimumWidth(520)
        self.setModal(True)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 16)
        layout.setSpacing(12)

        title_label = QLabel(title)
        title_label.setObjectName("DialogTitle")
        layout.addWidget(title_label)

        if helper:
            helper_label = QLabel(helper)
            helper_label.setObjectName("Muted")
            helper_label.setWordWrap(True)
            layout.addWidget(helper_label)

        field_label = QLabel(label)
        field_label.setObjectName("FieldLabel")
        self.name_edit = QLineEdit(initial)
        self.name_edit.setMinimumHeight(34)
        self.name_edit.selectAll()
        self.name_edit.returnPressed.connect(self.accept)
        layout.addWidget(field_label)
        layout.addWidget(self.name_edit)

        footer = QFrame()
        footer.setObjectName("DialogFooter")
        button_row = QHBoxLayout(footer)
        button_row.setContentsMargins(0, 10, 0, 0)
        button_row.addStretch(1)
        cancel = QPushButton("取消")
        cancel.clicked.connect(self.reject)
        ok = QPushButton("确定")
        ok.setObjectName("Primary")
        ok.setDefault(True)
        ok.clicked.connect(self.accept)
        button_row.addWidget(cancel)
        button_row.addWidget(ok)
        layout.addWidget(footer)

    def name(self) -> str:
        return self.name_edit.text()


class TextPreviewDialog(QDialog):
    save_requested = pyqtSignal(str)

    def __init__(
        self,
        path: str,
        text: str,
        size_label: str,
        truncated: bool,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("ToolDialog")
        self.setWindowTitle("文件预览")
        self.setMinimumSize(1180, 780)
        self._saved_text = text
        screen = QApplication.primaryScreen()
        if screen:
            available = screen.availableGeometry()
            self.resize(
                min(1540, max(1180, int(available.width() * 0.9))),
                min(1040, max(780, int(available.height() * 0.86))),
            )
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 16)
        layout.setSpacing(10)

        title = QLabel("文本编辑")
        title.setObjectName("DialogTitle")
        layout.addWidget(title)

        path_label = QLabel(path)
        path_label.setObjectName("PathBadge")
        path_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        layout.addWidget(path_label)

        detail = QLabel(f"{size_label}" + ("，仅显示前 128 KB" if truncated else ""))
        detail.setObjectName("Muted")
        layout.addWidget(detail)

        self.preview = QPlainTextEdit()
        self.preview.setObjectName("PreviewText")
        self.preview.setFont(QFont("DejaVu Sans Mono", 10))
        self.preview.setPlainText(text)
        self.preview.textChanged.connect(self._sync_dirty_state)
        layout.addWidget(self.preview, 1)

        footer = QFrame()
        footer.setObjectName("DialogFooter")
        buttons = QHBoxLayout(footer)
        buttons.setContentsMargins(0, 10, 0, 0)
        self.save_status = QLabel("未修改")
        self.save_status.setObjectName("Muted")
        buttons.addWidget(self.save_status)
        buttons.addStretch(1)
        self.save_btn = QPushButton("保存")
        self.save_btn.setObjectName("Primary")
        self.save_btn.clicked.connect(self._request_save)
        close = QPushButton("关闭")
        close.clicked.connect(self._close_dialog)
        buttons.addWidget(self.save_btn)
        buttons.addWidget(close)
        layout.addWidget(footer)
        QShortcut(QKeySequence.Save, self, activated=self._request_save)
        self._sync_dirty_state()

    def mark_saved(self, text: str | None = None) -> None:
        if text is not None:
            self._saved_text = text
        else:
            self._saved_text = self.preview.toPlainText()
        self._sync_dirty_state()

    def mark_save_failed(self, message: str = "保存失败") -> None:
        self.save_status.setText(message)
        self.save_btn.setEnabled(True)

    def _request_save(self) -> None:
        text = self.preview.toPlainText()
        self.save_status.setText("保存中")
        self.save_btn.setEnabled(False)
        self.save_requested.emit(text)

    def _sync_dirty_state(self) -> None:
        dirty = self.preview.toPlainText() != self._saved_text
        self.save_status.setText("已修改" if dirty else "已保存")
        self.save_btn.setEnabled(dirty)

    def _close_dialog(self) -> None:
        if self._confirm_discard_changes():
            self.accept()

    def _confirm_discard_changes(self) -> bool:
        if self.preview.toPlainText() == self._saved_text:
            return True
        answer = QMessageBox.question(
            self,
            "有未保存修改",
            "当前文本还没有保存，确认关闭？",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        return answer == QMessageBox.Yes

    def reject(self) -> None:
        if self._confirm_discard_changes():
            super().reject()

    def closeEvent(self, event) -> None:
        if self._confirm_discard_changes():
            event.accept()
        else:
            event.ignore()
