from __future__ import annotations

from PyQt5.QtCore import QTimer
from PyQt5.QtGui import QResizeEvent
from PyQt5.QtWidgets import QApplication


class MainWindowLayoutMixin:
    def _apply_adaptive_window_size(self) -> None:
        screen = QApplication.primaryScreen()
        if not screen:
            self.resize(1560, 1020)
            self.setMinimumSize(1180, 760)
            return

        available = screen.availableGeometry()
        width = min(max(1680, int(available.width() * 0.995)), available.width(), 1900)
        minimum_default_height = 920 if available.height() < 1000 else 1040
        height = min(max(minimum_default_height, min(int(available.height() * 0.985), 1280)), available.height())

        min_width = min(1480, max(1060, int(available.width() * 0.82)))
        min_height = min(760, max(620, int(available.height() * 0.72)))

        self.resize(width, height)
        self.setMinimumSize(min_width, min_height)
        self.move(
            available.x() + max(0, (available.width() - width) // 2),
            available.y() + max(0, (available.height() - height) // 2),
        )

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)
        position_task_toast = getattr(self, "_position_task_toast", None)
        if callable(position_task_toast):
            position_task_toast()
        if not self._user_adjusted_log_splitter:
            QTimer.singleShot(0, self._fit_log_splitter_to_window)

    def _adaptive_sidebar_width(self) -> int:
        screen = QApplication.primaryScreen()
        if not screen:
            return 190
        available_width = screen.availableGeometry().width()
        return min(224, max(188, int(available_width * 0.112)))

    def _mark_log_splitter_adjusted(self, _pos: int, _index: int) -> None:
        if not self._fitting_log_splitter:
            self._user_adjusted_log_splitter = True

    def _fit_log_splitter_to_window(self) -> None:
        total_height = self.main_splitter.height()
        if total_height <= 0:
            return
        if not getattr(self, "log_expanded", True):
            log_height = 54
            content_height = max(320, total_height - log_height)
            self._fitting_log_splitter = True
            try:
                self.main_splitter.setSizes([content_height, log_height])
            finally:
                self._fitting_log_splitter = False
            return
        ratio = 0.28 if self.height() >= 1000 else 0.24
        log_height = int(total_height * ratio)
        log_height = max(120, min(360, log_height))
        if total_height < 720:
            log_height = min(log_height, 120)
        elif self.height() < 820:
            log_height = min(log_height, 140)
        if self.width() < 1200:
            log_height = min(log_height, 120)
        content_height = max(320, total_height - log_height)
        if content_height + log_height > total_height:
            log_height = max(120, total_height - content_height)
        self._fitting_log_splitter = True
        try:
            self.main_splitter.setSizes([content_height, log_height])
        finally:
            self._fitting_log_splitter = False
