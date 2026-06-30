from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from PyQt5.QtCore import QEvent, QProcess, Qt
from PyQt5.QtWidgets import QComboBox, QLabel, QLineEdit, QTextEdit

from dog_remote_tool.modules import control
import dog_remote_tool.ui.pages.control.helpers as control_helpers
from dog_remote_tool.ui.pages.control.stream_ui import set_label_status


def _control_page_module():
    from dog_remote_tool.ui.pages.control import page as control_page

    return control_page


class ControlRuntimeMixin:
    def stop_control_tasks(self) -> None:
        self.stop_gamepad_stream()
        self.stop_l1_sdk_stream()
        self.runner.stop()
        self._set_control_low_load(False)
        self.runner.output.emit("[遥控] 已请求停止任务并回中实时遥控。\n")

    def eventFilter(self, watched, event) -> bool:
        if self.l1_sdk_stream_process and self.l1_sdk_stream_process.state() != QProcess.NotRunning:
            if event.type() not in (QEvent.KeyPress, QEvent.KeyRelease):
                return super().eventFilter(watched, event)
            if isinstance(watched, (QLineEdit, QTextEdit, QComboBox)):
                return super().eventFilter(watched, event)
            return self._handle_l1_sdk_key_event(event)

        if not self.gamepad_stream_process or self.gamepad_stream_process.state() == QProcess.NotRunning:
            return super().eventFilter(watched, event)
        if event.type() not in (QEvent.KeyPress, QEvent.KeyRelease):
            return super().eventFilter(watched, event)
        if isinstance(watched, (QLineEdit, QTextEdit, QComboBox)):
            return super().eventFilter(watched, event)

        key = event.key()
        direction = control_helpers.direction_key(key)
        action = control_helpers.l2_action_key(key)
        robot_sdk_stream = control.robot_remote_control_profile(self.profile()) is not None

        if event.type() == QEvent.KeyPress:
            if event.isAutoRepeat():
                return True
            if direction:
                self.gamepad_pressed_keys.add(direction)
                self.send_gamepad_stream_target()
                return True
            if key == Qt.Key_X:
                self.gamepad_pressed_keys.clear()
                self.send_gamepad_neutral()
                return True
            if key == Qt.Key_O:
                if robot_sdk_stream:
                    self.adjust_robot_sdk_linear_speed(-control_helpers.LINEAR_SPEED_STEP_MPS)
                else:
                    self.adjust_realtime_speed(-5)
                return True
            if key == Qt.Key_P:
                if robot_sdk_stream:
                    self.adjust_robot_sdk_linear_speed(control_helpers.LINEAR_SPEED_STEP_MPS)
                else:
                    self.adjust_realtime_speed(5)
                return True
            if robot_sdk_stream and key == Qt.Key_BracketLeft:
                self.adjust_robot_sdk_angular_speed(-control_helpers.ANGULAR_SPEED_STEP_RADPS)
                return True
            if robot_sdk_stream and key == Qt.Key_BracketRight:
                self.adjust_robot_sdk_angular_speed(control_helpers.ANGULAR_SPEED_STEP_RADPS)
                return True
            if action:
                self.gamepad_pressed_keys.clear()
                if action in {"neutral", "status"}:
                    self.send_gamepad_neutral()
                else:
                    payload, inplace_mode = control_helpers.l2_action_payload(action)
                    if inplace_mode is not None:
                        self.gamepad_inplace_mode = inplace_mode
                    self._write_gamepad_stream(payload)
                return True
        elif event.type() == QEvent.KeyRelease:
            if event.isAutoRepeat():
                return True
            if direction:
                self.gamepad_pressed_keys.discard(direction)
                self.send_gamepad_stream_target()
                return True
        return super().eventFilter(watched, event)

    def update_l2_nav_target(self) -> None:
        target = control.l2_control_profile(self.profile())
        robot_sdk_target = control.robot_remote_control_profile(self.profile())
        l1_target = control.l1_control_profile(self.profile())
        l2_visible = target is not None
        robot_sdk_visible = robot_sdk_target is not None
        l1_visible = l1_target is not None
        any_visible = l2_visible or robot_sdk_visible or l1_visible
        self.l2_overview.setVisible(any_visible)
        self.l2_controls_widget.setVisible(l2_visible or robot_sdk_visible)
        self.l1_controls_widget.setVisible(l1_visible)
        self.unsupported_box.setVisible(not any_visible)
        self.posture_box.setVisible(l2_visible or robot_sdk_visible)
        self.realtime_box.setVisible(l2_visible or robot_sdk_visible)
        self.l2_current_forward_label.setVisible(l2_visible or robot_sdk_visible)
        self.body_video_btn.setVisible(l2_visible or robot_sdk_visible)
        self.l1_posture_box.setVisible(l1_visible)
        self.l1_realtime_box.setVisible(l1_visible)
        self.l1_current_forward_label.setVisible(l1_visible)
        self.l1_video_btn.setVisible(l1_visible)
        if not (l2_visible or robot_sdk_visible):
            self.arc_status_slot.stop()
            self.set_remote_arc_action({}, "不支持")
        if not (l2_visible or robot_sdk_visible):
            self.stop_gamepad_stream()
        if not l2_visible:
            self.stop_l2_telemetry_stream()
        if not l1_visible:
            self.stop_l1_sdk_stream()
        if target:
            if self.page_active:
                _control_page_module().QTimer.singleShot(100, self.refresh_remote_arc_status)
            if self.page_active:
                self.start_l2_telemetry_stream()
            current = self.profile()
            self.control_target_badge.setText(current.label)
            self.control_target_badge.setToolTip("当前控制目标")
            self.gamepad_stream_status.setText("未连接")
            if robot_sdk_target is not None:
                self.key_hint.setText("W/S 前后，A/D 转向，Q/E 横移；X 停止，1 站立，2 趴下，3 匍匐，4 原地，O/P 调线速度，[/] 调角速度。")
            else:
                self.key_hint.setText("普通：W/S 前后，A/D 转向，Q/E 横移；原地：W/S 抬头低头，A/D 转向；X 停止，1 站立，2 趴下，3 匍匐，4 原地，O/P 调速。")
        elif robot_sdk_target:
            if self.page_active:
                _control_page_module().QTimer.singleShot(100, self.refresh_remote_arc_status)
            if self.page_active:
                self.start_l2_telemetry_stream()
            current = self.profile()
            self.control_target_badge.setText(current.label)
            self.control_target_badge.setToolTip("当前控制目标")
            self.gamepad_stream_status.setText("未连接")
            self.key_hint.setText("中狗：W/S 前后，A/D 转向，Q/E 横移；X 停止，1 站立，2 趴下，3 匍匐，4 原地，O/P 调线速度，[/] 调角速度。")
        elif l1_target:
            current = self.profile()
            self.control_target_badge.setText(current.label)
            self.control_target_badge.setToolTip("当前控制目标")
            self.l1_sdk_stream_status.setText("未连接")

    def _set_label_status(self, label: QLabel, state: str) -> None:
        set_label_status(label, state)

    def _set_control_low_load(self, enabled: bool) -> None:
        timer = getattr(self.device_bar, "battery_timer", None)
        if timer is None:
            return
        if enabled:
            timer.stop()
        elif not timer.isActive():
            timer.start()

    def _log_control_event(self, event: str, payload: dict) -> None:
        try:
            log_dir = Path.home() / ".cache" / "dog_remote_tool"
            log_dir.mkdir(parents=True, exist_ok=True)
            profile = self.profile()
            record = {
                "time": datetime.now().isoformat(timespec="milliseconds"),
                "event": event,
                "device": profile.key,
                "target": profile.target,
                "payload": payload,
            }
            with (log_dir / "control_actions.log").open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n")
        except OSError:
            return
