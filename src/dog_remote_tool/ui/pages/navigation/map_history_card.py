from __future__ import annotations

from pathlib import Path, PurePosixPath

from PyQt5.QtCore import QSize, Qt
from PyQt5.QtGui import QPixmap
from PyQt5.QtWidgets import QFrame, QLabel, QVBoxLayout

from dog_remote_tool.ui.map_helpers import history_map_label_prefix, history_map_timestamp_label
from dog_remote_tool.ui.map_history_card import map_history_card_stylesheet
from dog_remote_tool.ui.thumbnail_helpers import load_thumbnail_pixmap, update_scaled_thumbnail


class NavigationMapHistoryCard(QFrame):
    def __init__(self, label: str, remote_pgm: str, detail: str, on_clicked) -> None:
        super().__init__()
        self.remote_pgm = remote_pgm
        self.on_clicked = on_clicked
        self.thumbnail_pixmap: QPixmap | None = None
        self.setCursor(Qt.PointingHandCursor)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setMinimumHeight(230)
        self.setMinimumWidth(190)
        self.setMaximumWidth(430)
        self.setToolTip(detail)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(6)
        self.thumbnail = QLabel("预览待加载")
        self.thumbnail.setAlignment(Qt.AlignCenter)
        self.thumbnail.setMinimumHeight(186)
        self.thumbnail.setObjectName("MapHistoryThumbnail")
        self.title = QLabel(self.compact_label(label, remote_pgm))
        self.title.setAlignment(Qt.AlignCenter)
        self.title.setObjectName("MapHistoryTitle")
        layout.addWidget(self.thumbnail, 1)
        layout.addWidget(self.title)
        self.set_selected(False)

    @staticmethod
    def compact_label(label: str, remote_pgm: str) -> str:
        compact = history_map_label_prefix(label)
        if compact:
            return compact
        timestamp = history_map_timestamp_label(remote_pgm)
        if timestamp:
            return timestamp
        return PurePosixPath(remote_pgm).parent.name or "地图"

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.LeftButton:
            self.on_clicked(self.remote_pgm)
            event.accept()
            return
        super().mousePressEvent(event)

    def keyPressEvent(self, event) -> None:
        if event.key() in (Qt.Key_Return, Qt.Key_Enter, Qt.Key_Space):
            self.on_clicked(self.remote_pgm)
            event.accept()
            return
        super().keyPressEvent(event)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self.update_thumbnail()

    def set_selected(self, selected: bool) -> None:
        self.setStyleSheet(map_history_card_stylesheet(selected, selected_border="#2f6fa8"))

    def set_thumbnail_from_file(self, image_path: Path) -> bool:
        self.thumbnail_pixmap = load_thumbnail_pixmap(self.thumbnail, image_path)
        if self.thumbnail_pixmap is None:
            return False
        self.update_thumbnail()
        return True

    def update_thumbnail(self) -> None:
        update_scaled_thumbnail(self.thumbnail, self.thumbnail_pixmap, QSize(320, 186))
