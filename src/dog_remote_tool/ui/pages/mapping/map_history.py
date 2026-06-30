from __future__ import annotations

from pathlib import Path

from PyQt5.QtCore import QProcess, Qt, pyqtSignal
from PyQt5.QtGui import QPixmap
from PyQt5.QtWidgets import QFrame, QLabel, QVBoxLayout, QWidget

from dog_remote_tool.core.shell import CommandSpec
from dog_remote_tool.modules import mapping
from dog_remote_tool.ui.map_history_card import map_history_card_stylesheet
from dog_remote_tool.ui.map_helpers import compact_history_map_label
from dog_remote_tool.ui.thumbnail_helpers import load_thumbnail_pixmap, update_scaled_thumbnail


class MapHistoryCard(QFrame):
    clicked = pyqtSignal(str)

    def __init__(self, label: str, remote_pgm: str, detail: str) -> None:
        super().__init__()
        self.remote_pgm = remote_pgm
        self.setObjectName("MapHistoryCard")
        self.setCursor(Qt.PointingHandCursor)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setMinimumHeight(208)
        self.setMinimumWidth(180)
        self.setMaximumWidth(420)
        self.thumbnail_pixmap: QPixmap | None = None
        self.setToolTip(detail)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(7, 7, 7, 7)
        layout.setSpacing(5)
        self.thumbnail = QLabel("预览待加载")
        self.thumbnail.setAlignment(Qt.AlignCenter)
        self.thumbnail.setMinimumHeight(168)
        self.thumbnail.setObjectName("MapHistoryThumbnail")
        self.title = QLabel(MapHistoryCard.compact_label(label, remote_pgm))
        self.title.setAlignment(Qt.AlignCenter)
        self.title.setObjectName("MapHistoryTitle")
        layout.addWidget(self.thumbnail, 1)
        layout.addWidget(self.title)
        self.set_selected(False)

    @staticmethod
    def compact_label(label: str, remote_pgm: str) -> str:
        return compact_history_map_label(label, remote_pgm)

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.LeftButton:
            self.clicked.emit(self.remote_pgm)
            event.accept()
            return
        super().mousePressEvent(event)

    def keyPressEvent(self, event) -> None:
        if event.key() in (Qt.Key_Return, Qt.Key_Enter, Qt.Key_Space):
            self.clicked.emit(self.remote_pgm)
            event.accept()
            return
        super().keyPressEvent(event)

    def set_selected(self, selected: bool) -> None:
        self.setStyleSheet(
            map_history_card_stylesheet(
                selected,
                scoped_frame=True,
                thumbnail_padding=4,
                dynamic_thumbnail_bg=True,
                title_line_height="110%",
            )
        )

    def set_thumbnail_from_file(self, image_path: Path) -> bool:
        self.thumbnail_pixmap = load_thumbnail_pixmap(self.thumbnail, image_path)
        if self.thumbnail_pixmap is None:
            return False
        self.update_thumbnail_pixmap()
        return True

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self.update_thumbnail_pixmap()

    def update_thumbnail_pixmap(self) -> None:
        update_scaled_thumbnail(self.thumbnail, self.thumbnail_pixmap)


