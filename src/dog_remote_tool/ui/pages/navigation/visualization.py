from __future__ import annotations

import math
import re

from dog_remote_tool.ui.pages.navigation import status_helpers as _status_helpers

NAVIGATION_STATUS_WATCH_START_DELAY_MS = 500
NAVIGATION_STATUS_WATCH_INTERVAL_MS = 2000


def _navigation_page_class():
    from dog_remote_tool.ui.pages.navigation.page import NavigationPage

    return NavigationPage


def _navigation_page_module():
    from dog_remote_tool.ui.pages.navigation import page as navigation_page

    return navigation_page


class NavigationVisualizationMixin:
    def navigation_log_text(self) -> str:
        if not self.navigation_log_lines:
            return "暂无任务日志"
        return "\n".join(self.navigation_log_lines)

    def capture_navigation_log(self, text: str) -> None:
        for raw in text.splitlines():
            line = _status_helpers._sanitize_log_line(raw).strip()
            if line:
                self.navigation_log_lines.append(line)
        refresh = getattr(self, "refresh_workspace_from_page", None)
        if callable(refresh):
            refresh()

    def log_navigation_event(self, text: str) -> None:
        runner = getattr(self, "runner", None)
        output = getattr(runner, "output", None)
        emit = getattr(output, "emit", None)
        page = _navigation_page_class()
        if callable(emit):
            emit(text if text.endswith("\n") else text + "\n")
        else:
            page.capture_navigation_log(self, text)

    def _set_navigation_visual_layers(
        self,
        global_route: list[tuple[float, float, float]] | None = None,
        realtime_plan: list[tuple[float, float, float]] | None = None,
    ) -> None:
        page = _navigation_page_class()
        if global_route is not None:
            self.navigation_global_route = page._downsample_route(self, global_route)
            if callable(getattr(self.nav_map, "set_global_route", None)):
                self.nav_map.set_global_route(self.navigation_global_route)
        if realtime_plan is not None:
            self.navigation_realtime_plan = page._downsample_route(self, realtime_plan, max_points=900)
            if callable(getattr(self.nav_map, "set_realtime_plan", None)):
                self.nav_map.set_realtime_plan(self.navigation_realtime_plan)
        dialog = getattr(self, "workspace_dialog", None)
        if dialog is not None:
            dialog.canvas.set_global_route(self.navigation_global_route)
            dialog.canvas.set_realtime_plan(self.navigation_realtime_plan)

    def begin_navigation_visualization(self) -> None:
        page = _navigation_page_class()
        navigation_page = _navigation_page_module()
        self.navigation_tracking_enabled = True
        self.navigation_tracking_active_seen = False
        self.navigation_body_release_after_terminal_triggered = False
        self.navigation_global_plan_topic = ""
        self.navigation_realtime_plan_topic = ""
        page._set_navigation_visual_layers(self, [], [])
        page.start_navigation_status_watch(self)
        navigation_page.QTimer.singleShot(0, lambda: page.start_plan_stream(self))
        if getattr(self, "obstacle_overlay_enabled", True):
            navigation_page.QTimer.singleShot(0, lambda: page.start_obstacle_stream(self))

    def navigation_status_matches_selected_map(self, values: dict[str, str]) -> bool:
        map_pcd = self.map_pcd_path.text().strip() if hasattr(self, "map_pcd_path") else ""
        status_map_pcd = values.get("MAP_PCD", "").strip()
        return bool(map_pcd and status_map_pcd and map_pcd == status_map_pcd)

    def resume_navigation_visualization_from_status(self, values: dict[str, str]) -> bool:
        if values.get("STATUS") != "active":
            return False
        page = _navigation_page_class()
        navigation_page = _navigation_page_module()
        if not page.navigation_status_matches_selected_map(self, values):
            return False
        map_pcd = self.map_pcd_path.text().strip()
        was_tracking = bool(getattr(self, "navigation_tracking_enabled", False))
        self.navigation_tracking_enabled = True
        self.navigation_tracking_active_seen = True
        self.prepared_map_pcd_path = map_pcd
        self.preparing_map_pcd_path = ""
        self.map_prepare_error = ""
        self.map_prepare_auto_retry_pcd = ""
        page.start_navigation_status_watch(self)
        if page.navigation_streams_ready(self) and page.navigation_stream_subscription_active(self):
            navigation_page.QTimer.singleShot(0, self.start_plan_stream)
        return True

    def start_navigation_status_watch(self) -> bool:
        if not getattr(self, "page_active", False):
            return False
        if not getattr(self, "navigation_tracking_enabled", False):
            return False
        if getattr(self, "navigation_status_watch_running", False):
            return True
        self.navigation_status_watch_running = True
        navigation_page = _navigation_page_module()
        page = _navigation_page_class()
        navigation_page.QTimer.singleShot(
            NAVIGATION_STATUS_WATCH_START_DELAY_MS,
            lambda: page.continue_navigation_status_watch(self),
        )
        return True

    def continue_navigation_status_watch(self) -> bool:
        if not getattr(self, "page_active", False) or not getattr(self, "navigation_tracking_enabled", False):
            self.navigation_status_watch_running = False
            return False
        self.refresh_navigation_status()
        navigation_page = _navigation_page_module()
        page = _navigation_page_class()
        navigation_page.QTimer.singleShot(
            NAVIGATION_STATUS_WATCH_INTERVAL_MS,
            lambda: page.continue_navigation_status_watch(self),
        )
        return True

    def navigation_command_finished(self) -> bool:
        task_id = getattr(self, "navigation_command_task_id", None)
        if task_id is None:
            return True
        tasks = getattr(getattr(self, "runner", None), "tasks", None)
        if isinstance(tasks, dict) and task_id in tasks:
            return False
        return True

    def ready_status_confirms_navigation_finished(self, values: dict[str, str]) -> bool:
        page = _navigation_page_class()
        if values.get("STATUS") != "ready" or not page.navigation_command_finished(self):
            return False
        try:
            remaining = float(values.get("NAV_ESTIMATED_DISTANCE_REMAINING", "").strip())
        except ValueError:
            return False
        if abs(remaining) > 0.05:
            return False
        try:
            distance_from_start = float(values.get("NAV_DISTANCE_FROM_START", "").strip())
        except ValueError:
            distance_from_start = 0.0
        return bool(getattr(self, "navigation_tracking_active_seen", False)) or (
            distance_from_start > 0.1
        )

    def release_body_navigation_control_after_terminal(self) -> bool:
        if getattr(self, "navigation_body_release_after_terminal_triggered", False):
            return False
        from dog_remote_tool.modules import navigation

        spec = navigation.release_body_navigation_bridge_command(self.profile(), stop_service=False)
        if spec is None:
            self.navigation_body_release_after_terminal_triggered = True
            return False
        runner = getattr(self, "runner", None)
        if runner is None:
            return False
        conflict_reason = getattr(runner, "conflict_reason", None)
        if callable(conflict_reason) and conflict_reason(spec):
            return False
        self.navigation_body_release_after_terminal_triggered = True
        task_id = runner.run(spec, spec.display_command or spec.title)
        if task_id is not None:
            page = _navigation_page_class()
            page.log_navigation_event(self, "[导航] 远端终态已确认，保留导航服务热启动")
            return True
        self.navigation_body_release_after_terminal_triggered = False
        return False

    def pending_navigation_command_display_values(self, values: dict[str, str]) -> dict[str, str]:
        operation = getattr(self, "navigation_command_operation", "")
        pending_text = _status_helpers._navigation_command_pending_text(operation)
        display_values = _status_helpers._without_remote_navigation_state(values)
        display_values["STATUS"] = "starting"
        display_values["TEXT"] = pending_text
        return display_values

    def show_pending_navigation_command(self, operation: str, values: dict[str, str] | None = None) -> None:
        page = _navigation_page_class()
        pending_text = _status_helpers._navigation_command_pending_text(operation)
        wait_text = _status_helpers._navigation_command_wait_text(operation)
        display_values = page.pending_navigation_command_display_values(self, values or {})
        self.task_state.setText(f"任务\n{pending_text}")
        self._set_card_style(self.task_state, "starting")
        if hasattr(self, "nav_current_state"):
            icon = page.navigation_status_icon(self, display_values, "starting")
            self.nav_current_state.setText(f"当前状态\n{icon} {pending_text}\n{wait_text}")
            self._set_card_style(self.nav_current_state, "starting")
        if hasattr(self, "flow_detail"):
            self.flow_detail.setText(f"流程摘要\n{wait_text}")
            self.flow_detail.setToolTip(wait_text)
        if hasattr(self, "nav_code_detail"):
            self.nav_code_detail.setText(wait_text)
            self.nav_code_detail.setToolTip(wait_text)
        if hasattr(self, "nav_status_note"):
            self.nav_status_note.setText(wait_text)

    def on_runner_task_output(self, task_id: int, text: str) -> None:
        if task_id != getattr(self, "navigation_command_task_id", None):
            return
        matches = re.findall(r"(?m)^APP_NAV_STATUS=([^\s\r\n]+)", text)
        if not matches:
            return
        app_nav_status = matches[-1].strip()
        if not app_nav_status:
            return
        page = _navigation_page_class()
        from dog_remote_tool.modules import navigation

        state, label, detail, values = navigation.summarize_status(f"APP_NAV_STATUS={app_nav_status}")
        merged = _status_helpers._without_remote_navigation_state(dict(getattr(self, "last_status_values", {}) or {}))
        merged.update(values)
        merged["APP_NAV_STATUS"] = app_nav_status
        merged["STATUS"] = state
        merged["TEXT"] = label
        self.last_status_values = merged
        self.last_status_state = state
        page.set_cards_from_values(self, merged, detail)

    def on_runner_task_finished(self, _task_id: int, code: int, title: str) -> None:
        page = _navigation_page_class()
        navigation_page = _navigation_page_module()
        mark_charging_dock_finished = code == 0 and title == "执行：标记充电桩"
        arc_calibration_finished = title == "执行：ARC 标定充电桩"
        arc_recharge_finished = code == 0 and title in {"执行：ARC 回充", "执行：ARC 有图回充"}
        arc_undock_finished = code == 0 and title == "执行：ARC 出桩"
        stop_navigation_finished = title == "执行：停止导航"
        pause_resume_finished = title in {"执行：暂停导航", "执行：继续导航"}
        if pause_resume_finished:
            if code == 0:
                paused = title == "执行：暂停导航"
                display_values = dict(getattr(self, "last_status_values", {}) or {})
                display_values["STATUS"] = "paused" if paused else "active"
                display_values["TEXT"] = "导航暂停" if paused else "导航执行中"
                self.last_status_values = display_values
                self.last_status_state = display_values["STATUS"]
                self.task_state.setText("任务\n已暂停" if paused else "任务\n已继续")
                self._set_card_style(self.task_state, "paused" if paused else "active")
                self.nav_status_note.setText("导航已暂停" if paused else "导航已继续")
                page.update_navigation_action_buttons(self, display_values)
                self.refresh_workspace_from_page()
                navigation_page.QTimer.singleShot(500, self.refresh_navigation_status)
                return
            self.nav_status_note.setText("导航暂停/继续命令失败，请查看任务日志")
            page.log_navigation_event(self, f"[导航] 暂停/继续失败：{title}，请查看详细日志")
            return
        if arc_calibration_finished:
            self.navigation_command_task_id = None
            self.navigation_command_operation = ""
            if code == 0:
                self.task_state.setText("任务\n标定完成")
                self._set_card_style(self.task_state, "ready")
                self.nav_status_note.setText("充电桩标定完成，正在刷新 ARC 状态")
                page.log_navigation_event(self, "[ARC] 充电桩标定完成")
            else:
                self.task_state.setText("任务\n标定失败")
                self._set_card_style(self.task_state, "blocked")
                self.nav_status_note.setText("充电桩标定失败，请检查 ARC 状态机和任务日志")
                page.log_navigation_event(self, f"[ARC] 标定充电桩失败：{title}，请查看详细日志")
            page.update_navigation_action_buttons(self, getattr(self, "last_status_values", {}) or {})
            self.refresh_workspace_from_page()
            for delay in (500, 1500, 3200):
                navigation_page.QTimer.singleShot(delay, self.refresh_navigation_status)
            return
        if arc_recharge_finished:
            self.navigation_tracking_enabled = False
            self.navigation_tracking_active_seen = False
            self.navigation_status_watch_running = False
            self.navigation_command_task_id = None
            self.navigation_command_operation = ""
            self.navigation_body_release_after_terminal_triggered = True
            page.stop_plan_stream(self)
            page.stop_obstacle_stream(self)
            page._set_navigation_visual_layers(self, [], [])
            page.clear_obstacle_points(self)
            mark_charging = getattr(getattr(self, "device_bar", None), "mark_battery_charging_hint", None)
            if callable(mark_charging):
                mark_charging()
            display_values = dict(getattr(self, "last_status_values", {}) or {})
            display_values.update(
                {
                    "STATUS": "ready",
                    "TEXT": "充电中",
                    "ARC_DOCK_STATE": "2",
                    "ARC_DOCK_TEXT": "充电中",
                    "ARC_APP_DOCK_STATUS": "Charging",
                    "ARC_APP_ALG_STATUS": "Charging",
                }
            )
            self.last_status_values = display_values
            self.last_status_state = "ready"
            self.task_state.setText("任务\n充电中")
            self._set_card_style(self.task_state, "success")
            if hasattr(self, "nav_current_state"):
                self.nav_current_state.setText("当前状态\n✓ 充电中\nARC 已进入充电状态")
                self._set_card_style(self.nav_current_state, "success")
            self.nav_status_note.setText("回充成功，已进入充电状态；如需离桩请点击“出桩”")
            page.log_navigation_event(self, "[ARC] 回充成功，已进入充电状态")
            page.update_navigation_action_buttons(self, display_values)
            self.refresh_workspace_from_page()
            for delay in (1200, 3200):
                navigation_page.QTimer.singleShot(delay, self.refresh_navigation_status)
            return
        if arc_undock_finished:
            self.navigation_tracking_enabled = False
            self.navigation_tracking_active_seen = False
            self.navigation_status_watch_running = False
            self.navigation_command_task_id = None
            self.navigation_command_operation = ""
            self.navigation_body_release_after_terminal_triggered = True
            page.stop_plan_stream(self)
            page.stop_obstacle_stream(self)
            page._set_navigation_visual_layers(self, [], [])
            page.clear_obstacle_points(self)
            clear_charging = getattr(getattr(self, "device_bar", None), "clear_battery_charging_hint", None)
            if callable(clear_charging):
                clear_charging()
            display_values = dict(getattr(self, "last_status_values", {}) or {})
            for key in ("ARC_DOCK_STATE", "ARC_DOCK_TEXT", "ARC_APP_DOCK_STATUS", "ARC_APP_ALG_STATUS"):
                display_values.pop(key, None)
            display_values["STATUS"] = "ready"
            display_values["TEXT"] = "已出桩"
            self.last_status_values = display_values
            self.last_status_state = "ready"
            self.task_state.setText("任务\n已出桩")
            self._set_card_style(self.task_state, "ready")
            if hasattr(self, "nav_current_state"):
                self.nav_current_state.setText("当前状态\n● 导航就绪")
                self._set_card_style(self.nav_current_state, "ready")
            self.nav_status_note.setText("出桩成功，可再次使用“有图进桩”")
            page.log_navigation_event(self, "[ARC] 出桩成功，已离开充电状态")
            page.update_navigation_action_buttons(self, display_values)
            self.refresh_workspace_from_page()
            for delay in (500, 1500, 3200):
                navigation_page.QTimer.singleShot(delay, self.refresh_navigation_status)
            return
        if stop_navigation_finished:
            if code != 0:
                self.stop_navigation_waiting_remote_confirm = False
            self.navigation_tracking_enabled = False
            self.navigation_tracking_active_seen = False
            self.navigation_status_watch_running = False
            self.navigation_command_task_id = None
            self.navigation_command_operation = ""
            self.navigation_body_release_after_terminal_triggered = True
            page.stop_plan_stream(self)
            page.stop_obstacle_stream(self)
            page._set_navigation_visual_layers(self, [], [])
            page.clear_obstacle_points(self)
            self.task_state.setText("任务\n已停止" if code == 0 else "任务\n停止已发送")
            self._set_card_style(self.task_state, "ready" if code == 0 else "blocked")
            note = "停止命令已完成，正在刷新远端状态" if code == 0 else "停止命令返回异常，正在刷新远端状态"
            self.nav_status_note.setText(note)
            page.log_navigation_event(self, f"[导航] {note}")
            display_values = _status_helpers._without_remote_navigation_state(
                dict(getattr(self, "last_status_values", {}) or {})
            )
            display_values.setdefault("MAP_OK", "1")
            display_values.setdefault("LOAD_MAP_SERVICE", "1")
            display_values.setdefault("LOCALIZATION_READY", "1")
            display_values.setdefault("NAV_PROCESS", "1")
            display_values.setdefault("START_NAV_SUBSCRIBERS", "1")
            display_values["STATUS"] = "ready"
            display_values["TEXT"] = "已停止"
            page.update_navigation_action_buttons(self, display_values)
            for delay in (0, 500, 1500, 3200):
                navigation_page.QTimer.singleShot(delay, self.refresh_navigation_status)
            return
        if _task_id == getattr(self, "navigation_command_task_id", None):
            if code != 0:
                self.navigation_tracking_enabled = False
                self.navigation_tracking_active_seen = False
                self.navigation_status_watch_running = False
                self.navigation_command_task_id = None
                self.navigation_command_operation = ""
                page.stop_plan_stream(self)
                page.stop_obstacle_stream(self)
                page._set_navigation_visual_layers(self, [], [])
                page.clear_obstacle_points(self)
                self.nav_status_note.setText("导航命令下发失败，请查看任务日志")
                page.log_navigation_event(self, f"[导航] 任务失败：{title}，请查看详细日志")
            elif mark_charging_dock_finished:
                self.navigation_command_task_id = None
                self.navigation_command_operation = ""
                self.task_state.setText("任务\n标记完成")
                self._set_card_style(self.task_state, "ready")
                page.update_navigation_action_buttons(self, getattr(self, "last_status_values", {}) or {})
            for delay in (200, 1200, 3200):
                navigation_page.QTimer.singleShot(delay, self.refresh_navigation_status)
        if not mark_charging_dock_finished:
            return
        self.nav_status_note.setText("充电桩标记已写入，正在刷新地图预览")
        page.log_navigation_event(self, "[地图] 充电桩标记完成")
        if getattr(self, "map_preview_slot", None) is not None and self.map_preview_slot.is_running():
            self.map_preview_slot.stop()
            self.fetching_preview_remote_pgm = ""
        self.fetch_navigation_map_preview(force=True)
        self.refresh_navigation_status()
        navigation_page.QTimer.singleShot(1200, self.refresh_navigation_status)

    def finish_navigation_visualization_if_terminal(self, status: str) -> None:
        page = _navigation_page_class()
        if status == "active" and self.navigation_tracking_enabled:
            self.navigation_tracking_active_seen = True
            return
        values = getattr(self, "last_status_values", {}) or {}
        app_nav_status = values.get("APP_NAV_STATUS", "").strip()
        app_terminal = app_nav_status in {"Succeeded", "Error", "NavError", "LocError", "Failed"}
        ready_terminal = (
            status == "ready"
            and getattr(self, "navigation_command_idle_confirmations", 0) >= 2
            and page.ready_status_confirms_navigation_finished(self, values)
        )
        if not app_terminal and not ready_terminal:
            return
        if self.navigation_tracking_enabled:
            self.navigation_body_release_after_terminal_triggered = True
            self.navigation_tracking_enabled = False
            self.navigation_tracking_active_seen = False
            self.navigation_status_watch_running = False
            self.navigation_command_task_id = None
            self.navigation_command_operation = ""
            page.stop_plan_stream(self)
            page.stop_obstacle_stream(self)
            page.clear_obstacle_points(self)
            if app_nav_status in {"Error", "NavError", "LocError", "Failed"}:
                page.update_nav_map_points(self)
                self.nav_status_note.setText("导航任务异常结束，点位记录已保留")
            else:
                page._set_navigation_visual_layers(self, [], [])
                page.reset_navigation_targets_after_task(self)
                self.nav_status_note.setText("导航任务已结束，可重新选择目标点")

    def reset_navigation_targets_after_task(self) -> None:
        page = _navigation_page_class()
        self.goal_point_selected = False
        self.route_target_node_ids = []
        self.added_waypoint_undo_stack = []
        if hasattr(self, "waypoints_text"):
            self.waypoints_text.setPlainText("")
        page.refresh_navigation_points_list(self)
        if callable(getattr(self.nav_map, "set_points", None)):
            self.nav_map.set_points([])
        if callable(getattr(self.nav_map, "set_route_target_node_ids", None)):
            self.nav_map.set_route_target_node_ids([])
        dialog = getattr(self, "workspace_dialog", None)
        if dialog is not None:
            dialog.canvas.set_points([])
            point_summary = getattr(dialog, "point_summary", None)
            if point_summary is not None and callable(getattr(self, "target_summary_text", None)):
                point_summary.setText(self.target_summary_text())

    def handle_navigation_plan_update(
        self,
        kind: str,
        topic: str,
        points: list[tuple[float, float, float]],
    ) -> None:
        if not points:
            return
        page = _navigation_page_class()
        if kind == "GLOBAL":
            self.navigation_global_plan_topic = topic
            page._set_navigation_visual_layers(self, global_route=points)

    def _downsample_route(
        self,
        points: list[tuple[float, float, float]],
        max_points: int = 500,
    ) -> list[tuple[float, float, float]]:
        if len(points) <= max_points:
            return list(points)
        step = max(1, math.ceil(len(points) / max_points))
        sampled = points[::step]
        if sampled[-1] != points[-1]:
            sampled.append(points[-1])
        return sampled
