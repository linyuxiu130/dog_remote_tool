from __future__ import annotations

from PyQt5.QtCore import QProcess

from dog_remote_tool.core.qprocess_bash import configure_bash_process
from dog_remote_tool.modules import control
import dog_remote_tool.ui.pages.control.helpers as control_helpers
from dog_remote_tool.ui.pages.control.stream_ui import stream_exit_text


def _user_telemetry_message(message: object, *, error: bool = False) -> str:
    text = str(message or "").strip()
    if "telemetry stream exited" in text.lower():
        return "速度读取中断，请查看详细日志。" if error else "速度读取中断，正在重试。"
    return text


def _control_page_module():
    from dog_remote_tool.ui.pages.control import page as control_page

    return control_page


class ControlTelemetryMixin:
    def start_l2_telemetry_stream(self) -> bool:
        control_page = _control_page_module()
        if not self.page_active:
            return False
        profile = self.profile()
        if not (control.l2_control_profile(profile) or control.robot_remote_control_profile(profile)):
            return False
        if self.l2_telemetry_process and self.l2_telemetry_process.state() != control_page.QProcess.NotRunning:
            return False
        self.l2_telemetry_buffer = ""
        self.l2_telemetry_ready = False
        if hasattr(self, "l2_current_mode_label"):
            self.l2_current_mode_label.setText("来源 连接中...")
        self.l2_telemetry_request_id += 1
        request_id = self.l2_telemetry_request_id
        process = control_page.QProcess(self)
        self.l2_telemetry_process = process
        if control.robot_remote_control_profile(profile):
            command = control.robot_sdk_body_telemetry_stream_command(profile, 500)
        else:
            return False
        configure_bash_process(process, command)
        process.setProcessChannelMode(control_page.QProcess.MergedChannels)
        process.readyReadStandardOutput.connect(lambda: self.read_l2_telemetry_output(process, request_id))
        process.finished.connect(lambda code, status: self.l2_telemetry_finished(process, request_id, code, status))
        process.start()
        return True

    def read_l2_telemetry_output(self, process: QProcess, request_id: int) -> None:
        if process is not self.l2_telemetry_process or request_id != self.l2_telemetry_request_id:
            return
        data = bytes(process.readAllStandardOutput()).decode("utf-8", errors="replace")
        self.l2_telemetry_buffer, events = control_helpers.consume_control_json_stream(
            self.l2_telemetry_buffer,
            data,
            keep_partial=True,
        )
        for payload, line in events:
            if payload is None:
                self.runner.output.emit(f"[本体速度] {line}\n")
                continue
            kind = payload.get("type")
            if kind == "ready":
                self.l2_telemetry_ready = True
                topic = payload.get("topic") or "--"
                self.l2_current_mode_label.setText("来源 本体状态")
                self.runner.output.emit("[本体速度] 速度显示已开启。\n")
            elif kind == "telemetry":
                self.l2_telemetry_ready = True
                self.update_l2_body_telemetry(payload)
            elif kind == "error":
                self.l2_current_mode_label.setText("来源 读取失败")
                self.runner.output.emit(f"[本体速度] 速度读取失败：{_user_telemetry_message(payload.get('message'), error=True)}\n")
            elif kind == "log":
                message = _user_telemetry_message(payload.get("message"))
                if message:
                    self.runner.output.emit(f"[本体速度] {message}\n")

    def l2_telemetry_finished(self, process: QProcess, request_id: int, code: int, _status) -> None:
        control_page = _control_page_module()
        if process is not self.l2_telemetry_process or request_id != self.l2_telemetry_request_id:
            control_page.safe_delete_process(process)
            return
        self.read_l2_telemetry_output(process, request_id)
        self.l2_telemetry_process = None
        self.l2_telemetry_buffer = ""
        self.l2_telemetry_ready = False
        if hasattr(self, "l2_current_mode_label"):
            self.l2_current_mode_label.setText(stream_exit_text(code, "来源 "))
        control_page.safe_delete_process(process)

    def stop_l2_telemetry_stream(self, *, wait_for_exit: bool = False) -> bool:
        control_page = _control_page_module()
        process = self.l2_telemetry_process
        was_running = process is not None and process.state() != control_page.QProcess.NotRunning
        self.l2_telemetry_request_id += 1
        self.l2_telemetry_process = None
        self.l2_telemetry_buffer = ""
        self.l2_telemetry_ready = False
        self.reset_l2_telemetry()
        if wait_for_exit:
            control_page.stop_process_safely(process)
        else:
            control_page.stop_process_async(process)
        return was_running
