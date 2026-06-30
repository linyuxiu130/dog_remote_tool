from __future__ import annotations

from PyQt5.QtCore import QProcess
from PyQt5.QtWidgets import QMessageBox

from dog_remote_tool.core.shell import CommandSpec
from dog_remote_tool.modules.navigation import route_network
from dog_remote_tool.ui.pages.navigation.map_history import NavigationMapHistoryMixin
from dog_remote_tool.ui.pages.navigation.page_refs import navigation_page_class
from dog_remote_tool.ui.pages.navigation.status_helpers import _compact_failure_lines


class NavigationRouteFileRemoteMixin:
    def refresh_route_file_state(self, remote_pgm: str | None = None) -> bool:
        remote_pgm = remote_pgm or self.selected_map_pgm()
        if not remote_pgm:
            self.refresh_workspace_from_page()
            return False
        if self.route_check_slot.is_running():
            self.refresh_workspace_from_page()
            return False
        self.route_check_remote_pgm = remote_pgm
        remote_route = route_network.route_geojson_for_remote_map(remote_pgm)
        process, request_id = self.route_check_slot.start_spec(
            CommandSpec(
                "检查远端路网文件",
                route_network.route_file_exists_command(self.profile(), remote_route),
                concurrency="parallel",
                locks=("navigation-route-file",),
            )
        )
        if process is None:
            return False
        process.readyReadStandardOutput.connect(lambda: self.read_route_check_output(process, request_id))
        process.finished.connect(lambda exit_code, _status: self.route_check_finished(process, exit_code, remote_pgm, request_id))
        process.start()
        self.refresh_workspace_from_page()
        return True

    def read_route_check_output(self, process: QProcess, request_id: int) -> bool:
        return self.route_check_slot.read_available_output(process, request_id)

    def route_check_finished(self, process: QProcess, exit_code: int, remote_pgm: str, request_id: int) -> bool:
        output = self.route_check_slot.finish(process, request_id)
        if output is None:
            return False
        self.route_file_states[remote_pgm] = exit_code == 0 and "ROUTE_FILE_OK=1" in output.splitlines()
        if self.route_check_remote_pgm == remote_pgm:
            self.route_check_remote_pgm = ""
        update_buttons = getattr(self, "update_navigation_action_buttons", None)
        if callable(update_buttons) and hasattr(self, "last_status_values"):
            update_buttons(self.last_status_values)
        self.refresh_workspace_from_page()
        return True

    def pull_remote_route_overlay(self, remote_pgm: str) -> bool:
        if self.route_pull_slot.is_running():
            self.nav_status_note.setText("正在拉取路网，请稍候")
            self.refresh_workspace_from_page()
            return False
        local_route = NavigationMapHistoryMixin.local_route_geojson_path(self, remote_pgm)
        if local_route is None:
            return False
        remote_route = route_network.route_geojson_for_remote_map(remote_pgm)
        self.route_pull_remote_pgm = remote_pgm
        self.route_pull_local_file = str(local_route)
        process, request_id = self.route_pull_slot.start_spec(
            route_network.pull_route_file_command(self.profile(), remote_route, str(local_route))
        )
        if process is None:
            return False
        process.readyReadStandardOutput.connect(lambda: self.read_route_pull_output(process, request_id))
        process.finished.connect(lambda exit_code, _status: self.route_pull_finished(process, exit_code, remote_pgm, request_id))
        process.start()
        self.nav_status_note.setText("正在拉取远端路网并加载到地图")
        self.refresh_workspace_from_page()
        return True

    def read_route_pull_output(self, process: QProcess, request_id: int) -> bool:
        return self.route_pull_slot.read_available_output(process, request_id)

    def route_pull_finished(self, process: QProcess, exit_code: int, remote_pgm: str, request_id: int) -> bool:
        output = self.route_pull_slot.finish(process, request_id)
        if output is None:
            return False
        if remote_pgm != self.selected_map_pgm():
            return True
        if exit_code != 0:
            self.nav_status_note.setText("远端路网拉取失败，请先上传或检查 map.geojson")
            navigation_page_class()._log_route_event(self, "[路网] 远端路网拉取失败：" + _compact_failure_lines(output))
            self.refresh_workspace_from_page()
            return True
        self.route_file_states[remote_pgm] = True
        self.route_geojson_path.setText(route_network.route_geojson_for_remote_map(remote_pgm))
        navigation_page_class().load_local_route_overlay(self, remote_pgm)
        return True

    def ensure_route_target_mode(self) -> bool:
        remote_pgm = self.selected_map_pgm()
        if not remote_pgm:
            QMessageBox.information(self, "未选择历史图", "请先选择一个历史图。")
            return False
        if (
            getattr(self, "route_target_mode", False)
            and self.route_graph is not None
            and self.route_graph_remote_pgm == remote_pgm
        ):
            return True
        page = navigation_page_class()
        state = self.route_file_states.get(remote_pgm)
        if state is True:
            return page.pull_remote_route_overlay(self, remote_pgm)
        if page.load_local_route_overlay(self, remote_pgm):
            return True
        if state is None:
            self.refresh_route_file_state(remote_pgm)
            self.nav_status_note.setText("正在检查远端路网，检查完成后可进入路网目标模式")
        else:
            self.nav_status_note.setText("当前地图还没有可用路网，请先新建/上传 map.geojson")
        self.refresh_workspace_from_page()
        return False

    def exit_route_target_mode(self) -> bool:
        self.route_target_mode = False
        self.route_graph = None
        self.route_graph_remote_pgm = ""
        self.route_graph_local_path = ""
        self.route_target_node_ids = []
        self.added_waypoint_undo_stack = []
        self.goal_point_selected = False
        if hasattr(self, "waypoints_text"):
            self.waypoints_text.setPlainText("")
        if callable(getattr(self.nav_map, "set_route_graph", None)):
            self.nav_map.set_route_graph(None)
        if callable(getattr(self.nav_map, "set_route_target_node_ids", None)):
            self.nav_map.set_route_target_node_ids([])
        if callable(getattr(self.nav_map, "set_points", None)):
            self.nav_map.set_points([])
        dialog = getattr(self, "workspace_dialog", None)
        if dialog is not None:
            if callable(getattr(dialog.canvas, "set_route_graph", None)):
                dialog.canvas.set_route_graph(None)
            if callable(getattr(dialog.canvas, "set_route_target_node_ids", None)):
                dialog.canvas.set_route_target_node_ids([])
            if callable(getattr(dialog.canvas, "set_points", None)):
                dialog.canvas.set_points([])
            refresh_list = getattr(dialog, "refresh_point_list", None)
            if callable(refresh_list):
                refresh_list()
        refresh_points = getattr(self, "refresh_navigation_points_list", None)
        if callable(refresh_points):
            refresh_points()
        update_hint = getattr(self, "update_target_hint", None)
        if callable(update_hint):
            update_hint()
        update_buttons = getattr(self, "update_navigation_action_buttons", None)
        if callable(update_buttons):
            update_buttons(getattr(self, "last_status_values", {}))
        self.nav_status_note.setText("已退出路网导航模式，点位导航已恢复")
        self.refresh_workspace_from_page()
        return True

    def toggle_route_target_mode(self) -> bool:
        remote_pgm = self.selected_map_pgm()
        if (
            getattr(self, "route_target_mode", False)
            and getattr(self, "route_graph", None) is not None
            and getattr(self, "route_graph_remote_pgm", "") == remote_pgm
        ):
            return navigation_page_class().exit_route_target_mode(self)
        return navigation_page_class().ensure_route_target_mode(self)
