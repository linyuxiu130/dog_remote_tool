from __future__ import annotations

import time
from dataclasses import replace

from dog_remote_tool.modules import navigation
from dog_remote_tool.ui.pages.navigation.action_arc import NavigationArcActionsMixin
from dog_remote_tool.ui.pages.navigation.action_runner import NavigationActionRunnerMixin
from dog_remote_tool.ui.pages.navigation.action_safety import NavigationActionSafetyMixin
from dog_remote_tool.ui.pages.navigation.page_refs import navigation_page_class, navigation_page_module
from dog_remote_tool.ui.status_text import task_not_started_text


def _navigation_page_class():
    return navigation_page_class()


def _navigation_page_module():
    return navigation_page_module()


class NavigationActionsMixin(NavigationArcActionsMixin, NavigationActionSafetyMixin, NavigationActionRunnerMixin):
    def open_navigation_workspace(self) -> bool:
        page = _navigation_page_class()
        if self.workspace_dialog is not None:
            self.workspace_dialog.show_workspace_fullscreen()
            self.refresh_workspace_from_page()
            page.update_navigation_action_buttons(self, self.last_status_values)
            self.start_pose_stream()
            self.start_plan_stream()
            self.start_navigation_camera_overlay()
            return True
        dialog = _navigation_page_module().NavigationWorkspaceDialog(self)
        self.workspace_dialog = dialog
        dialog.finished.connect(lambda _code: self._workspace_closed(dialog))
        dialog.show_workspace_fullscreen()
        page.update_navigation_action_buttons(self, self.last_status_values)
        self.start_pose_stream()
        self.start_plan_stream()
        self.start_navigation_camera_overlay()
        return True

    def _workspace_closed(self, dialog) -> None:
        if dialog is self.workspace_dialog:
            self.workspace_dialog = None
            if not getattr(self, "navigation_tracking_enabled", False):
                self.stop_plan_stream()
                self.stop_obstacle_stream()

    def refresh_workspace_from_page(self) -> None:
        dialog = getattr(self, "workspace_dialog", None)
        if dialog is not None:
            dialog.refresh_from_page()

    def make_start_point_navigation(self) -> bool:
        page = _navigation_page_class()
        points = self.visible_navigation_points()
        if not points:
            return page.warn_point_goal_missing(self)
        if len(points) >= 2:
            return self.make_start_multipoint()
        return self.make_start_goal()

    def make_inspect_navigation(self) -> bool:
        map_pcd, _x, _y, _yaw, _speed, _tol = self.navigation_values()
        started = self.set_command(navigation.status_command(self.profile(), map_pcd))
        if started is False:
            self.task_state.setText("任务\n任务未启动")
            self._set_card_style(self.task_state, "blocked")
            self.flow_detail.setText(f"流程摘要\n{task_not_started_text('导航状态检查')}")
        elif started is True:
            self.flow_detail.setText("流程摘要\n导航状态检查已启动")
        return bool(started)

    def make_load_map(self) -> bool:
        map_pcd, _x, _y, _yaw, _speed, _tol = self.navigation_values()
        return self.run_navigation_spec(navigation.load_map_command(self.profile(), map_pcd), "加载地图中")

    def make_relocalize_selected_map(self) -> bool:
        page = _navigation_page_class()
        map_pcd, _x, _y, _yaw, _speed, _tol = self.navigation_values()
        if not map_pcd:
            _navigation_page_module().QMessageBox.information(self, "未选择地图", "请先选择一个历史图。")
            return False
        values = getattr(self, "last_status_values", {}) or {}
        if page.remote_navigation_running(self, values):
            self.nav_status_note.setText("当前正在导航，请先停止后再重新定位")
            self.refresh_workspace_from_page()
            return False
        self.prepared_map_pcd_path = ""
        self.map_prepare_error = ""
        self.map_prepare_auto_retry_pcd = ""
        self.nav_status_note.setText("正在重新定位当前地图")
        page.log_navigation_event(self, "[定位] 已请求重新定位当前地图")
        started = page.start_selected_map_preparation(self, force=True)
        if not started:
            self.refresh_navigation_status()
            self.refresh_workspace_from_page()
        return bool(started)

    def make_start_goal(self) -> bool:
        page = _navigation_page_class()
        if not page.single_goal_ready(self):
            return page.warn_single_goal_missing(self)
        if not page.ensure_selected_map_prepared_for_goal(self):
            page.queue_pending_navigation_action(self, "goal")
            return False
        _map_pcd, x, y, yaw, _speed, _tolerance = self.navigation_values()
        if not page.validate_navigation_points_safety(self, [(x, y, yaw)], "单点导航"):
            return False
        return page._start_goal_after_status(self)

    def _start_goal_after_status(self) -> bool:
        page = _navigation_page_class()
        map_pcd, x, y, yaw, speed, tolerance = self.navigation_values()
        spec = navigation.start_goal_command(self.profile(), map_pcd, x, y, yaw, speed, tolerance)
        started = self.run_navigation_spec(spec, "发送目标中")
        if started:
            page.begin_navigation_visualization(self)
        return started

    def make_start_multipoint(self) -> bool:
        page = _navigation_page_class()
        navigation_page = _navigation_page_module()
        map_pcd, _x, _y, _yaw, speed, _tolerance = self.navigation_values()
        try:
            points = self.navigation_points()
        except ValueError as exc:
            navigation_page.QMessageBox.information(self, "点位格式错误", str(exc))
            return False
        if len(points) < 2:
            navigation_page.QMessageBox.information(self, "点位不足", "多点导航至少需要 2 个点。")
            return False
        if not page.ensure_selected_map_prepared_for_goal(self):
            page.queue_pending_navigation_action(self, "multipoint")
            return False
        if not page.validate_navigation_points_safety(self, points, "多点导航"):
            return False
        if getattr(self, "navigation_loop_enabled", False):
            return page._start_multipoint_loop_after_status(self, map_pcd, points, speed)
        return page._start_multipoint_after_status(self, map_pcd, points, speed)

    def _start_multipoint_after_status(self, map_pcd: str, points: list[tuple[float, float, float]], speed: float) -> bool:
        page = _navigation_page_class()
        spec = navigation.start_multipoint_command(self.profile(), map_pcd, points, speed)
        started = self.run_navigation_spec(spec, "多点导航中")
        if started:
            page.begin_navigation_visualization(self)
        return started

    def make_start_route_goal(self) -> bool:
        page = _navigation_page_class()
        if not page.ensure_route_target_mode(self):
            return False
        if not (
            getattr(self, "route_target_mode", False)
            and getattr(self, "route_graph", None) is not None
            and getattr(self, "route_graph_remote_pgm", "") == self.selected_map_pgm()
        ):
            self.refresh_workspace_from_page()
            return False
        if not page.single_goal_ready(self):
            self.nav_status_note.setText("路网导航未下发：请先在路网节点附近选择目标")
            page.update_navigation_action_buttons(self, self.last_status_values)
            self.refresh_workspace_from_page()
            return False
        route_ready, route_reason = page.route_navigation_ready_reason(self)
        if not route_ready:
            page.log_navigation_event(self, f"[路网] 路网状态未确认，将在下发时实时检查远端路网：{route_reason}")
        route_path = page.sync_selected_route_geojson_path(self)
        map_pcd, x, y, yaw, speed, tolerance = self.navigation_values()
        if not page.ensure_selected_map_prepared_for_goal(self):
            page.queue_pending_navigation_action(self, "route")
            return False
        points = page.visible_navigation_points(self)
        if points:
            x, y, yaw = points[-1]
        if len(points) > 1:
            page.log_navigation_event(self, f"[路网] 已选择 {len(points)} 个路网目标节点，将按顺序下发")
        if getattr(self, "navigation_loop_enabled", False):
            if not page.validate_route_loop_closure(self):
                return False
            return page._start_route_loop_after_status(self, map_pcd, route_path, x, y, yaw, speed, tolerance, points)
        return page._start_route_goal_after_status(self, map_pcd, route_path, x, y, yaw, speed, tolerance, points)

    def _start_route_goal_after_status(
        self,
        map_pcd: str,
        route_path: str,
        x: float,
        y: float,
        yaw: float,
        speed: float,
        tolerance: float,
        points: list[tuple[float, float, float]] | None = None,
    ) -> bool:
        page = _navigation_page_class()
        spec = navigation.start_route_goal_command(self.profile(), map_pcd, route_path, x, y, yaw, speed, tolerance, points)
        started = self.run_navigation_spec(spec, "路网导航中")
        if started:
            page.begin_navigation_visualization(self)
        return started

    def toggle_navigation_loop(self) -> bool:
        page = _navigation_page_class()
        enabled = not bool(getattr(self, "navigation_loop_enabled", False))
        self.navigation_loop_enabled = enabled
        self.nav_status_note.setText("循环模式已开启" if enabled else "循环模式已关闭")
        page.log_navigation_event(self, "[导航] 循环模式已开启" if enabled else "[导航] 循环模式已关闭")
        page.update_navigation_action_buttons(self, self.last_status_values)
        self.refresh_workspace_from_page()
        return enabled

    def make_start_loop_navigation(self) -> bool:
        return self.toggle_navigation_loop()

    def make_start_multipoint_loop(self) -> bool:
        page = _navigation_page_class()
        navigation_page = _navigation_page_module()
        map_pcd, _x, _y, _yaw, speed, _tolerance = self.navigation_values()
        try:
            points = self.navigation_points()
        except ValueError as exc:
            navigation_page.QMessageBox.information(self, "点位格式错误", str(exc))
            return False
        if len(points) < 2:
            navigation_page.QMessageBox.information(self, "点位不足", "多点循环至少需要 2 个点。")
            return False
        if not page.ensure_selected_map_prepared_for_goal(self):
            page.queue_pending_navigation_action(self, "multipoint")
            return False
        if not page.validate_navigation_points_safety(self, points, "多点循环"):
            return False
        return page._start_multipoint_loop_after_status(self, map_pcd, points, speed)

    def _start_multipoint_loop_after_status(self, map_pcd: str, points: list[tuple[float, float, float]], speed: float) -> bool:
        page = _navigation_page_class()
        spec = navigation.start_multipoint_loop_command(self.profile(), map_pcd, points, speed)
        started = self.run_navigation_spec(spec, "多点循环中")
        if started:
            page.begin_navigation_visualization(self)
        return started

    def make_start_route_loop(self) -> bool:
        page = _navigation_page_class()
        if not page.ensure_route_target_mode(self):
            return False
        if not (
            getattr(self, "route_target_mode", False)
            and getattr(self, "route_graph", None) is not None
            and getattr(self, "route_graph_remote_pgm", "") == self.selected_map_pgm()
        ):
            self.refresh_workspace_from_page()
            return False
        if not page.single_goal_ready(self):
            self.nav_status_note.setText("路网循环未下发：请先在路网节点附近选择目标")
            page.update_navigation_action_buttons(self, self.last_status_values)
            self.refresh_workspace_from_page()
            return False
        route_path = page.sync_selected_route_geojson_path(self)
        map_pcd, x, y, yaw, speed, tolerance = self.navigation_values()
        if not page.ensure_selected_map_prepared_for_goal(self):
            page.queue_pending_navigation_action(self, "route")
            return False
        points = page.visible_navigation_points(self)
        if points:
            x, y, yaw = points[-1]
        if not page.validate_route_loop_closure(self):
            return False
        return page._start_route_loop_after_status(self, map_pcd, route_path, x, y, yaw, speed, tolerance, points)

    def _start_route_loop_after_status(
        self,
        map_pcd: str,
        route_path: str,
        x: float,
        y: float,
        yaw: float,
        speed: float,
        tolerance: float,
        points: list[tuple[float, float, float]] | None = None,
    ) -> bool:
        page = _navigation_page_class()
        spec = navigation.start_route_goal_loop_command(self.profile(), map_pcd, route_path, x, y, yaw, speed, tolerance, points)
        started = self.run_navigation_spec(spec, "路网循环中")
        if started:
            page.begin_navigation_visualization(self)
        return started

    def make_stop_navigation(self) -> bool:
        page = _navigation_page_class()
        had_pending_action = bool(self.pending_navigation_action)
        self.pending_navigation_action = ""
        if had_pending_action:
            self.nav_status_note.setText("已取消等待地图和定位就绪的导航任务")
            page.log_navigation_event(self, "[任务] 已取消等待地图和定位就绪的导航任务")
        started = self.run_navigation_spec(navigation.stop_command(self.profile(), source="manual_button"), "停止中")
        if started:
            self.stop_navigation_waiting_remote_confirm = True
            self.stop_navigation_waiting_started_at = time.monotonic()
            for target in (self, getattr(self, "workspace_dialog", None)):
                stop_button = getattr(target, "stop_button", None)
                if stop_button is not None:
                    stop_button.setText("停止中")
                    stop_button.setEnabled(False)
                    stop_button.setToolTip("停止命令已发送，正在等待远端确认")
            self.navigation_tracking_enabled = False
            self.navigation_tracking_active_seen = False
            self.navigation_status_watch_running = False
            self.navigation_command_task_id = None
            self.navigation_command_operation = ""
            page.stop_plan_stream(self)
            page.stop_obstacle_stream(self)
            page._set_navigation_visual_layers(self, [], [])
            page.clear_obstacle_points(self)
            page.log_navigation_event(self, "[规划] 已停止导航规划更新并清空规划线")
        return started

    def stop_navigation_for_map_switch(self) -> bool:
        page = _navigation_page_class()
        page.log_navigation_event(self, "[地图] 检测到导航中切换地图，准备自动停止当前导航")
        spec = replace(
            navigation.stop_command(self.profile(), source="map_switch"),
            dangerous=False,
            description="切换地图前自动停止当前远端导航任务。",
        )
        started = self.run_navigation_spec(spec, "停止中")
        if started:
            self.pending_navigation_action = ""
            self.navigation_tracking_enabled = False
            self.navigation_tracking_active_seen = False
            self.navigation_status_watch_running = False
            self.navigation_command_task_id = None
            self.navigation_command_operation = ""
            page.stop_plan_stream(self)
            page.stop_obstacle_stream(self)
            page._set_navigation_visual_layers(self, [], [])
            page.clear_obstacle_points(self)
            page.log_navigation_event(self, "[地图] 切换地图前已停止当前导航任务")
        return started

    def make_toggle_navigation_pause(self) -> bool:
        page = _navigation_page_class()
        values = getattr(self, "last_status_values", {}) or {}
        if page.remote_navigation_paused(self, values):
            started = self.run_navigation_spec(navigation.continue_command(self.profile()), "继续中")
            if started:
                self.navigation_tracking_enabled = True
                page.start_navigation_status_watch(self)
            return started
        if not page.remote_navigation_running(self, values):
            self.nav_status_note.setText("当前没有可暂停的导航任务")
            self.refresh_workspace_from_page()
            return False
        started = self.run_navigation_spec(navigation.pause_command(self.profile()), "暂停中")
        if started:
            self.navigation_tracking_enabled = True
            page.start_navigation_status_watch(self)
        return started
