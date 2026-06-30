from __future__ import annotations

from PyQt5.QtCore import QProcess, QSignalBlocker, Qt

from dog_remote_tool.core.shell import CommandSpec
from dog_remote_tool.modules import mapping
from dog_remote_tool.ui import map_helpers
from .map_history_card import RouteMapHistoryCard as RouteMapHistoryCard
from .map_history_cards import RouteNetworkMapHistoryCardsMixin
from .map_history_fetch import RouteNetworkMapHistoryFetchMixin
from .map_history_selection import RouteNetworkMapHistorySelectionMixin
from .map_history_sync import RouteNetworkMapHistorySyncMixin
from .map_history_thumbnails import RouteNetworkMapHistoryThumbnailsMixin


__all__ = ["RouteMapHistoryCard", "RouteNetworkMapHistoryMixin"]


class RouteNetworkMapHistoryMixin(
    RouteNetworkMapHistoryCardsMixin,
    RouteNetworkMapHistoryFetchMixin,
    RouteNetworkMapHistoryThumbnailsMixin,
    RouteNetworkMapHistorySelectionMixin,
    RouteNetworkMapHistorySyncMixin,
):
    def refresh_history_map_list(self) -> bool:
        if self.history_map_slot.is_running():
            return False
        profile = self.profile()
        save_map_path = mapping.default_save_map_path(profile)
        process, request_id = self.history_map_slot.start_spec(
            CommandSpec(
                "读取路网历史地图",
                mapping.list_map_pgm_command(profile, save_map_path),
                concurrency="parallel",
                locks=("route-map-history",),
            )
        )
        if process is None:
            return False
        process.readyReadStandardOutput.connect(lambda: self.read_history_map_output(process, request_id))
        process.finished.connect(lambda exit_code, _status: self.history_map_list_finished(process, exit_code, request_id))
        process.start()
        self.set_status("刷新地图", "warning")
        return True

    def read_history_map_output(self, process: QProcess, request_id: int) -> bool:
        return self.history_map_slot.read_available_output(process, request_id)

    def history_map_list_finished(self, process: QProcess, exit_code: int, request_id: int) -> bool:
        output = self.history_map_slot.finish(process, request_id)
        if output is None:
            return False
        if exit_code != 0:
            self.set_status("地图读取失败", "error")
            self.selected_history_detail.setText((output.strip() or "远端历史图读取失败")[:240])
            return True
        self.history_map_list_loaded_once = True
        entries = map_helpers.parse_history_map_entries(output)
        current = self.selected_history_map_pgm()
        previous_signature = self.history_map_entries_signature
        self.history_map_entries_signature = tuple(entries)
        self.history_map_details = {remote_path: detail for _label, remote_path, detail in entries}
        signature_changed = self.history_map_entries_signature != previous_signature
        if entries and not signature_changed:
            self.update_history_map_card_selection()
            self.sync_selected_history_paths(load_existing=True)
            self.set_status("地图已刷新", "ready")
            return True
        with QSignalBlocker(self.history_map_selector):
            self.history_map_selector.clear()
            for label, remote_path, detail in entries:
                self.history_map_selector.addItem(label, remote_path)
                self.history_map_selector.setItemData(self.history_map_selector.count() - 1, detail, Qt.ToolTipRole)
            if current:
                index = self.history_map_selector.findData(current)
                if index >= 0:
                    self.history_map_selector.setCurrentIndex(index)
            if entries and self.history_map_selector.currentIndex() < 0:
                self.history_map_selector.setCurrentIndex(0)
        if entries:
            self.update_history_map_cards(entries)
            self.sync_selected_history_paths(load_existing=True)
            self.set_status("地图已刷新", "ready")
        else:
            self.clear_history_map_cards()
            self.selected_history_detail.setText("远端目录：未发现历史图")
            self.set_status("无地图", "warning")
        return True

    def on_history_map_changed(self) -> None:
        self.update_history_map_card_selection()
        self.sync_selected_history_paths(load_existing=True)
