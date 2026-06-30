from __future__ import annotations

from PyQt5.QtCore import QProcess

from dog_remote_tool.modules import mapping
from dog_remote_tool.modules import navigation
from dog_remote_tool.modules.navigation import route_network


def _navigation_page_class():
    from dog_remote_tool.ui.pages.navigation.page import NavigationPage

    return NavigationPage


def _navigation_page_module():
    from dog_remote_tool.ui.pages.navigation import page as navigation_page

    return navigation_page


class NavigationLifecycleMixin:
    def on_navigation_profile_changed(self, profile) -> None:
        page = _navigation_page_class()
        old_profile = getattr(self, "navigation_cleanup_profile", None)
        self.stop_navigation_camera_overlay()
        self._stop_refresh_processes(clear_maps=True)
        if old_profile is not None and old_profile != profile:
            page.cleanup_navigation_tool_helpers_detached(self, old_profile)
        self.navigation_cleanup_profile = profile
        self.save_map_path.setText(mapping.default_save_map_path(profile))
        self.map_pcd_path.setText(mapping.default_map_pcd_path(profile))
        self.route_geojson_path.setText(route_network.DEFAULT_REMOTE_ROUTE_FILE)
        self.last_status_values = {}
        self.last_status_state = "unknown"
        self.last_status_at = 0.0
        self.prepared_map_pcd_path = ""
        self.preparing_map_pcd_path = ""
        self.map_prepare_error = ""
        self.map_prepare_auto_retry_pcd = ""
        self.pending_navigation_action = ""
        self.navigation_loop_enabled = False
        self.robot_pose = None
        self.update_robot_pose_on_maps()
        self.set_cards_from_values({})
        if self.page_active:
            navigation_page = _navigation_page_module()
            self.refresh_map_list()
            self.start_pose_stream()
            self.start_plan_stream()
            navigation_page.QTimer.singleShot(600, self.start_navigation_camera_overlay)

    def activate_page(self) -> None:
        if self.page_active:
            return
        page = _navigation_page_class()
        navigation_page = _navigation_page_module()
        self.page_active = True
        self.refresh_selected_map_preview_once = True
        self.navigation_cleanup_profile = self.profile()
        navigation_page.QTimer.singleShot(100, self.ensure_navigation_helpers)
        navigation_page.QTimer.singleShot(150, self.refresh_map_list)
        navigation_page.QTimer.singleShot(600, self.start_navigation_camera_overlay)

    def deactivate_page(self) -> None:
        page = _navigation_page_class()
        self.page_active = False
        self.navigation_status_watch_running = False
        self.stop_navigation_camera_overlay()
        self._stop_refresh_processes(clear_maps=False)
        page.cleanup_navigation_tool_helpers_detached(self)

    def cleanup_navigation_tool_helpers_detached(self, profile=None) -> bool:
        cleanup_profile = profile or getattr(self, "navigation_cleanup_profile", None)
        if cleanup_profile is None:
            return False
        command = navigation.cleanup_navigation_tool_helpers_command(cleanup_profile).command
        command = f"{{ {command}; }} >/dev/null 2>&1"
        return QProcess.startDetached("bash", ["-lc", command])

    def _stop_refresh_processes(self, clear_maps: bool) -> None:
        navigation_page = _navigation_page_module()
        def stop_slot(slot) -> None:
            stop = getattr(slot, "stop_async", None) or getattr(slot, "stop", None)
            if callable(stop):
                stop()

        if getattr(self, "nav_camera_video_thread", None) is not None:
            self.stop_navigation_camera_overlay()
        stop_slot(self.status_slot)
        stop_slot(self.map_list_slot)
        stop_slot(self.map_preview_slot)
        map_prepare_slot = getattr(self, "map_prepare_slot", None)
        if map_prepare_slot is not None:
            stop_slot(map_prepare_slot)
        self.preparing_map_pcd_path = ""
        self.pending_navigation_action = ""
        self.navigation_loop_enabled = False
        stop_slot(self.route_check_slot)
        route_pull_slot = getattr(self, "route_pull_slot", None)
        if route_pull_slot is not None:
            stop_slot(route_pull_slot)
        pose_stream_slot = getattr(self, "pose_stream_slot", None)
        if pose_stream_slot is not None:
            stop_slot(pose_stream_slot)
        self.pose_stream_buffer = ""
        plan_stream_slot = getattr(self, "plan_stream_slot", None)
        if plan_stream_slot is not None:
            stop_slot(plan_stream_slot)
        self.plan_stream_buffer = ""
        obstacle_stream_slot = getattr(self, "obstacle_stream_slot", None)
        if obstacle_stream_slot is not None:
            stop_slot(obstacle_stream_slot)
        self.obstacle_stream_buffer = ""
        nav_camera_overlay_slot = getattr(self, "nav_camera_overlay_slot", None)
        if nav_camera_overlay_slot is not None:
            stop_slot(nav_camera_overlay_slot)
        self.nav_camera_overlay_buffer = ""
        nav_camera_overlay_store = getattr(self, "nav_camera_overlay_store", None)
        if nav_camera_overlay_store is not None:
            nav_camera_overlay_store.clear()
        nav_camera_timer = getattr(self, "nav_camera_frame_timer", None)
        if nav_camera_timer is not None:
            nav_camera_timer.stop()
        helper_slot = getattr(self, "mode_switch_helper_slot", None)
        if helper_slot is not None:
            stop_slot(helper_slot)
        thumbnail_slot = getattr(self, "map_thumbnail_slot", None)
        if thumbnail_slot is not None:
            stop_slot(thumbnail_slot)
        if clear_maps:
            self.map_entries_signature = ()
            self.map_details = {}
            self.preview_remote_pgm = ""
            self.map_thumbnail_queue = []
            self.route_file_states = {}
            self.route_check_remote_pgm = ""
            self.prepared_map_pcd_path = ""
            self.preparing_map_pcd_path = ""
            self.map_prepare_error = ""
            self.open_workspace_after_preview = False
            self.fetching_preview_remote_pgm = ""
            self.robot_pose = None
            self.navigation_global_route = []
            self.navigation_realtime_plan = []
            self.navigation_obstacle_points = []
            self.navigation_obstacle_topic = ""
            self.navigation_tracking_enabled = False
            self.navigation_tracking_active_seen = False
            self.navigation_status_watch_running = False
            self.navigation_command_task_id = None
            self.navigation_command_operation = ""
            self.navigation_global_plan_topic = ""
            self.navigation_realtime_plan_topic = ""
            self.nav_map.set_global_route([])
            self.nav_map.set_realtime_plan([])
            if callable(getattr(self.nav_map, "set_obstacle_points", None)):
                self.nav_map.set_obstacle_points([])
            clear_cards = getattr(self, "clear_map_cards", None)
            if callable(clear_cards):
                clear_cards()
            self.goal_point_selected = False
            with navigation_page.QSignalBlocker(self.map_selector):
                self.map_selector.clear()
            self.selected_map_detail.setText("远端目录：--")
            self.nav_map_preview_path = ""
            if callable(getattr(self.nav_map, "setToolTip", None)):
                self.nav_map.setToolTip("")
            self.nav_map.clear_map("选择历史图后加载预览")
            self.update_robot_pose_on_maps()

    def shutdown_processes(self) -> None:
        self.deactivate_page()
