from __future__ import annotations

from PyQt5.QtCore import QProcess, QTimer

from dog_remote_tool.core.shell import CommandSpec
from dog_remote_tool.modules import localization
from dog_remote_tool.modules import navigation
from dog_remote_tool.ui.navigation_helpers import (
    consume_obstacle_stream_output,
    consume_plan_stream_output,
    consume_pose_stream_output,
)
from dog_remote_tool.ui.pages.navigation.status_helpers import _status_allows_selected_map_pose_display


NAVIGATION_STREAM_RESTART_DELAY_MS = 1500
NAVIGATION_STREAM_TRANSIENT_RESTART_DELAYS_MS = (3000, 8000, 15000, 30000)


class NavigationStreamsMixin:
    def _log_stream_event(self, text: str) -> None:
        log = getattr(self, "log_navigation_event", None)
        if callable(log):
            log(text)
            return
        lines = getattr(self, "navigation_log_lines", None)
        if lines is not None:
            lines.append(text)
            refresh = getattr(self, "refresh_workspace_from_page", None)
            if callable(refresh):
                refresh()

    def _handle_plan_stream_update(self, kind: str, topic: str, points: list[tuple[float, float, float]]) -> None:
        handler = getattr(self, "handle_navigation_plan_update", None)
        if callable(handler):
            handler(kind, topic, points)
            return
        if not points:
            return
        if kind == "GLOBAL":
            self.navigation_global_route = list(points)
            self.navigation_global_plan_topic = topic

    def _set_obstacle_overlay_button_state(self) -> None:
        button = getattr(self, "obstacle_overlay_button", None)
        if button is None:
            return
        enabled = bool(getattr(self, "obstacle_overlay_enabled", True))
        button.setText("障碍 ON" if enabled else "障碍 OFF")
        button.setToolTip("显示或隐藏实时障碍点云；关闭后停止轻量转发通道" if enabled else "实时障碍点云已关闭")
        if callable(getattr(button, "setChecked", None)):
            button.setChecked(enabled)

    def _set_navigation_obstacle_points(self, points: list[tuple[float, float]], topic: str = "") -> None:
        next_points = list(points)
        changed = (
            next_points != list(getattr(self, "navigation_obstacle_points", []) or [])
            or topic != getattr(self, "navigation_obstacle_topic", "")
        )
        self.navigation_obstacle_points = next_points
        self.navigation_obstacle_topic = topic
        nav_map = getattr(self, "nav_map", None)
        if callable(getattr(nav_map, "set_obstacle_points", None)):
            nav_map.set_obstacle_points(self.navigation_obstacle_points)
        dialog = getattr(self, "workspace_dialog", None)
        if dialog is not None and callable(getattr(dialog.canvas, "set_obstacle_points", None)):
            dialog.canvas.set_obstacle_points(self.navigation_obstacle_points)
        if not changed:
            return
        refresh = getattr(self, "refresh_workspace_from_page", None)
        if callable(refresh):
            refresh()

    def clear_obstacle_points(self) -> None:
        NavigationStreamsMixin._set_navigation_obstacle_points(self, [], "")

    def toggle_obstacle_overlay(self) -> bool:
        self.obstacle_overlay_enabled = not bool(getattr(self, "obstacle_overlay_enabled", True))
        NavigationStreamsMixin._set_obstacle_overlay_button_state(self)
        if self.obstacle_overlay_enabled:
            NavigationStreamsMixin.start_obstacle_stream(self)
            return True
        NavigationStreamsMixin.stop_obstacle_stream(self)
        NavigationStreamsMixin.clear_obstacle_points(self)
        return False

    def ensure_navigation_helpers(self) -> bool:
        if not self.page_active or not self.navigation_supported():
            return False
        if self.mode_switch_helper_slot.is_running():
            return False
        self.navigation_cleanup_profile = self.profile()
        process, request_id = self.mode_switch_helper_slot.start_spec(
            navigation.ensure_navigation_helpers_command(self.profile())
        )
        if process is None:
            return False
        process.readyReadStandardOutput.connect(lambda: self.read_navigation_helpers_output(process, request_id))
        process.finished.connect(
            lambda exit_code, _status: self.navigation_helpers_finished(process, exit_code, request_id)
        )
        process.start()
        return True

    def read_navigation_helpers_output(self, process: QProcess, request_id: int) -> bool:
        return self.mode_switch_helper_slot.read_available_output(process, request_id)

    def navigation_helpers_finished(self, process: QProcess, exit_code: int, request_id: int) -> bool:
        output = self.mode_switch_helper_slot.finish(process, request_id)
        if output is None:
            return False
        if exit_code != 0 and self.page_active:
            self.nav_status_note.setText("导航通道准备失败，请检查远端导航服务")
            self.refresh_workspace_from_page()
        return True

    ensure_mode_switch_helper = ensure_navigation_helpers
    read_mode_switch_helper_output = read_navigation_helpers_output
    mode_switch_helper_finished = navigation_helpers_finished

    def navigation_streams_ready(self) -> bool:
        if not self.page_active or not self.navigation_supported():
            return False
        map_pcd = self.map_pcd_path.text().strip() if hasattr(self, "map_pcd_path") else ""
        if not map_pcd:
            return False
        if getattr(self, "prepared_map_pcd_path", "") == map_pcd:
            return True
        slot = getattr(self, "map_prepare_slot", None)
        prepare_running = slot is not None and slot.is_running()
        preparing_map = getattr(self, "preparing_map_pcd_path", "")
        status_ready = _status_allows_selected_map_pose_display(getattr(self, "last_status_values", {}) or {}, map_pcd)
        if prepare_running and preparing_map and preparing_map != map_pcd:
            return False
        if status_ready:
            return True
        return False

    def navigation_stream_subscription_active(self) -> bool:
        if not self.page_active or not self.navigation_supported():
            return False
        if getattr(self, "navigation_tracking_enabled", False):
            return True
        return getattr(self, "workspace_dialog", None) is not None

    def navigation_stream_should_restart(self, output: str) -> bool:
        return NavigationStreamsMixin.navigation_stream_restart_delay_ms(self, output, "stream") is not None

    def navigation_stream_restart_delay_ms(self, output: str, stream_name: str) -> int | None:
        if "STREAM=shm_guard" in output:
            self.nav_status_note.setText("位姿/路径流未启动：远端 /dev/shm 使用率过高")
            NavigationStreamsMixin._log_stream_event(self, "[诊断] 位姿/路径流未重连：远端 /dev/shm 使用率过高")
            return None
        if "STREAM=ros_error" in output or "Error setting up zenoh session" in output or "POSIX shm" in output:
            attr = f"{stream_name}_stream_transient_failures"
            failures = int(getattr(self, attr, 0)) + 1
            setattr(self, attr, failures)
            index = min(failures - 1, len(NAVIGATION_STREAM_TRANSIENT_RESTART_DELAYS_MS) - 1)
            delay_ms = NAVIGATION_STREAM_TRANSIENT_RESTART_DELAYS_MS[index]
            delay_s = delay_ms / 1000
            self.nav_status_note.setText(f"位姿/路径流初始化失败，{delay_s:.0f} 秒后重试")
            NavigationStreamsMixin._log_stream_event(
                self,
                f"[诊断] 位姿/路径流初始化失败，将在 {delay_s:.0f} 秒后重试",
            )
            return delay_ms
        setattr(self, f"{stream_name}_stream_transient_failures", 0)
        return NAVIGATION_STREAM_RESTART_DELAY_MS

    def start_pose_stream(self) -> bool:
        if not self.page_active or not self.navigation_supported():
            return False
        if not NavigationStreamsMixin.navigation_streams_ready(self):
            return False
        if self.pose_stream_slot.is_running():
            return False
        self.navigation_cleanup_profile = self.profile()
        self.pose_stream_buffer = ""
        process, request_id = self.pose_stream_slot.start_spec(
            CommandSpec(
                "导航位姿流",
                localization.pose_stream_command(self.profile()),
                concurrency="parallel",
                locks=("navigation-pose-stream",),
            )
        )
        if process is None:
            return False
        process.readyReadStandardOutput.connect(lambda: self.read_pose_stream_output(process, request_id))
        process.finished.connect(lambda _exit_code, _status: self.pose_stream_finished(process, request_id))
        process.start()
        return True

    def stop_pose_stream(self) -> bool:
        self.pose_stream_buffer = ""
        return self.pose_stream_slot.stop()

    def read_pose_stream_output(self, process: QProcess, request_id: int) -> None:
        chunk = self.pose_stream_slot.read_available_text(process, request_id)
        if not chunk:
            return
        self.pose_stream_buffer, pose = consume_pose_stream_output(self.pose_stream_buffer, chunk)
        if pose:
            self.pose_stream_transient_failures = 0
            self.handle_robot_pose_update(pose)

    def pose_stream_finished(self, process: QProcess, request_id: int) -> None:
        output = self.pose_stream_slot.finish(process, request_id)
        if output is None:
            return
        if self.page_active and NavigationStreamsMixin.navigation_streams_ready(self):
            delay_ms = NavigationStreamsMixin.navigation_stream_restart_delay_ms(self, output, "pose")
            if delay_ms is not None:
                QTimer.singleShot(delay_ms, self.start_pose_stream)

    def start_plan_stream(self) -> bool:
        if not self.page_active or not self.navigation_supported():
            return False
        if not getattr(self, "navigation_tracking_enabled", False):
            return False
        if not NavigationStreamsMixin.navigation_stream_subscription_active(self):
            return False
        if not NavigationStreamsMixin.navigation_streams_ready(self):
            return False
        slot = getattr(self, "plan_stream_slot", None)
        if slot is None:
            return False
        if slot.is_running():
            return False
        self.navigation_cleanup_profile = self.profile()
        self.plan_stream_buffer = ""
        process, request_id = slot.start_spec(
            CommandSpec(
                "导航路径流",
                localization.navigation_plan_stream_command(self.profile()),
                concurrency="parallel",
                locks=("navigation-plan-stream",),
            )
        )
        if process is None:
            return False
        process.readyReadStandardOutput.connect(lambda: self.read_plan_stream_output(process, request_id))
        process.finished.connect(lambda _exit_code, _status: self.plan_stream_finished(process, request_id))
        process.start()
        return True

    def stop_plan_stream(self) -> bool:
        self.plan_stream_buffer = ""
        slot = getattr(self, "plan_stream_slot", None)
        return bool(slot is not None and slot.stop())

    def read_plan_stream_output(self, process: QProcess, request_id: int) -> None:
        chunk = self.plan_stream_slot.read_available_text(process, request_id)
        if not chunk:
            return
        self.plan_stream_buffer, updates = consume_plan_stream_output(self.plan_stream_buffer, chunk)
        for kind, topic, points in updates:
            self.plan_stream_transient_failures = 0
            NavigationStreamsMixin._handle_plan_stream_update(self, kind, topic, points)

    def plan_stream_finished(self, process: QProcess, request_id: int) -> None:
        output = self.plan_stream_slot.finish(process, request_id)
        if output is None:
            return
        if (
            self.page_active
            and NavigationStreamsMixin.navigation_stream_subscription_active(self)
            and NavigationStreamsMixin.navigation_streams_ready(self)
            and getattr(self, "navigation_tracking_enabled", False)
        ):
            delay_ms = NavigationStreamsMixin.navigation_stream_restart_delay_ms(self, output, "plan")
            if delay_ms is not None:
                QTimer.singleShot(delay_ms, self.start_plan_stream)

    def start_obstacle_stream(self) -> bool:
        if not self.page_active or not self.navigation_supported():
            return False
        if not getattr(self, "obstacle_overlay_enabled", True):
            return False
        if not getattr(self, "navigation_tracking_enabled", False):
            return False
        if not NavigationStreamsMixin.navigation_streams_ready(self):
            return False
        slot = getattr(self, "obstacle_stream_slot", None)
        if slot is None or slot.is_running():
            return False
        self.navigation_cleanup_profile = self.profile()
        self.obstacle_stream_buffer = ""
        process, request_id = slot.start_spec(
            CommandSpec(
                "导航障碍物流",
                localization.obstacle_stream_command(self.profile()),
                concurrency="parallel",
                locks=("navigation-obstacle-stream",),
            )
        )
        if process is None:
            return False
        process.readyReadStandardOutput.connect(lambda: self.read_obstacle_stream_output(process, request_id))
        process.finished.connect(lambda _exit_code, _status: self.obstacle_stream_finished(process, request_id))
        process.start()
        return True

    def stop_obstacle_stream(self) -> bool:
        self.obstacle_stream_buffer = ""
        slot = getattr(self, "obstacle_stream_slot", None)
        return bool(slot is not None and slot.stop())

    def read_obstacle_stream_output(self, process: QProcess, request_id: int) -> None:
        chunk = self.obstacle_stream_slot.read_available_text(process, request_id)
        if not chunk:
            return
        self.obstacle_stream_buffer, updates = consume_obstacle_stream_output(self.obstacle_stream_buffer, chunk)
        for topic, points in updates:
            self.obstacle_stream_transient_failures = 0
            NavigationStreamsMixin._set_navigation_obstacle_points(self, points, topic)

    def obstacle_stream_finished(self, process: QProcess, request_id: int) -> None:
        output = self.obstacle_stream_slot.finish(process, request_id)
        if output is None:
            return
        if (
            self.page_active
            and getattr(self, "obstacle_overlay_enabled", True)
            and getattr(self, "navigation_tracking_enabled", False)
            and NavigationStreamsMixin.navigation_streams_ready(self)
        ):
            delay_ms = NavigationStreamsMixin.navigation_stream_restart_delay_ms(self, output, "obstacle")
            if delay_ms is not None:
                QTimer.singleShot(delay_ms, self.start_obstacle_stream)
