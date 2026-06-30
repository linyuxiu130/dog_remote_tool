from __future__ import annotations

import shutil
from pathlib import Path, PurePosixPath

from PyQt5.QtWidgets import QFileDialog, QMessageBox

from dog_remote_tool.modules.navigation import route_network
from dog_remote_tool.ui.pages.navigation.map_history import NavigationMapHistoryMixin
from dog_remote_tool.ui.pages.navigation.page_refs import navigation_page_class


class NavigationRouteFileLocalMixin:
    def clear_route_targets_after_route_update(self) -> bool:
        self.goal_point_selected = False
        self.route_target_node_ids = []
        self.added_waypoint_undo_stack = []
        if hasattr(self, "waypoints_text"):
            self.waypoints_text.setPlainText("")
        if callable(getattr(self.nav_map, "set_points", None)):
            self.nav_map.set_points([])
        if callable(getattr(self.nav_map, "set_route_target_node_ids", None)):
            self.nav_map.set_route_target_node_ids([])
        refresh_points = getattr(self, "refresh_navigation_points_list", None)
        if callable(refresh_points):
            refresh_points()
        dialog = getattr(self, "workspace_dialog", None)
        if dialog is not None:
            if callable(getattr(dialog.canvas, "set_points", None)):
                dialog.canvas.set_points([])
            if callable(getattr(dialog.canvas, "set_route_target_node_ids", None)):
                dialog.canvas.set_route_target_node_ids([])
            refresh_list = getattr(dialog, "refresh_point_list", None)
            if callable(refresh_list):
                refresh_list()
        self.refresh_workspace_from_page()
        return True

    def load_local_route_overlay(self, remote_pgm: str) -> bool:
        local_route = NavigationMapHistoryMixin.local_route_geojson_path(self, remote_pgm)
        if local_route is None or not local_route.exists():
            return False
        try:
            graph = route_network.load_geojson(local_route)
        except Exception as exc:
            self.route_graph = None
            self.route_graph_remote_pgm = ""
            self.route_graph_local_path = ""
            self.route_target_mode = False
            self.route_target_node_ids = []
            self.added_waypoint_undo_stack = []
            if callable(getattr(self.nav_map, "set_route_graph", None)):
                self.nav_map.set_route_graph(None)
                self.nav_map.set_route_target_node_ids([])
            self.nav_status_note.setText(f"路网加载失败：{exc}")
            page = navigation_page_class()
            page._log_route_event(self, f"[路网] 本地 map.geojson 加载失败：{exc}")
            self.refresh_workspace_from_page()
            return False
        self.route_graph = graph
        self.route_graph_remote_pgm = remote_pgm
        self.route_graph_local_path = str(local_route)
        self.route_target_mode = True
        self.route_target_node_ids = []
        self.added_waypoint_undo_stack = []
        if callable(getattr(self.nav_map, "set_route_graph", None)):
            self.nav_map.set_route_graph(graph)
            self.nav_map.set_route_target_node_ids([])
        dialog = getattr(self, "workspace_dialog", None)
        if dialog is not None:
            dialog.canvas.set_route_graph(graph)
            dialog.canvas.set_route_target_node_ids([])
        NavigationRouteFileLocalMixin.clear_route_targets_after_route_update(self)
        self.update_target_hint()
        self.nav_status_note.setText(f"路网已加载：{len(graph.nodes)} 个节点 / {len(graph.edges)} 条边，请点击路网节点附近设定目标")
        page = navigation_page_class()
        page._log_route_event(self, f"[路网] 已加载路网叠加：{local_route}")
        page._update_route_action_buttons(self)
        self.refresh_workspace_from_page()
        return True

    def handle_local_route_geojson_updated(self, remote_pgm: str, local_route: str | Path | None = None) -> bool:
        if not remote_pgm:
            return False
        if remote_pgm != self.selected_map_pgm():
            return False
        visible = (
            bool(getattr(self, "route_target_mode", False))
            and getattr(self, "route_graph", None) is not None
            and getattr(self, "route_graph_remote_pgm", "") == remote_pgm
        )
        if not visible:
            return False
        reloaded = navigation_page_class().load_local_route_overlay(self, remote_pgm)
        if reloaded:
            NavigationRouteFileLocalMixin.clear_route_targets_after_route_update(self)
            suffix = f"：{local_route}" if local_route else ""
            self.nav_status_note.setText("路网已更新，原有路网目标点已清空，请重新选择目标节点")
            navigation_page_class()._log_route_event(self, f"[路网] 本地路网已更新，地图叠加已刷新{suffix}")
        return reloaded

    def choose_local_route_geojson(self) -> bool:
        remote_pgm = self.selected_map_pgm()
        if not remote_pgm:
            QMessageBox.information(self, "未选择历史图", "请先选择一个历史图。")
            return False
        filename, _selected_filter = QFileDialog.getOpenFileName(
            self,
            "导入本地路网文件",
            str(Path.home()),
            "GeoJSON (*.geojson *.json);;所有文件 (*)",
        )
        if not filename:
            return False
        source = Path(filename)
        local_route = NavigationMapHistoryMixin.local_route_geojson_path(self, remote_pgm)
        if local_route is None:
            return False
        try:
            local_route.parent.mkdir(parents=True, exist_ok=True)
            if source.resolve() != local_route.resolve():
                shutil.copyfile(source, local_route)
        except OSError as exc:
            QMessageBox.warning(self, "选择路网失败", f"无法复制本地路网文件：{exc}")
            return False
        self.route_geojson_path.setText(route_network.route_geojson_for_remote_map(remote_pgm))
        if self.route_file_states.get(remote_pgm) is not True:
            self.route_file_states[remote_pgm] = False
        self.nav_status_note.setText("已导入本地路网，请点击“上传路网”同步到机器人后再路网导航")
        page = navigation_page_class()
        page._log_route_event(self, f"[路网] 已关联本地路网：{local_route}")
        page.handle_local_route_geojson_updated(self, remote_pgm, local_route)
        page._update_route_action_buttons(self)
        self.refresh_workspace_from_page()
        return True

    def export_selected_route_geojson(self) -> bool:
        remote_pgm = self.selected_map_pgm()
        if not remote_pgm:
            QMessageBox.information(self, "未选择历史图", "请先选择一个历史图。")
            return False
        local_route = NavigationMapHistoryMixin.local_route_geojson_path(self, remote_pgm)
        if local_route is None or not local_route.exists():
            QMessageBox.information(self, "没有本地路网", "请先点击“编辑路网”并保存 map.geojson。")
            return False
        default_name = f"{PurePosixPath(remote_pgm).parent.name or 'map'}_map.geojson"
        filename, _selected_filter = QFileDialog.getSaveFileName(
            self,
            "导出路网文件",
            str(Path.home() / default_name),
            "GeoJSON (*.geojson);;所有文件 (*)",
        )
        if not filename:
            return False
        target = Path(filename)
        if target.suffix == "":
            target = target.with_suffix(".geojson")
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            if local_route.resolve() != target.resolve():
                shutil.copyfile(local_route, target)
        except OSError as exc:
            QMessageBox.warning(self, "导出路网失败", f"无法导出路网文件：{exc}")
            return False
        self.nav_status_note.setText(f"路网已导出：{target.name}")
        navigation_page_class()._log_route_event(self, f"[路网] 已导出路网：{target.name}")
        self.refresh_workspace_from_page()
        return True
