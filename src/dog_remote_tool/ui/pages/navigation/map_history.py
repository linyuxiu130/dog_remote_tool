from __future__ import annotations

from pathlib import Path, PurePosixPath

from PyQt5.QtCore import QProcess, QSignalBlocker
from PyQt5.QtWidgets import QWidget

from dog_remote_tool.core.shell import CommandSpec
from dog_remote_tool.modules import mapping
from dog_remote_tool.modules.navigation import route_network
from dog_remote_tool.ui.map_helpers import local_map_preview_dir
from dog_remote_tool.ui.pages.navigation.map_widgets import NavigationMapHistoryCard


class NavigationMapHistoryMixin:
    def selected_map_pgm(self) -> str:
        return str(self.map_selector.currentData() or "")

    def selected_route_geojson_path(self) -> str:
        remote_pgm = self.selected_map_pgm()
        if remote_pgm:
            return route_network.route_geojson_for_remote_map(remote_pgm)
        return self.route_geojson_path.text().strip() or route_network.DEFAULT_REMOTE_ROUTE_FILE

    def local_route_geojson_path(self, remote_pgm: str | None = None) -> Path | None:
        remote_pgm = remote_pgm or self.selected_map_pgm()
        if not remote_pgm:
            return None
        return self.local_preview_dir(remote_pgm) / "map.geojson"

    def sync_selected_route_geojson_path(self) -> str:
        route_path = NavigationMapHistoryMixin.selected_route_geojson_path(self)
        self.route_geojson_path.setText(route_path)
        return route_path

    def update_selected_map_detail(self) -> None:
        remote_pgm = self.selected_map_pgm()
        detail = self.map_details.get(remote_pgm, "远端目录：--")
        self.selected_map_detail.setText(detail)
        if callable(getattr(self.map_selector, "setToolTip", None)):
            self.map_selector.setToolTip(detail)
        self.update_map_card_selection()
        self.refresh_workspace_from_page()

    def workspace_map_title(self) -> str:
        remote_pgm = self.selected_map_pgm()
        if not remote_pgm:
            return "未选择地图"
        name = PurePosixPath(remote_pgm).parent.name
        parts = name.split("_")
        if len(parts) >= 6 and parts[0].isdigit() and len(parts[0]) == 4:
            return f"{parts[1]}-{parts[2]} {parts[3]}:{parts[4]}"
        return name or "历史图"

    def clear_selected_map_preview_if_stale(self, remote_pgm: str) -> None:
        if not remote_pgm or getattr(self, "preview_remote_pgm", "") == remote_pgm:
            return
        self.preview_remote_pgm = ""
        self.fetching_preview_remote_pgm = ""
        self.nav_map_preview_path = ""
        self.charging_docks = []
        if callable(getattr(self.nav_map, "set_charging_docks", None)):
            self.nav_map.set_charging_docks([])
        if callable(getattr(self.nav_map, "clear_map", None)):
            self.nav_map.clear_map("正在加载地图预览")
        if callable(getattr(self.nav_map, "setToolTip", None)):
            self.nav_map.setToolTip("")
        dialog = getattr(self, "workspace_dialog", None)
        if dialog is not None and callable(getattr(dialog.canvas, "clear_map", None)):
            dialog.canvas.clear_map("正在加载地图预览")
            dialog.canvas.set_charging_docks([])
            dialog.canvas.set_global_route([])
            dialog.canvas.set_realtime_plan([])
            dialog.refresh_from_page()

    def select_history_map(self, remote_pgm: str) -> bool:
        index = self.map_selector.findData(remote_pgm)
        if index < 0:
            return False
        if self.map_selector.currentIndex() != index:
            if hasattr(self.map_selector, "blockSignals"):
                with QSignalBlocker(self.map_selector):
                    self.map_selector.setCurrentIndex(index)
            else:
                self.map_selector.setCurrentIndex(index)
        self.on_map_selection_changed()
        return True

    def open_history_map_workspace(self, remote_pgm: str) -> bool:
        select_history_map = getattr(self, "select_history_map", None)
        selected = (
            select_history_map(remote_pgm)
            if callable(select_history_map)
            else NavigationMapHistoryMixin.select_history_map(self, remote_pgm)
        )
        if not selected:
            return False
        self.open_navigation_workspace()
        return True

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
        self.clear_map_cards()
        visible_entries = entries[:5]
        if not visible_entries:
            self.map_cards_empty.setText("暂无历史图")
            return
        self.map_cards_empty.hide()
        self.map_cards_panel.show()
        card_count = max(3, len(visible_entries))
        for label, remote_pgm, detail in visible_entries:
            card = NavigationMapHistoryCard(label, remote_pgm, detail, self.open_history_map_workspace)
            self.map_cards[remote_pgm] = card
            self.map_cards_layout.addWidget(card, 1)
            self.update_map_card_thumbnail(remote_pgm)
        for _index in range(card_count - len(visible_entries)):
            spacer = QWidget()
            spacer.setMaximumWidth(430)
            self.map_cards_layout.addWidget(spacer, 1)
        self.update_map_card_selection()
        self.preload_map_card_thumbnails(visible_entries)

    def update_map_card_selection(self) -> None:
        selected = self.selected_map_pgm()
        for remote_pgm, card in getattr(self, "map_cards", {}).items():
            card.set_selected(remote_pgm == selected)

    def update_map_card_thumbnail(self, remote_pgm: str, local_dir: Path | None = None) -> bool:
        card = getattr(self, "map_cards", {}).get(remote_pgm)
        if card is None:
            return False
        local_dir = local_dir or self.local_preview_dir(remote_pgm)
        return card.set_thumbnail_from_file(local_dir / "map.pgm")

    def local_preview_dir(self, remote_pgm: str) -> Path:
        profile = self.profile()
        return local_map_preview_dir(profile.key, profile.host, remote_pgm, mapping.DEFAULT_LOCAL_MAP_DIR)

    def preload_map_card_thumbnails(self, entries: list[tuple[str, str, str]]) -> None:
        if self.map_thumbnail_slot.is_running():
            return
        queue = []
        for _label, remote_pgm, _detail in entries[:5]:
            local_dir = self.local_preview_dir(remote_pgm)
            if (local_dir / "map.pgm").exists() and (local_dir / "map.yaml").exists():
                self.update_map_card_thumbnail(remote_pgm, local_dir)
            else:
                queue.append(remote_pgm)
        self.map_thumbnail_queue = queue
        self.fetch_next_map_card_thumbnail()

    def fetch_next_map_card_thumbnail(self) -> bool:
        if self.map_thumbnail_slot.is_running():
            return False
        while self.map_thumbnail_queue:
            remote_pgm = self.map_thumbnail_queue.pop(0)
            if remote_pgm not in self.map_cards:
                continue
            local_dir = self.local_preview_dir(remote_pgm)
            if (local_dir / "map.pgm").exists() and (local_dir / "map.yaml").exists():
                self.update_map_card_thumbnail(remote_pgm, local_dir)
                continue
            process, request_id = self.map_thumbnail_slot.start_spec(
                CommandSpec(
                    "拉取导航地图缩略图",
                    mapping.fetch_map_preview_files_command(self.profile(), remote_pgm, str(local_dir)),
                    concurrency="parallel",
                    locks=("navigation-map-preview",),
                )
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

    def map_thumbnail_finished(self, process: QProcess, exit_code: int, remote_pgm: str, local_dir: Path, request_id: int) -> bool:
        output = self.map_thumbnail_slot.finish(process, request_id)
        if output is None:
            return False
        if exit_code == 0:
            self.update_map_card_thumbnail(remote_pgm, local_dir)
        self.fetch_next_map_card_thumbnail()
        return True