class MappingMapHistoryMixin:
    def selected_remote_map_pgm(self) -> str:
        data = self.map_selector.currentData()
        return str(data or "")

    def on_map_selection_changed(self) -> None:
        MappingMapHistoryMixin.update_map_card_selection(self)
        self.update_selected_map_detail()
        self.fetch_selected_map_preview(force=False)

    def select_history_map(self, remote_pgm: str) -> bool:
        index = self.map_selector.findData(remote_pgm)
        if index < 0:
            return False
        if self.map_selector.currentIndex() == index:
            return True
        self.map_selector.setCurrentIndex(index)
        return True

    def update_selected_map_detail(self) -> None:
        remote_pgm = self.selected_remote_map_pgm()
        self.selected_map_detail.setText(self.map_entry_details.get(remote_pgm, "远端目录：--"))

    def clear_map_cards(self) -> None:
        layout = getattr(self, "map_cards_layout", None)
        if layout is None:
            return
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        self.map_cards = {}
        self.map_cards_panel.hide()
        self.map_cards_empty.show()

    def update_map_cards(self, entries: list[tuple[str, str, str]]) -> None:
        if not hasattr(self, "map_cards_layout"):
            return
        visible_entries = entries[:5]
        if not visible_entries:
            MappingMapHistoryMixin.clear_map_cards(self)
            self.map_cards_empty.setText("暂无历史图")
            return
        self.map_cards_empty.hide()
        self.map_cards_panel.show()
        visible_paths = {remote_pgm for _label, remote_pgm, _detail in visible_entries}
        existing = getattr(self, "map_cards", {})
        self.map_cards = {remote_pgm: card for remote_pgm, card in existing.items() if remote_pgm in visible_paths}
        while self.map_cards_layout.count():
            item = self.map_cards_layout.takeAt(0)
            widget = item.widget()
            if widget is None:
                continue
            remote_pgm = getattr(widget, "remote_pgm", "")
            if remote_pgm not in visible_paths:
                widget.deleteLater()
        card_count = max(3, len(visible_entries))
        for label, remote_pgm, detail in visible_entries:
            card = existing.get(remote_pgm)
            if card is None:
                card = MapHistoryCard(label, remote_pgm, detail)
                card.clicked.connect(self.select_history_map)
                self.map_cards[remote_pgm] = card
                self.update_map_card_thumbnail(remote_pgm)
            else:
                card.setToolTip(detail)
                card.title.setText(MapHistoryCard.compact_label(label, remote_pgm))
            self.map_cards[remote_pgm] = card
            self.map_cards_layout.addWidget(card, 1)
        for _index in range(card_count - len(visible_entries)):
            spacer = QWidget()
            spacer.setMaximumWidth(420)
            self.map_cards_layout.addWidget(spacer, 1)
        MappingMapHistoryMixin.update_map_card_selection(self)
        self.preload_map_card_thumbnails(visible_entries)

    def update_map_card_selection(self) -> None:
        selected = self.selected_remote_map_pgm()
        for remote_pgm, card in getattr(self, "map_cards", {}).items():
            card.set_selected(remote_pgm == selected)

    def update_map_card_thumbnail(self, remote_pgm: str, local_dir: Path | None = None) -> bool:
        card = getattr(self, "map_cards", {}).get(remote_pgm)
        if card is None:
            return False
        local_dir = local_dir or self.local_preview_dir(remote_pgm)
        return card.set_thumbnail_from_file(local_dir / "map.pgm")

    def preload_map_card_thumbnails(self, entries: list[tuple[str, str, str]]) -> None:
        if not hasattr(self, "map_thumbnail_slot"):
            return
        if self.map_thumbnail_slot.is_running():
            return
        profile = self.profile()
        selected = self.selected_remote_map_pgm()
        queue = []
        for _label, remote_pgm, _detail in entries[:5]:
            local_dir = self.local_preview_dir(remote_pgm, profile)
            if self._local_map_preview_cache_ready(local_dir):
                self.update_map_card_thumbnail(remote_pgm, local_dir)
            elif remote_pgm != selected and remote_pgm != self.fetching_preview_remote_pgm:
                queue.append(remote_pgm)
        self.map_thumbnail_queue = queue
        self.fetch_next_map_card_thumbnail()

    def fetch_next_map_card_thumbnail(self) -> bool:
        if not hasattr(self, "map_thumbnail_slot") or self.map_thumbnail_slot.is_running():
            return False
        while self.map_thumbnail_queue:
            remote_pgm = self.map_thumbnail_queue.pop(0)
            if remote_pgm not in getattr(self, "map_cards", {}):
                continue
            profile = self.profile()
            local_dir = self.local_preview_dir(remote_pgm, profile)
            if self._local_map_preview_cache_ready(local_dir):
                self.update_map_card_thumbnail(remote_pgm, local_dir)
                continue
            command = mapping.fetch_map_preview_files_command(profile, remote_pgm, str(local_dir))
            process, request_id = self.map_thumbnail_slot.start_spec(
                CommandSpec("拉取地图缩略图", command, concurrency="parallel", locks=("mapping-preview",))
            )
            if process is None:
                return False
            process.readyReadStandardOutput.connect(lambda: self.read_map_thumbnail_output(process, request_id))
            process.finished.connect(
                lambda exit_code, _status, remote=remote_pgm, path=local_dir: self.map_thumbnail_finished(
                    process, exit_code, remote, path, request_id
                )
            )
            process.start()
            return True
        return False

    def read_map_thumbnail_output(self, process: QProcess, request_id: int) -> bool:
        return self.map_thumbnail_slot.read_available_output(process, request_id)

    def map_thumbnail_finished(
        self,
        process: QProcess,
        exit_code: int,
        remote_pgm: str,
        local_dir: Path,
        request_id: int,
    ) -> bool:
        output = self.map_thumbnail_slot.finish(process, request_id)
        if output is None:
            return False
        if exit_code == 0:
            self.update_map_card_thumbnail(remote_pgm, local_dir)
        self.fetch_next_map_card_thumbnail()
        return True
