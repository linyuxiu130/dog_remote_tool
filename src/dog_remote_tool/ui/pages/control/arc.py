from __future__ import annotations

from PyQt5.QtCore import QProcess

from dog_remote_tool.core.shell import CommandSpec
from dog_remote_tool.modules import control
from dog_remote_tool.modules import mapping
import dog_remote_tool.ui.pages.control.helpers as control_helpers


def _control_page_module():
    from dog_remote_tool.ui.pages.control import page as control_page

    return control_page


class ControlArcMixin:
    def refresh_remote_arc_status(self) -> bool:
        if not self.page_active:
            return False
        if not self.arc_controls_supported():
            self.set_remote_arc_action({}, "不支持")
            return False
        if self.runner.is_running():
            return False
        if self.arc_status_slot.is_running():
            return False
        process, request_id = self.arc_status_slot.start_spec(
            CommandSpec(
                "刷新 ARC 状态",
                mapping.arc_status_snapshot_command(self.profile()),
                concurrency="parallel",
                locks=("control-arc-status",),
            )
        )
        if process is None:
            return False
        process.readyReadStandardOutput.connect(lambda: self.read_remote_arc_status_output(process, request_id))
        process.finished.connect(lambda exit_code, _status: self.remote_arc_status_finished(process, exit_code, request_id))
        process.start()
        return True

    def read_remote_arc_status_output(self, process: QProcess, request_id: int) -> bool:
        return self.arc_status_slot.read_available_output(process, request_id)

    def remote_arc_status_finished(self, process: QProcess, exit_code: int, request_id: int) -> bool:
        output = self.arc_status_slot.finish(process, request_id)
        if output is None:
            return False
        if exit_code != 0:
            self.set_remote_arc_action({}, "读取失败")
            return True
        self.set_remote_arc_action(control_helpers.parse_key_value_lines(output))
        return True

    def set_remote_arc_action(self, values: dict[str, str], override_status: str = "") -> bool:
        action, label, enabled, status = control_helpers.arc_remote_action_state(values)
        if override_status:
            action, enabled, status = "", False, override_status
        self.arc_action = action
        self.arc_action_btn.setText(label)
        self.arc_action_btn.setEnabled(enabled)
        self.arc_action_btn.setVisible(enabled)
        self.arc_action_btn.setToolTip(status)
        role = "Danger" if action == "undock" else "Primary"
        _control_page_module().set_button_role(self.arc_action_btn, label, role if enabled else "SoftPrimary")
        self.arc_action_status.setText(f"ARC {status}")
        return enabled

    def run_arc_action(self) -> bool:
        if not self.arc_action:
            return False
        spec = mapping.arc_start_action_command(self.profile(), self.arc_action)
        self.arc_status_slot.stop()
        self.stop_gamepad_stream()
        self.stop_l1_sdk_stream()
        self.runner.stop()
        self._set_control_low_load(False)
        started = self.set_command(spec)
        if started is False:
            self.arc_action_status.setText("ARC 任务未启动")
            return False
        return bool(started)

    def on_runner_task_finished(self, _task_id: int, _code: int, title: str) -> None:
        if title.startswith("执行：ARC "):
            if getattr(self, "page_active", False) and self.arc_controls_supported():
                for delay in (100, 1500, 4000):
                    _control_page_module().QTimer.singleShot(delay, self.refresh_remote_arc_status)

    def arc_controls_supported(self) -> bool:
        return bool(control.l2_control_profile(self.profile()) or control.robot_sdk_control_profile(self.profile()))
