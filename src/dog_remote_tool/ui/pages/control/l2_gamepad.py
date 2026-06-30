from __future__ import annotations

from dog_remote_tool.modules import control
from dog_remote_tool.ui.pages.control import helpers as control_helpers
from dog_remote_tool.ui.pages.control.l2_gamepad_stream import ControlL2GamepadStreamMixin
from dog_remote_tool.ui.widget_roles import set_widget_texts


def _control_page_module():
    from dog_remote_tool.ui.pages.control import page as control_page

    return control_page


class ControlL2GamepadMixin(ControlL2GamepadStreamMixin):
    def update_l2_target_speed_labels(self) -> bool:
        if not hasattr(self, "l2_target_forward_label"):
            return False
        is_robot_sdk = hasattr(self, "profile") and control.robot_remote_control_profile(self.profile()) is not None
        if is_robot_sdk:
            linear = control_helpers.clamp_stream_speed(
                getattr(self, "robot_sdk_linear_speed_mps", control_helpers.LINEAR_SPEED_DEFAULT_MPS),
                control_helpers.LINEAR_SPEED_MIN_MPS,
                control_helpers.LINEAR_SPEED_MAX_MPS,
            )
            angular = control_helpers.clamp_stream_speed(
                getattr(self, "robot_sdk_angular_speed_radps", control_helpers.ROBOT_REMOTE_ANGULAR_SPEED_DEFAULT_RADPS),
                control_helpers.ANGULAR_SPEED_MIN_RADPS,
                control_helpers.ANGULAR_SPEED_MAX_RADPS,
            )
            return set_widget_texts((
                (self.l2_target_forward_label, f"前后 {linear:.2f} m/s"),
                (self.l2_target_strafe_label, f"横移 {linear:.2f} m/s"),
                (self.l2_target_turn_label, f"转向 {angular:.2f} rad/s"),
                (
                    self.l2_remote_limit_label,
                    f"上限 线速度 {control_helpers.LINEAR_SPEED_MAX_MPS:.1f} m/s / 角速度 {control_helpers.ANGULAR_SPEED_MAX_RADPS:.1f} rad/s",
                ),
            ))
        return set_widget_texts((
            (self.l2_target_forward_label, "前后 --"),
            (self.l2_target_strafe_label, "横移 --"),
            (self.l2_target_turn_label, "转向 --"),
            (self.l2_remote_limit_label, "上限 --"),
        ))

    def reset_l2_telemetry(self) -> bool:
        if not hasattr(self, "l2_current_forward_label"):
            return False
        return set_widget_texts((
            (self.l2_current_forward_label, "--"),
            (self.l2_current_strafe_label, "横移 --"),
            (self.l2_current_turn_label, "角速度 --"),
            (self.l2_current_mode_label, "来源 --"),
        ))

    def current_l2_gamepad_vector(self) -> tuple[int | float, int | float, int | float, int | float]:
        if control.robot_remote_control_profile(self.profile()):
            return control_helpers.robot_sdk_velocity_vector(
                set(self.gamepad_pressed_keys),
                self.robot_sdk_linear_speed_value(),
                self.robot_sdk_angular_speed_value(),
            )
        return control_helpers.l2_gamepad_vector(
            set(self.gamepad_pressed_keys),
            self.realtime_speed_axis_value(),
            self.gamepad_inplace_mode,
        )

    def update_l2_body_telemetry(self, payload: dict) -> bool:
        if not hasattr(self, "l2_current_forward_label"):
            return False

        forward, strafe, turn, source = control_helpers.l2_telemetry_text(payload)
        return set_widget_texts((
            (self.l2_current_forward_label, forward),
            (self.l2_current_strafe_label, strafe),
            (self.l2_current_turn_label, turn),
            (self.l2_current_mode_label, source),
        ))

    def run_robot_remote_probe(self) -> bool:
        started = self.set_command(control.robot_remote_probe_command(self.profile()))
        if started is False:
            self.gamepad_stream_status.setText("任务未启动")
            self._set_label_status(self.gamepad_stream_status, "warn")
        elif started is True:
            self.gamepad_stream_status.setText("检查中...")
            self._set_label_status(self.gamepad_stream_status, "warn")
        return bool(started)

    def run_navigation_mc_mode(self, mc_mode: int) -> bool:
        self._log_control_event("navigation_mc_mode", {"mc_mode": mc_mode, "target": self.profile().target})
        started = self.set_command(control.navigation_mc_mode_command(self.profile(), mc_mode))
        if started is False:
            self.gamepad_stream_status.setText("任务未启动")
            self._set_label_status(self.gamepad_stream_status, "warn")
        return bool(started)

    def run_l2_gamepad(self, action: str) -> bool:
        control_page = _control_page_module()
        self._log_control_event("l2_action", {"action": action, "target": self.profile().target})
        robot_sdk_target = control.robot_remote_control_profile(self.profile())
        if action in {"stand", "lie", "crawl", "head"} and self.gamepad_stream_process and self.gamepad_stream_process.state() != control_page.QProcess.NotRunning:
            payload, inplace_mode = control_helpers.l2_action_payload(action)
            if inplace_mode is not None:
                self.gamepad_inplace_mode = inplace_mode
            self._write_gamepad_stream(payload)
            return True
        if robot_sdk_target is not None:
            started = self.set_command(control.robot_sdk_posture_command(self.profile(), action))
            if started is False:
                self.gamepad_stream_status.setText("任务未启动")
                self._set_label_status(self.gamepad_stream_status, "warn")
            return bool(started)
        self.gamepad_stream_status.setText("当前设备未适配")
        self._set_label_status(self.gamepad_stream_status, "warn")
        return False
