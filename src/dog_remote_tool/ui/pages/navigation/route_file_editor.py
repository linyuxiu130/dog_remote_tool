from __future__ import annotations

from pathlib import Path, PurePosixPath

from PyQt5.QtCore import QSignalBlocker, Qt
from PyQt5.QtWidgets import QFileDialog, QMessageBox

from dog_remote_tool.modules.navigation import route_network
from dog_remote_tool.ui.pages.navigation.map_history import NavigationMapHistoryMixin
from dog_remote_tool.ui.pages.navigation.map_widgets import NavigationMapHistoryCard


class NavigationRouteFileEditorMixin:
    def open_local_route_editor(self) -> bool:
        remote_pgm = self.selected_map_pgm()
        if remote_pgm:
            return self.open_route_editor_for_selected_map(force_local_edit=False)
        filename, _selected_filter = QFileDialog.getOpenFileName(
            self,
            "选择本地 map.yaml",
            str(Path.home()),
            "Map YAML (map.yaml *.yaml *.yml)",
        )
        if not filename:
            return False
        route_page = self._route_editor_backing_page()
        with QSignalBlocker(route_page.history_map_selector):
            route_page.history_map_selector.clear()
        route_page.history_map_details = {}
        route_page.selected_history_detail.setText("远端目录：未关联；选择远端历史图后保存会默认同步到机器人")
        route_page.remote_route_path.setText(route_network.DEFAULT_REMOTE_ROUTE_FILE)
        if not route_page.load_map(filename):
            return False
        local_geojson = Path(filename).with_name("map.geojson")
        route_page.geojson_path.setText(str(local_geojson))
        if local_geojson.exists():
            if not route_page.load_geojson(str(local_geojson)):
                return False
        else:
            route_page.new_graph()
        route_page.open_route_editor()
        self.nav_status_note.setText("已打开本地地图路网编辑；选择远端历史图后保存会默认同步到机器人")
        self.refresh_workspace_from_page()
        return True

    def open_route_editor_for_selected_map(self, *, force_local_edit: bool = False) -> bool:
        remote_pgm = self.selected_map_pgm()
        if not remote_pgm:
            QMessageBox.information(self, "未选择历史图", "请先选择一个历史图。")
            return False
        if not force_local_edit and self.route_action_label() == "检查路网":
            self.refresh_route_file_state(remote_pgm)
            return False
        route_page = self._route_editor_backing_page()
        label = NavigationMapHistoryCard.compact_label("", remote_pgm)
        detail = self.map_details.get(remote_pgm, f"目录：{PurePosixPath(remote_pgm).parent}")
        local_route = NavigationMapHistoryMixin.local_route_geojson_path(self, remote_pgm)
        route_page.history_map_details = {remote_pgm: detail}
        route_page.require_remote_route_pull_before_edit = (
            not force_local_edit and self.route_file_states.get(remote_pgm) is True
        )
        with QSignalBlocker(route_page.history_map_selector):
            route_page.history_map_selector.clear()
            route_page.history_map_selector.addItem(label, remote_pgm)
            route_page.history_map_selector.setItemData(0, detail, Qt.ToolTipRole)
            route_page.history_map_selector.setCurrentIndex(0)
        route_page.sync_selected_history_paths(load_existing=True)
        action = "edit" if local_route is not None and local_route.exists() else "new"
        if not force_local_edit and self.route_action_label() == "编辑路网":
            action = "edit"
        self.nav_status_note.setText("正在准备路网编辑")
        show_note = getattr(self.nav_status_note, "show", None)
        if callable(show_note):
            show_note()
        started_or_opened = route_page.ensure_selected_history_preview(action)
        if route_page.history_route_fetch_slot.is_running():
            self.nav_status_note.setText("正在同步远端路网，完成后会自动打开编辑器")
        elif route_page.history_map_fetch_slot.is_running():
            self.nav_status_note.setText("正在加载地图底图，完成后会自动打开编辑器")
        if started_or_opened:
            if action == "new":
                route_page.start_new_history_route(open_editor=True)
            else:
                route_page.open_route_editor()
        self.refresh_workspace_from_page()
        return (
            True
            if route_page.history_map_fetch_slot.is_running() or route_page.history_route_fetch_slot.is_running()
            else bool(started_or_opened)
        )

    def _route_editor_backing_page(self):
        page = getattr(self, "route_editor_page", None)
        if page is None:
            from dog_remote_tool.ui.pages.route_network.page import RouteNetworkPage

            page = RouteNetworkPage(self.runner, self.device_bar)
            page.hide()
            self.route_editor_page = page
        page.route_editor_status_callback = self._route_editor_status_changed
        page.route_saved_callback = lambda remote_pgm, local_path: self.handle_local_route_geojson_updated(
            remote_pgm, local_path
        )
        return page

    def _route_editor_status_changed(self, message: str, _state: str = "") -> None:
        if hasattr(self, "nav_status_note"):
            self.nav_status_note.setText(message)
            show_note = getattr(self.nav_status_note, "show", None)
            if callable(show_note):
                show_note()
        self.refresh_workspace_from_page()
