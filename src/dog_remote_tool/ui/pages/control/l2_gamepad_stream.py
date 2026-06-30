from __future__ import annotations

import json

from PyQt5.QtCore import QProcess, Qt

from dog_remote_tool.core.qprocess_bash import configure_bash_process
from dog_remote_tool.modules import control
from dog_remote_tool.ui.pages.control import helpers as control_helpers
from dog_remote_tool.ui.pages.control.stream_ui import stream_exit_state, stream_exit_text


def _control_page_module():
    from dog_remote_tool.ui.pages.control import page as control_page

    return control_page


class ControlL2GamepadStreamMixin:
    def toggle_gamepad_stream(self) -> bool:
        if self.gamepad_stream_process and self.gamepad_stream_process.state() != _control_page_module().QProcess.NotRunning:
            return self.stop_gamepad_stream()
        return self.start_gamepad_stream()

    def start_gamepad_stream(self) -> bool:
        control_page = _control_page_module()
        if not self.page_active:
            return False
        if not (control.l2_control_profile(self.profile()) or control.robot_remote_control_profile(self.profile())):
            control_page.QMessageBox.warning(self, "不支持", "当前设备未适配遥控工作台，请切换到已支持的设备。")
            return False
        self.stop_l1_sdk_stream()
        self.stop_gamepad_stream()
        self.gamepad_stream_ready = False
        self.gamepad_stream_buffer = ""
        self.gamepad_inplace_mode = False
        self.gamepad_stream_last_vector = None
        self.gamepad_pressed_keys.clear()
        self.gamepad_stream_status.setText("连接中...")
        self._set_label_status(self.gamepad_stream_status, "warn")
        control_page.set_button_role(self.start_stream_btn, "停止遥控", "Danger")

        profile = self.profile()
        self.gamepad_stream_request_id += 1
        request_id = self.gamepad_stream_request_id
        process = control_page.QProcess(self)
        self.gamepad_stream_process = process
        command = control.body_realtime_stream_command(profile, self.realtime_max_axis_value(), 20)
        configure_bash_process(process, command)
        process.setProcessChannelMode(control_page.QProcess.MergedChannels)
        process.readyReadStandardOutput.connect(lambda: self.read_gamepad_stream_output(process, request_id))
        process.finished.connect(lambda code, status: self.gamepad_stream_finished(process, request_id, code, status))
        process.start()
        self.gamepad_stream_timer.start()
        self._set_control_low_load(True)
        self._log_control_event("l2_stream_start", {"target": profile.target, "interval_ms": 20})
        self.setFocus(Qt.OtherFocusReason)
        return True

    def read_gamepad_stream_output(self, process: QProcess, request_id: int) -> None:
        if process is not self.gamepad_stream_process or request_id != self.gamepad_stream_request_id:
            return
        data = bytes(process.readAllStandardOutput()).decode("utf-8", errors="replace")
        self.gamepad_stream_buffer, events = control_helpers.consume_control_json_stream(
            self.gamepad_stream_buffer,
            data,
            keep_partial=True,
        )
        for payload, line in events:
            if payload is None:
                self.runner.output.emit(f"[实时遥控] {line}\n")
                continue
            kind = payload.get("type")
            if kind == "ready":
                self.gamepad_stream_ready = True
                self.gamepad_stream_status.setText("键盘遥控中")
                self._set_label_status(self.gamepad_stream_status, "ok")
                self.runner.output.emit(control_helpers.l2_stream_log_line(payload))
                axes = payload.get("abs")
                if isinstance(axes, dict):
                    self.runner.output.emit(f"[实时遥控] 轴范围: {json.dumps(axes, ensure_ascii=False)}\n")
            elif kind == "error":
                self.runner.output.emit(control_helpers.l2_stream_log_line(payload))
            elif kind == "state":
                self.runner.output.emit(control_helpers.l2_stream_log_line(payload))
            elif kind == "result":
                inplace_mode = control_helpers.l2_stream_result_inplace_mode(payload)
                if inplace_mode is not None:
                    self.gamepad_inplace_mode = inplace_mode
                self.runner.output.emit(control_helpers.l2_stream_log_line(payload))

    def gamepad_stream_finished(self, process: QProcess, request_id: int, code: int, _status) -> None:
        control_page = _control_page_module()
        if process is not self.gamepad_stream_process or request_id != self.gamepad_stream_request_id:
            control_page.safe_delete_process(process)
            return
        self.read_gamepad_stream_output(process, request_id)
        self.gamepad_stream_timer.stop()
        self.gamepad_pressed_keys.clear()
        self.gamepad_stream_process = None
        self.gamepad_stream_ready = False
        self.gamepad_stream_buffer = ""
        self.gamepad_inplace_mode = False
        self.gamepad_stream_last_vector = None
        self.gamepad_stream_status.setText(stream_exit_text(code))
        self._set_label_status(self.gamepad_stream_status, stream_exit_state(code))
        control_page.set_button_role(self.start_stream_btn, "开始遥控", "Primary")
        self._set_control_low_load(False)
        self._log_control_event("l2_stream_finished", {"code": code})
        control_page.safe_delete_process(process)

    def stop_gamepad_stream(self, *, wait_for_exit: bool = False) -> bool:
        control_page = _control_page_module()
        process = self.gamepad_stream_process
        was_running = process is not None and process.state() != control_page.QProcess.NotRunning
        self.gamepad_stream_request_id += 1
        self.gamepad_stream_process = None
        self.gamepad_stream_timer.stop()
        self.gamepad_pressed_keys.clear()
        self.gamepad_stream_buffer = ""
        self.gamepad_stream_ready = False
        self.gamepad_stream_last_vector = None
        self.gamepad_inplace_mode = False
        if process and process.state() != control_page.QProcess.NotRunning:
            self._log_control_event("l2_stream_stop", {})
            self._stop_json_stream_process(process, ({"cmd": "neutral"}, {"cmd": "quit"}), wait_for_exit=wait_for_exit)
        if hasattr(self, "gamepad_stream_status"):
            self.gamepad_stream_status.setText("未连接")
            self._set_label_status(self.gamepad_stream_status, "warn")
            control_page.set_button_role(self.start_stream_btn, "开始遥控", "Primary")
        self._set_control_low_load(False)
        return was_running

    def send_gamepad_neutral(self) -> bool:
        self.gamepad_stream_last_vector = None
        self.gamepad_pressed_keys.clear()
        return self._write_gamepad_stream({"cmd": "neutral"})

    def adjust_realtime_speed(self, delta: int) -> None:
        value = control_helpers.stepped_slider_value(
            self.realtime_speed_slider.value(),
            delta,
            self.realtime_speed_slider.singleStep(),
            self.realtime_speed_slider.minimum(),
            self.realtime_speed_slider.maximum(),
        )
        self.realtime_speed_slider.setValue(value)
        self.runner.output.emit(f"[实时遥控] 遥控速度: {value}%\n")

    def realtime_speed_changed(self, value: int) -> None:
        if hasattr(self, "realtime_speed_value"):
            self.realtime_speed_value.setText(f"速度 {value}%")
        self.update_l2_target_speed_labels()
        self.gamepad_stream_last_vector = None
        if self.gamepad_stream_ready:
            self.runner.output.emit(f"[实时遥控] 速度比例已更新: {value}%\n")
            self.send_gamepad_stream_target()

    def adjust_robot_sdk_linear_speed(self, delta: float) -> None:
        value = control_helpers.stepped_stream_speed(
            self.robot_sdk_linear_speed_value(),
            delta,
            control_helpers.LINEAR_SPEED_MIN_MPS,
            control_helpers.LINEAR_SPEED_MAX_MPS,
        )
        self.robot_sdk_linear_speed_mps = value
        if hasattr(self, "realtime_speed_value"):
            self.realtime_speed_value.setText(f"线速度 {value:.1f} m/s")
        self.update_l2_target_speed_labels()
        self.gamepad_stream_last_vector = None
        self.runner.output.emit(f"[实时遥控] 线速度: {value:.1f} m/s\n")
        if self.gamepad_stream_ready:
            self.send_gamepad_stream_target()

    def adjust_robot_sdk_angular_speed(self, delta: float) -> None:
        value = control_helpers.stepped_stream_speed(
            self.robot_sdk_angular_speed_value(),
            delta,
            control_helpers.ANGULAR_SPEED_MIN_RADPS,
            control_helpers.ANGULAR_SPEED_MAX_RADPS,
        )
        self.robot_sdk_angular_speed_radps = value
        self.update_l2_target_speed_labels()
        self.gamepad_stream_last_vector = None
        self.runner.output.emit(f"[实时遥控] 角速度: {value:.1f} rad/s\n")
        if self.gamepad_stream_ready:
            self.send_gamepad_stream_target()

    def realtime_max_axis_value(self) -> int:
        return self.realtime_speed_slider.maximum()

    def realtime_speed_axis_value(self) -> int:
        speed = max(self.realtime_speed_slider.minimum(), min(self.realtime_speed_slider.maximum(), self.realtime_speed_slider.value()))
        return int(speed)

    def robot_sdk_linear_speed_value(self) -> float:
        return control_helpers.clamp_stream_speed(
            getattr(self, "robot_sdk_linear_speed_mps", control_helpers.LINEAR_SPEED_DEFAULT_MPS),
            control_helpers.LINEAR_SPEED_MIN_MPS,
            control_helpers.LINEAR_SPEED_MAX_MPS,
        )

    def robot_sdk_angular_speed_value(self) -> float:
        return control_helpers.clamp_stream_speed(
            getattr(self, "robot_sdk_angular_speed_radps", control_helpers.ROBOT_REMOTE_ANGULAR_SPEED_DEFAULT_RADPS),
            control_helpers.ANGULAR_SPEED_MIN_RADPS,
            control_helpers.ANGULAR_SPEED_MAX_RADPS,
        )

    def send_gamepad_stream_target(self) -> None:
        if not self.gamepad_stream_ready:
            return
        vector = self.current_l2_gamepad_vector()
        if vector == self.gamepad_stream_last_vector:
            return
        self.gamepad_stream_last_vector = vector
        if control.robot_remote_control_profile(self.profile()):
            self._write_gamepad_stream(
                control_helpers.stream_set_payload(
                    vector,
                    linear_speed=self.robot_sdk_linear_speed_value(),
                    angular_speed=self.robot_sdk_angular_speed_value(),
                    linear_limit_mps=control_helpers.LINEAR_SPEED_MAX_MPS,
                    angular_limit_radps=control_helpers.ANGULAR_SPEED_MAX_RADPS,
                )
            )
            return
        self._write_gamepad_stream(control_helpers.stream_set_payload(vector))

    def _write_gamepad_stream(self, payload: dict) -> bool:
        process = self.gamepad_stream_process
        if not _control_page_module().write_json_line(process, payload):
            return False
        self._log_control_event("l2_stream_command", payload)
        return True

    def _stop_json_stream_process(
        self,
        process: QProcess,
        payloads: tuple[dict, ...],
        timeout_ms: int = 2000,
        *,
        wait_for_exit: bool = False,
    ) -> None:
        control_page = _control_page_module()
        for payload in payloads:
            control_page.write_json_line(process, payload)
        try:
            process.closeWriteChannel()
        except RuntimeError:
            return
        if process.state() == control_page.QProcess.NotRunning:
            return
        if wait_for_exit:
            control_page.stop_process_safely(process, timeout_ms)
            return
        process.terminate()
        kill_delay_ms = max(100, min(timeout_ms, 700))
        delete_delay_ms = max(kill_delay_ms + 200, min(timeout_ms + 500, 1500))
        control_page.QTimer.singleShot(kill_delay_ms, lambda p=process: self._kill_json_stream_process_if_running(p))
        control_page.QTimer.singleShot(delete_delay_ms, lambda p=process: self._delete_json_stream_process_if_stopped(p))

    def _kill_json_stream_process_if_running(self, process: QProcess) -> None:
        control_page = _control_page_module()
        try:
            if process.state() != control_page.QProcess.NotRunning:
                control_page.kill_process_tree(process)
                process.kill()
        except RuntimeError:
            return

    def _delete_json_stream_process_if_stopped(self, process: QProcess) -> None:
        control_page = _control_page_module()
        try:
            if process.state() == control_page.QProcess.NotRunning:
                control_page.safe_delete_process(process)
        except RuntimeError:
            return
