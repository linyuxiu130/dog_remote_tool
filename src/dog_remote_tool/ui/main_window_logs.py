from __future__ import annotations

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QDialog, QHBoxLayout, QLabel, QPushButton, QSizePolicy, QTabWidget, QVBoxLayout

from .components import LogPanel


class MainWindowLogsMixin:
    def _append_log(self, text: str) -> None:
        self.log.append_text(text)
        self._update_log_summary(text)
        if self.log_fullscreen_view is not None:
            self.log_fullscreen_view.append_text(text)

    def _append_technical_log(self, text: str) -> None:
        self.technical_log.append_text(text)
        if self.log_fullscreen_technical_view is not None:
            self.log_fullscreen_technical_view.append_text(text)

    def clear_logs(self) -> None:
        self.log.clear()
        self.technical_log.clear()
        self.log_summary.setText("暂无执行日志")
        if self.log_fullscreen_view is not None:
            self.log_fullscreen_view.clear()
        if self.log_fullscreen_technical_view is not None:
            self.log_fullscreen_technical_view.clear()

    def toggle_log_panel(self) -> None:
        self.log_expanded = not self.log_expanded
        self.log.setVisible(self.log_expanded)
        self.log_toggle_btn.setText("收起日志" if self.log_expanded else "打开日志")
        self._user_adjusted_log_splitter = False
        self._fit_log_splitter_to_window()

    def _update_log_summary(self, text: str) -> None:
        clean = self.log.clean_text(text)
        lines = [line.strip() for line in clean.splitlines() if line.strip()]
        if not lines:
            return
        summary = lines[-1]
        if len(summary) > 120:
            summary = summary[:117] + "..."
        self.log_summary.setText(summary)

    def open_log_fullscreen(self) -> None:
        if self.log_fullscreen_dialog is not None:
            self.log_fullscreen_dialog.showFullScreen()
            self.log_fullscreen_dialog.raise_()
            self.log_fullscreen_dialog.activateWindow()
            return

        dialog = QDialog(self)
        dialog.setObjectName("ToolDialog")
        dialog.setWindowTitle("执行日志")
        dialog.setAttribute(Qt.WA_DeleteOnClose, True)
        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        header = QHBoxLayout()
        title = QLabel("执行日志")
        title.setObjectName("DialogTitle")
        close_button = QPushButton("退出全屏")
        close_button.setObjectName("SoftPrimary")
        close_button.clicked.connect(dialog.close)
        header.addWidget(title)
        header.addStretch(1)
        header.addWidget(close_button)

        tabs = QTabWidget()
        tabs.setObjectName("LogTabs")

        fullscreen_view = LogPanel(mode="user")
        fullscreen_view.setPlainText(self.log.toPlainText())
        fullscreen_view.moveCursor(fullscreen_view.textCursor().End)
        fullscreen_view.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        technical_view = LogPanel(mode="technical")
        technical_view.setPlainText(self.technical_log.toPlainText())
        technical_view.moveCursor(technical_view.textCursor().End)
        technical_view.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        tabs.addTab(fullscreen_view, "简洁日志")
        tabs.addTab(technical_view, "详细日志")

        layout.addLayout(header)
        layout.addWidget(tabs, 1)
        dialog.finished.connect(self._log_fullscreen_closed)
        self.log_fullscreen_dialog = dialog
        self.log_fullscreen_view = fullscreen_view
        self.log_fullscreen_technical_view = technical_view
        dialog.showFullScreen()

    def _log_fullscreen_closed(self, _result: int) -> None:
        self.log_fullscreen_dialog = None
        self.log_fullscreen_view = None
        self.log_fullscreen_technical_view = None
