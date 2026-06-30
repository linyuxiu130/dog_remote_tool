from __future__ import annotations

from pathlib import Path

from PyQt5.QtCore import QProcess, QTimer
from PyQt5.QtGui import QPixmap

from dog_remote_tool.core.shell import CommandSpec
from dog_remote_tool.modules import mapping
from dog_remote_tool.modules.navigation import route_network
from dog_remote_tool.ui.map_helpers import local_map_preview_dir
from dog_remote_tool.ui.navigation_helpers import read_map_yaml_charging_docks, read_map_yaml_metadata
from dog_remote_tool.ui.route_inflation_overlay import (
    DEFAULT_ROUTE_INFLATION_RADIUS_M,
    InflationOverlay,
    create_inflation_overlay,
)
from dog_remote_tool.ui.pages.navigation.status_helpers import _status_allows_selected_map_pose_display


class NavigationMapPreviewMixin:
    def _update_preview_action_buttons(self) -> bool:
        update = getattr(self, "update_navigation_action_buttons", None)
        if not callable(update):
            return False
        update(getattr(self, "last_status_values", {}))
        return True

    def clear_selected_map_pose_overlays(self) -> None:
        self.robot_pose = None
        self.navigation_global_route = []
        self.navigation_realtime_plan = []
        self.navigation_global_plan_topic = ""
        self.navigation_realtime_plan_topic = ""
        self.update_robot_pose_on_maps()
        if callable(getattr(self.nav_map, "set_global_route", None)):
            self.nav_map.set_global_route([])
        if callable(getattr(self.nav_map, "set_realtime_plan", None)):
            self.nav_map.set_realtime_plan([])
        dialog = getattr(self, "workspace_dialog", None)
        if dialog is not None:
            dialog.canvas.set_global_route([])
            dialog.canvas.set_realtime_plan([])
            dialog.refresh_from_page()

    def clear_selected_map_target_points(self) -> None:
        self.goal_point_selected = False
        self.route_target_node_ids = []
        self.added_waypoint_undo_stack = []
        waypoints_text = getattr(self, "waypoints_text", None)
        if callable(getattr(waypoints_text, "setPlainText", None)):
            waypoints_text.setPlainText("")
        nav_map = getattr(self, "nav_map", None)
        if callable(getattr(nav_map, "set_points", None)):
            nav_map.set_points([])
        if callable(getattr(nav_map, "set_route_target_node_ids", None)):
            nav_map.set_route_target_node_ids([])
        refresh_list = getattr(self, "refresh_navigation_points_list", None)
        if callable(refresh_list):
            refresh_list()
        dialog = getattr(self, "workspace_dialog", None)
        if dialog is not None:
            if callable(getattr(dialog.canvas, "set_points", None)):
                dialog.canvas.set_points([])
            if callable(getattr(dialog.canvas, "set_route_target_node_ids", None)):
                dialog.canvas.set_route_target_node_ids([])
            refresh_point_list = getattr(dialog, "refresh_point_list", None)
            if callable(refresh_point_list):
                refresh_point_list()
        refresh_workspace = getattr(self, "refresh_workspace_from_page", None)
        if callable(refresh_workspace):
            refresh_workspace()

    def reset_selected_map_runtime_state(self) -> None:
        self.last_status_values = {}
        self.last_status_state = "unknown"
        self.last_status_at = 0.0
        self.prepared_map_pcd_path = ""
        self.map_prepare_error = ""
        self.map_prepare_auto_retry_pcd = ""
        self.route_graph = None
        self.route_graph_remote_pgm = ""
        self.route_graph_local_path = ""
        self.route_target_mode = False
        NavigationMapPreviewMixin.clear_selected_map_target_points(self)
        if callable(getattr(self.nav_map, "set_route_graph", None)):
            self.nav_map.set_route_graph(None)
            self.nav_map.set_route_target_node_ids([])
        self.pending_navigation_action = ""
        self.navigation_tracking_enabled = False
        self.navigation_tracking_active_seen = False
        self.charging_docks = []
        if callable(getattr(self.nav_map, "set_charging_docks", None)):
            self.nav_map.set_charging_docks([])
        if callable(getattr(self.nav_map, "set_route_graph", None)):
            self.nav_map.set_route_graph(None)
            self.nav_map.set_route_target_node_ids([])
        NavigationMapPreviewMixin.clear_selected_map_pose_overlays(self)
        self.set_cards_from_values({})

    def robot_pose_display_ready(self) -> bool:
        map_pcd = self.map_pcd_path.text().strip() if hasattr(self, "map_pcd_path") else ""
        if not map_pcd:
            return False
        if self.prepared_map_pcd_path == map_pcd:
            return True
        return _status_allows_selected_map_pose_display(getattr(self, "last_status_values", {}) or {}, map_pcd)

    def handle_robot_pose_update(self, pose: tuple[float, float, float]) -> None:
        if not NavigationMapPreviewMixin.robot_pose_display_ready(self):
            if self.robot_pose is not None:
                self.robot_pose = None
                self.update_robot_pose_on_maps()
            return
        self.robot_pose = pose
        self.update_robot_pose_on_maps()

    def open_navigation_map_preview(self) -> bool:
        return self.open_navigation_workspace()

    def fetch_navigation_map_preview(self, *, force: bool = False) -> bool:
        if not self.page_active or not self.navigation_supported():
            return False
        remote_pgm = self.selected_map_pgm()
        if not remote_pgm:
            return False
        profile = self.profile()
        local_dir = local_map_preview_dir(
            profile.key,
            profile.host,
            remote_pgm,
            mapping.DEFAULT_LOCAL_MAP_DIR,
        )
        map_file = local_dir / "map.pgm"
        yaml_file = local_dir / "map.yaml"
        current_pixmap = getattr(self.nav_map, "source_pixmap", None)
        if (
            not force
            and getattr(self, "preview_remote_pgm", "") == remote_pgm
            and current_pixmap is not None
            and not current_pixmap.isNull()
        ):
            return False
        if not force and map_file.is_file() and yaml_file.is_file():
            self.fetching_preview_remote_pgm = remote_pgm
            self.nav_map_preview_path = str(map_file)
            return NavigationMapPreviewMixin._load_navigation_map_preview_from_local(self, local_dir, remote_pgm)
        if self.map_preview_slot.is_running():
            running_remote = getattr(self, "fetching_preview_remote_pgm", "")
            if not force and running_remote == remote_pgm:
                return False
            self.map_preview_slot.stop()
        self.fetching_preview_remote_pgm = remote_pgm
        self.nav_map_preview_path = str(map_file)
        self.nav_map.setText("正在加载地图预览")
        process, request_id = self.map_preview_slot.start_spec(
            CommandSpec(
                "拉取导航地图预览",
                mapping.fetch_map_preview_files_command(profile, remote_pgm, str(local_dir)),
                concurrency="parallel",
                locks=("navigation-map-preview",),
            )
        )
        if process is None:
            return False
        process.readyReadStandardOutput.connect(lambda: self.read_map_preview_output(process, request_id))
        process.finished.connect(lambda exit_code, _status: self.map_preview_finished(process, exit_code, local_dir, request_id))
        process.start()
        return True

    def read_map_preview_output(self, process: QProcess, request_id: int) -> bool:
        return self.map_preview_slot.read_available_output(process, request_id)

    def map_preview_finished(self, process: QProcess, exit_code: int, local_dir: Path, request_id: int) -> None:
        output = self.map_preview_slot.finish(process, request_id)
        if output is None:
            return
        fetched_remote_pgm = getattr(self, "fetching_preview_remote_pgm", "")
        self.fetching_preview_remote_pgm = ""
        if fetched_remote_pgm and fetched_remote_pgm != self.selected_map_pgm():
            self.fetch_navigation_map_preview()
            return
        if exit_code != 0:
            self.preview_remote_pgm = ""
            self.charging_docks = []
            if callable(getattr(self.nav_map, "set_charging_docks", None)):
                self.nav_map.set_charging_docks([])
            self.nav_map.clear_map("地图预览加载失败")
            self.nav_map.setToolTip(output.strip())
            self.nav_status_note.setText("地图预览加载失败")
            self.open_workspace_after_preview = False
            return
        NavigationMapPreviewMixin._load_navigation_map_preview_from_local(self, local_dir, fetched_remote_pgm)

    def _load_navigation_map_preview_from_local(self, local_dir: Path, remote_pgm: str) -> bool:
        map_file = local_dir / "map.pgm"
        yaml_file = local_dir / "map.yaml"
        pixmap = QPixmap(str(map_file))
        metadata = read_map_yaml_metadata(str(yaml_file))
        if pixmap.isNull() or not metadata:
            self.preview_remote_pgm = ""
            self.charging_docks = []
            if callable(getattr(self.nav_map, "set_charging_docks", None)):
                self.nav_map.set_charging_docks([])
            self.nav_map.clear_map("地图预览不可用")
            self.nav_status_note.setText("地图预览不可用")
            self.open_workspace_after_preview = False
            return False
        resolution, origin = metadata
        charging_docks = read_map_yaml_charging_docks(str(yaml_file))
        self.preview_remote_pgm = remote_pgm or self.selected_map_pgm()
        self.nav_map.set_map(pixmap, resolution, origin)
        safety_overlay = NavigationMapPreviewMixin.create_navigation_safety_overlay(str(yaml_file))
        if callable(getattr(self.nav_map, "set_safety_overlay", None)):
            self.nav_map.set_safety_overlay(safety_overlay)
        self.charging_docks = charging_docks
        self.nav_map.set_charging_docks(charging_docks)
        dialog = getattr(self, "workspace_dialog", None)
        if dialog is not None:
            dialog.canvas.set_map(pixmap, resolution, origin)
            nudge_map = getattr(dialog, "_nudge_workspace_map_view_right", None)
            if callable(nudge_map):
                nudge_map()
            if callable(getattr(dialog.canvas, "set_safety_overlay", None)):
                dialog.canvas.set_safety_overlay(safety_overlay)
            dialog.canvas.set_global_route(self.navigation_global_route)
            dialog.canvas.set_realtime_plan(self.navigation_realtime_plan)
            dialog.canvas.set_charging_docks(charging_docks)
            sync_map_pip = getattr(dialog, "_sync_workspace_map_pip", None)
            if callable(sync_map_pip):
                sync_map_pip()
        self.update_target_hint()
        dock_note = f"，已显示 {len(charging_docks)} 个充电桩标记" if charging_docks else ""
        self.nav_status_note.setText(f"地图已加载{dock_note}，确认后可开始导航")
        NavigationMapPreviewMixin._update_preview_action_buttons(self)
        self.update_nav_map_points()
        if self.open_workspace_after_preview:
            self.open_workspace_after_preview = False
            QTimer.singleShot(0, self.open_navigation_workspace)
        return True

    @staticmethod
    def create_navigation_safety_overlay(yaml_path: str) -> InflationOverlay | None:
        try:
            metadata = route_network.read_map_yaml(yaml_path)
            return create_inflation_overlay(metadata, radius_m=DEFAULT_ROUTE_INFLATION_RADIUS_M)
        except Exception:
            return None

    def refresh_navigation_safety_overlay(self) -> bool:
        pgm_path = getattr(self, "nav_map_preview_path", "")
        if not pgm_path:
            return False
        yaml_file = Path(pgm_path).with_name("map.yaml")
        if not yaml_file.exists():
            return False
        safety_overlay = NavigationMapPreviewMixin.create_navigation_safety_overlay(str(yaml_file))
        if callable(getattr(self.nav_map, "set_safety_overlay", None)):
            self.nav_map.set_safety_overlay(safety_overlay)
        dialog = getattr(self, "workspace_dialog", None)
        if dialog is not None and callable(getattr(dialog.canvas, "set_safety_overlay", None)):
            dialog.canvas.set_safety_overlay(safety_overlay)
        return True
