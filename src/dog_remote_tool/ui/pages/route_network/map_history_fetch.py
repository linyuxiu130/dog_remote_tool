from __future__ import annotations

from pathlib import Path

from PyQt5.QtCore import QProcess, QTimer
from PyQt5.QtWidgets import QMessageBox

from dog_remote_tool.core.shell import CommandSpec
from dog_remote_tool.modules import mapping
from dog_remote_tool.modules.navigation import route_network


def notify_route_editor_status(page, message: str, state: str = "") -> None:
    callback = getattr(page, "route_editor_status_callback", None)
    if callable(callback):
        callback(message, state)


class RouteNetworkMapHistoryFetchMixin:
    def _notify_route_editor_status(self, message: str, state: str = "") -> None:
        notify_route_editor_status(self, message, state)

    def ensure_selected_history_preview(self, next_action: str) -> bool:
        remote_pgm = self.selected_history_map_pgm()
        if not remote_pgm:
            QMessageBox.information(self, "未选择历史地图", "请先刷新并选择一个历史图。")
            return False
        self.sync_selected_history_paths(load_existing=False)
        _local_pgm, local_yaml, _local_geojson = self.local_paths_for_history(remote_pgm)
        if local_yaml.exists() and self.load_map(str(local_yaml)):
            if next_action == "edit" and getattr(self, "require_remote_route_pull_before_edit", False):
                return self.ensure_selected_history_route(next_action)
            return True
        if self.history_map_fetch_slot.is_running():
            self.set_status("底图拉取中", "warning")
            return False
        local_dir = local_yaml.parent
        self.pending_history_action = next_action
        process, request_id = self.history_map_fetch_slot.start_spec(
            CommandSpec(
                "拉取路网底图",
                mapping.fetch_map_preview_files_command(self.profile(), remote_pgm, str(local_dir)),
                concurrency="parallel",
                locks=("route-map-fetch",),
            )
        )
        if process is None:
            return False
        process.readyReadStandardOutput.connect(lambda: self.read_history_map_fetch_output(process, request_id))
        process.finished.connect(lambda exit_code, _status: self.history_map_fetch_finished(process, exit_code, remote_pgm, local_yaml, request_id))
        process.start()
        self.set_status("拉取底图中", "warning")
        return False

    def read_history_map_fetch_output(self, process: QProcess, request_id: int) -> bool:
        return self.history_map_fetch_slot.read_available_output(process, request_id)

    def history_map_fetch_finished(self, process: QProcess, exit_code: int, remote_pgm: str, local_yaml: Path, request_id: int) -> bool:
        output = self.history_map_fetch_slot.finish(process, request_id)
        if output is None:
            return False
        action = self.pending_history_action
        self.pending_history_action = ""
        if remote_pgm != self.selected_history_map_pgm():
            self.sync_selected_history_paths(load_existing=True)
            return True
        if exit_code != 0 or not local_yaml.exists():
            self.set_status("底图拉取失败", "error")
            QMessageBox.information(self, "底图拉取失败", (output.strip() or "未能拉取所选历史地图")[:500])
            return True
        if not self.load_map(str(local_yaml)):
            return True
        if action == "edit" and getattr(self, "require_remote_route_pull_before_edit", False):
            self.ensure_selected_history_route(action)
            return True
        if action == "new":
            self.start_new_history_route(open_editor=True)
        elif action == "edit":
            self.open_route_editor()
        return True

    def ensure_selected_history_route(self, next_action: str) -> bool:
        remote_pgm = self.selected_history_map_pgm()
        if not remote_pgm:
            return False
        self.sync_selected_history_paths(load_existing=False)
        _local_pgm, _local_yaml, local_geojson = self.local_paths_for_history(remote_pgm)
        if self.history_route_fetch_slot.is_running():
            self.set_status("同步远端路网中", "warning")
            return False
        self.pending_history_route_action = next_action
        remote_route = route_network.route_geojson_for_remote_map(remote_pgm)
        spec = route_network.pull_route_file_command(self.profile(), remote_route, str(local_geojson))
        process, request_id = self.history_route_fetch_slot.start_spec(spec)
        if process is None:
            return False
        process.readyReadStandardOutput.connect(lambda: self.read_history_route_fetch_output(process, request_id))
        process.finished.connect(
            lambda exit_code, _status: self.history_route_fetch_finished(
                process, exit_code, remote_pgm, local_geojson, request_id
            )
        )
        process.start()
        self.set_status("同步远端路网中", "warning")
        notify_route_editor_status(self, "正在同步远端路网，完成后会自动打开编辑器", "warning")
        return False

    def read_history_route_fetch_output(self, process: QProcess, request_id: int) -> bool:
        return self.history_route_fetch_slot.read_available_output(process, request_id)

    def history_route_fetch_finished(self, process: QProcess, exit_code: int, remote_pgm: str, local_geojson: Path, request_id: int) -> bool:
        output = self.history_route_fetch_slot.finish(process, request_id)
        if output is None:
            return False
        action = self.pending_history_route_action
        self.pending_history_route_action = ""
        self.require_remote_route_pull_before_edit = False
        if remote_pgm != self.selected_history_map_pgm():
            self.sync_selected_history_paths(load_existing=True)
            return True
        if exit_code != 0 or not local_geojson.exists():
            self.set_status("路网拉取失败", "error")
            notify_route_editor_status(self, "远端路网同步失败，请检查 map.geojson 或重新上传", "error")
            if getattr(self, "route_editor_status_callback", None) is None:
                QMessageBox.information(self, "路网拉取失败", (output.strip() or "未能拉取远端 map.geojson")[:500])
            return True
        if not self.load_geojson(str(local_geojson)):
            notify_route_editor_status(self, "远端路网已同步，但本地加载失败", "error")
            return True
        if action == "edit":
            notify_route_editor_status(self, "远端路网已同步，正在打开编辑器", "ready")
            QTimer.singleShot(0, self.open_route_editor)
        elif action == "new":
            notify_route_editor_status(self, "远端路网已同步，正在打开编辑器", "ready")
            QTimer.singleShot(0, lambda: self.start_new_history_route(open_editor=True))
        return True
