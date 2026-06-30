from __future__ import annotations

from PyQt5.QtCore import QEvent, QProcess, Qt
from PyQt5.QtWidgets import QLabel

from dog_remote_tool.core.qprocess_bash import configure_bash_process
from dog_remote_tool.modules import control
from dog_remote_tool.ui.widget_roles import set_widget_texts
import dog_remote_tool.ui.pages.control.helpers as control_helpers
from dog_remote_tool.ui.pages.control.stream_ui import stream_exit_state, stream_exit_text


def _control_page_module():
    from dog_remote_tool.ui.pages.control import page as control_page

    return control_page


class ControlL1SdkMixin:
    def _make_l1_metric_label(self, text: str) -> QLabel:
        label = QLabel(text)
        label.setObjectName("ControlSpeedValue")
        label.setMinimumHeight(30)
        label.setAlignment(Qt.AlignVCenter | Qt.AlignLeft)
        return label

    def update_l1_target_speed_labels(self) -> bool:
        if not hasattr(self, "l1_target_forward_label"):
            return False
        linear = control_helpers.clamp_stream_speed(
            getattr(self, "l1_sdk_linear_speed_mps", control_helpers.LINEAR_SPEED_DEFAULT_MPS),
            control_helpers.LINEAR_SPEED_MIN_MPS,
            control_helpers.LINEAR_SPEED_MAX_MPS,
        )
        angular = control_helpers.clamp_stream_speed(
            getattr(self, "l1_sdk_angular_speed_radps", control_helpers.ANGULAR_SPEED_DEFAULT_RADPS),
            control_helpers.ANGULAR_SPEED_MIN_RADPS,
            control_helpers.ANGULAR_SPEED_MAX_RADPS,
        )
        vx_max, vy_max, yaw_max = self.l1_sdk_limits
        forward = f"前后 {min(linear, vx_max):.2f} m/s"
        strafe = f"横移 {min(linear, vy_max):.2f} m/s"
        turn = f"转向 {min(angular, yaw_max):.2f} rad/s"
        limit = f"上限 线速度 {control_helpers.LINEAR_SPEED_MAX_MPS:.1f} m/s / 角速度 {control_helpers.ANGULAR_SPEED_MAX_RADPS:.1f} rad/s"
        return set_widget_texts((
            (self.l1_target_forward_label, forward),
            (self.l1_target_strafe_label, strafe),
            (self.l1_target_turn_label, turn),
            (self.l1_sdk_limit_label, limit),
        ))

    def l1_sdk_path(self) -> str:
        value = self.l1_sdk_path_input.text().strip()
        return value or control.L1_DEFAULT_REMOTE_SDK_PATH

    def prepare_l1_sdk(self) -> bool:
        started = self.set_command(control.l1_sdk_prepare_auto_command(self.profile(), self.l1_sdk_path()))
        if started is False:
            self.l1_sdk_stream_status.setText("任务未启动")
            self._set_label_status(self.l1_sdk_stream_status, "warn")
        return bool(started)

    def deploy_l1_sdk(self) -> bool:
        started = self.set_command(control.l1_sdk_deploy_command(self.profile(), str(control.L1_LOCAL_SDK_PATH), self.l1_sdk_path()))
        if started is False:
            self.l1_sdk_stream_status.setText("任务未启动")
            self._set_label_status(self.l1_sdk_stream_status, "warn")
        return bool(started)

    def run_l1_sdk_action(self, action: str) -> bool:
        control_page = _control_page_module()
        if self.l1_sdk_stream_process and self.l1_sdk_stream_process.state() != control_page.QProcess.NotRunning:
            if action in {"stand", "lie", "passive", "crawl"}:
                self.l1_pressed_keys.clear()
                self.l1_sdk_last_vector = None
            self._write_l1_sdk_stream({"cmd": action})
            return True
        started = self.set_command(control.l1_sdk_basic_action_command(self.profile(), self.l1_sdk_path(), action))
        if started is False:
            self.l1_sdk_stream_status.setText("任务未启动")
            self._set_label_status(self.l1_sdk_stream_status, "warn")
        return bool(started)

    def toggle_l1_sdk_stream(self) -> bool:
        control_page = _control_page_module()
        if self.l1_sdk_stream_process and self.l1_sdk_stream_process.state() != control_page.QProcess.NotRunning:
            return self.stop_l1_sdk_stream()
        return self.start_l1_sdk_stream()

    def start_l1_sdk_stream(self) -> bool:
        control_page = _control_page_module()
        if not self.page_active:
            return False
        if not control.l1_control_profile(self.profile()):
            control_page.QMessageBox.warning(self, "不支持", "当前设备不是小狗一代，无法使用 L1 SDK 键盘遥控。")
            return False
        self.stop_gamepad_stream()
        self.stop_l1_sdk_stream()
        self.l1_sdk_stream_ready = False
        self.l1_sdk_last_vector = None
        self.l1_sdk_stream_buffer = ""
        self.l1_pressed_keys.clear()
        self.l1_sdk_stream_status.setText("连接中...")
        self.reset_l1_telemetry()
        self._set_label_status(self.l1_sdk_stream_status, "warn")
        control_page.set_button_role(self.l1_start_stream_btn, "停止遥控", "Danger")

        profile = self.profile()
        self.l1_sdk_stream_request_id += 1
        request_id = self.l1_sdk_stream_request_id
        process = control_page.QProcess(self)
        self.l1_sdk_stream_process = process
        check_command = control.l1_sdk_prepare_auto_command(profile, self.l1_sdk_path()).command
        sync_command = control.l1_sdk_deploy_command(profile, str(control.L1_LOCAL_SDK_PATH), self.l1_sdk_path()).command
        stream_command = control.l1_sdk_stream_command(profile, self.l1_sdk_path(), 100, 20)
        command = (
            "set -e\n"
            f"if {check_command} >/tmp/dog_remote_l1_sdk_check.log 2>&1; then\n"
            "  echo '[L1 SDK] 使用远端 SDK，启动键盘遥控。'\n"
            "else\n"
            "  echo '[L1 SDK] 远端 SDK 不完整，正在同步。'\n"
            f"  {sync_command}\n"
            "  echo '[L1 SDK] SDK 同步完成，启动键盘遥控。'\n"
            "fi\n"
            f"{stream_command}\n"
        )
        configure_bash_process(process, command)
        process.setProcessChannelMode(control_page.QProcess.MergedChannels)
        process.readyReadStandardOutput.connect(lambda: self.read_l1_sdk_stream_output(process, request_id))
        process.finished.connect(lambda code, status: self.l1_sdk_stream_finished(process, request_id, code, status))
        process.start()
        self.l1_sdk_stream_timer.start()
        self._set_control_low_load(True)
        self._log_control_event("l1_stream_start", {"target": profile.target})
        self.setFocus(Qt.OtherFocusReason)
        return True

    def read_l1_sdk_stream_output(self, process: QProcess, request_id: int) -> None:
        if process is not self.l1_sdk_stream_process or request_id != self.l1_sdk_stream_request_id:
            return
        data = bytes(process.readAllStandardOutput()).decode("utf-8", errors="replace")
        self.l1_sdk_stream_buffer, events = control_helpers.consume_control_json_stream(
            self.l1_sdk_stream_buffer,
            data,
            keep_partial=True,
        )
        for payload, line in events:
            if payload is None:
                self.runner.technical_output.emit(f"[L1 遥控] {line}\n")
                continue
            kind = payload.get("type")
            if kind == "ready":
                self.l1_sdk_stream_ready = True
                self.l1_sdk_stream_status.setText("键盘遥控中")
                self._set_label_status(self.l1_sdk_stream_status, "ok")
                limits = payload.get("limits") or {}
                try:
                    self.l1_sdk_limits = (
                        float(limits.get("vx", self.l1_sdk_limits[0])),
                        float(limits.get("vy", self.l1_sdk_limits[1])),
                        float(limits.get("yaw", self.l1_sdk_limits[2])),
                    )
                    self.update_l1_target_speed_labels()
                except (TypeError, ValueError):
                    pass
                self.runner.output.emit(control_helpers.l1_stream_ready_log(payload))
                if payload.get("stand_ready"):
                    self.runner.output.emit("[L1 遥控] 当前已在站立或移动状态，方向键会立即发送速度指令。\n")
            elif kind == "error":
                self.runner.output.emit(control_helpers.l1_stream_log_line(payload))
            elif kind == "log":
                self.runner.technical_output.emit(control_helpers.l1_stream_log_line(payload))
            elif kind == "result":
                self.runner.output.emit(control_helpers.l1_stream_log_line(payload))
            elif kind == "move":
                line = control_helpers.l1_stream_log_line(payload)
                if line:
                    self.runner.output.emit(line)
            elif kind == "telemetry":
                self.update_l1_telemetry(payload)

    def l1_sdk_stream_finished(self, process: QProcess, request_id: int, code: int, _status) -> None:
        control_page = _control_page_module()
        if process is not self.l1_sdk_stream_process or request_id != self.l1_sdk_stream_request_id:
            control_page.safe_delete_process(process)
            return
        self.read_l1_sdk_stream_output(process, request_id)
        self.l1_sdk_stream_timer.stop()
        self.l1_pressed_keys.clear()
        self.l1_sdk_stream_process = None
        self.l1_sdk_stream_ready = False
        self.l1_sdk_last_vector = None
        self.l1_sdk_stream_buffer = ""
        self.reset_l1_telemetry()
        self.l1_sdk_stream_status.setText(stream_exit_text(code))
        self._set_label_status(self.l1_sdk_stream_status, stream_exit_state(code))
        control_page.set_button_role(self.l1_start_stream_btn, "开始遥控", "Primary")
        self._set_control_low_load(False)
        self._log_control_event("l1_stream_finished", {"code": code})
        control_page.safe_delete_process(process)

    def stop_l1_sdk_stream(self, *, wait_for_exit: bool = False) -> bool:
        control_page = _control_page_module()
        process = self.l1_sdk_stream_process
        was_running = process is not None and process.state() != control_page.QProcess.NotRunning
        self.l1_sdk_stream_request_id += 1
        self.l1_sdk_stream_process = None
        self.l1_sdk_stream_timer.stop()
        self.l1_pressed_keys.clear()
        self.l1_sdk_stream_buffer = ""
        self.l1_sdk_stream_ready = False
        self.l1_sdk_last_vector = None
        if process and process.state() != control_page.QProcess.NotRunning:
            self._log_control_event("l1_stream_stop", {})
            self._stop_json_stream_process(process, ({"cmd": "neutral"}, {"cmd": "quit"}), wait_for_exit=wait_for_exit)
        if hasattr(self, "l1_sdk_stream_status"):
            self.l1_sdk_stream_status.setText("未连接")
            self.reset_l1_telemetry()
            self._set_label_status(self.l1_sdk_stream_status, "warn")
            control_page.set_button_role(self.l1_start_stream_btn, "开始遥控", "Primary")
        self._set_control_low_load(False)
        return was_running

    def reset_l1_telemetry(self) -> bool:
        if not hasattr(self, "l1_linear_speed_label"):
            return False
        if hasattr(self, "l1_current_forward_label"):
            self.l1_current_forward_label.setText("--")
        return set_widget_texts((
            (self.l1_linear_speed_label, "前后 --"),
            (self.l1_translate_speed_label, "横移 --"),
            (self.l1_angular_speed_label, "角速度 --"),
            (self.l1_ctrl_mode_label, "控制模式 --"),
        ))

    def update_l1_telemetry(self, payload: dict) -> bool:
        if not hasattr(self, "l1_linear_speed_label"):
            return False
        linear, translate, angular, mode = control_helpers.l1_telemetry_text(payload)
        if hasattr(self, "l1_current_forward_label"):
            self.l1_current_forward_label.setText(linear.replace("前后 ", "", 1) if linear.startswith("前后 ") else linear)
        return set_widget_texts((
            (self.l1_linear_speed_label, linear),
            (self.l1_translate_speed_label, translate),
            (self.l1_angular_speed_label, angular),
            (self.l1_ctrl_mode_label, mode),
        ))

    def adjust_l1_sdk_linear_speed(self, delta: float) -> None:
        value = control_helpers.stepped_stream_speed(
            self.l1_sdk_linear_speed_value(),
            delta,
            control_helpers.LINEAR_SPEED_MIN_MPS,
            control_helpers.LINEAR_SPEED_MAX_MPS,
        )
        self.l1_sdk_linear_speed_mps = value
        self.l1_sdk_speed_value.setText(f"线速度 {value:.1f} m/s")
        self.update_l1_target_speed_labels()
        self.l1_sdk_last_vector = None
        self.runner.output.emit(f"[L1 遥控] 线速度: {value:.1f} m/s\n")
        if self.l1_sdk_stream_ready:
            self.send_l1_sdk_stream_target()

    def adjust_l1_sdk_angular_speed(self, delta: float) -> None:
        value = control_helpers.stepped_stream_speed(
            self.l1_sdk_angular_speed_value(),
            delta,
            control_helpers.ANGULAR_SPEED_MIN_RADPS,
            control_helpers.ANGULAR_SPEED_MAX_RADPS,
        )
        self.l1_sdk_angular_speed_radps = value
        self.update_l1_target_speed_labels()
        self.l1_sdk_last_vector = None
        self.runner.output.emit(f"[L1 遥控] 角速度: {value:.1f} rad/s\n")
        if self.l1_sdk_stream_ready:
            self.send_l1_sdk_stream_target()

    def l1_sdk_linear_speed_value(self) -> float:
        return control_helpers.clamp_stream_speed(
            getattr(self, "l1_sdk_linear_speed_mps", control_helpers.LINEAR_SPEED_DEFAULT_MPS),
            control_helpers.LINEAR_SPEED_MIN_MPS,
            control_helpers.LINEAR_SPEED_MAX_MPS,
        )

    def l1_sdk_angular_speed_value(self) -> float:
        return control_helpers.clamp_stream_speed(
            getattr(self, "l1_sdk_angular_speed_radps", control_helpers.ANGULAR_SPEED_DEFAULT_RADPS),
            control_helpers.ANGULAR_SPEED_MIN_RADPS,
            control_helpers.ANGULAR_SPEED_MAX_RADPS,
        )

    def send_l1_sdk_stream_target(self) -> None:
        if not self.l1_sdk_stream_ready:
            return
        linear_speed = self.l1_sdk_linear_speed_value()
        angular_speed = self.l1_sdk_angular_speed_value()
        vector = control_helpers.l1_velocity_vector(set(self.l1_pressed_keys), linear_speed, angular_speed)
        if vector == self.l1_sdk_last_vector:
            return
        self.l1_sdk_last_vector = vector
        self._write_l1_sdk_stream(
            control_helpers.stream_set_payload(
                vector,
                linear_speed=linear_speed,
                angular_speed=angular_speed,
                linear_limit_mps=control_helpers.LINEAR_SPEED_MAX_MPS,
                angular_limit_radps=control_helpers.ANGULAR_SPEED_MAX_RADPS,
            )
        )

    def _write_l1_sdk_stream(self, payload: dict) -> bool:
        process = self.l1_sdk_stream_process
        if not _control_page_module().write_json_line(process, payload):
            return False
        self._log_control_event("l1_stream_command", payload)
        return True

    def _handle_l1_sdk_key_event(self, event) -> bool:
        key = event.key()
        direction = control_helpers.direction_key(key)
        action = control_helpers.l1_action_key(key)
        if event.type() == QEvent.KeyPress:
            if event.isAutoRepeat():
                return True
            if direction:
                self.l1_pressed_keys.add(direction)
                self.send_l1_sdk_stream_target()
                return True
            if key == Qt.Key_X:
                self.l1_pressed_keys.clear()
                self.l1_sdk_last_vector = None
                self._write_l1_sdk_stream({"cmd": "neutral"})
                return True
            if key == Qt.Key_O:
                self.adjust_l1_sdk_linear_speed(-control_helpers.LINEAR_SPEED_STEP_MPS)
                return True
            if key == Qt.Key_P:
                self.adjust_l1_sdk_linear_speed(control_helpers.LINEAR_SPEED_STEP_MPS)
                return True
            if key == Qt.Key_BracketLeft:
                self.adjust_l1_sdk_angular_speed(-control_helpers.ANGULAR_SPEED_STEP_RADPS)
                return True
            if key == Qt.Key_BracketRight:
                self.adjust_l1_sdk_angular_speed(control_helpers.ANGULAR_SPEED_STEP_RADPS)
                return True
            if action:
                self.l1_pressed_keys.clear()
                self.l1_sdk_last_vector = None
                self._write_l1_sdk_stream({"cmd": action})
                return True
        elif event.type() == QEvent.KeyRelease:
            if event.isAutoRepeat():
                return True
            if direction:
                self.l1_pressed_keys.discard(direction)
                self.send_l1_sdk_stream_target()
                return True
        return False
