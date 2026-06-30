from __future__ import annotations

import time

from PyQt5.QtCore import QProcess

from dog_remote_tool.core.shell import CommandSpec, ssh_command
from dog_remote_tool.ui.label_status import set_label_text_style


CONNECTION_PENDING_STYLE = "color:#8a5a00; font-weight:700;"
CONNECTION_ACTIVE_STYLE = "color:#1f6fc9; font-weight:700;"
CONNECTION_OK_STYLE = "color:#167c3f; font-weight:700;"


class DeviceBarConnectionMixin:
    def test_connection(self, manual: bool = True, request_id: int | None = None) -> None:
        if request_id is not None and request_id != self.connection_slot.request_id:
            return
        if self.connection_slot.is_running():
            return
        profile = self.current_profile()
        target_key = f"{profile.user}@{profile.host}"
        if not manual:
            now = time.monotonic()
            if target_key == self.last_auto_connection_target and now - self.last_auto_connection_probe < 60:
                return
            self.last_auto_connection_target = target_key
            self.last_auto_connection_probe = now
        spec = CommandSpec("连接检测", ssh_command(profile, "echo ONLINE"), concurrency="parallel")
        set_label_text_style(self.status, "连接中" if manual else "验证中", CONNECTION_ACTIVE_STYLE)
        if manual:
            self.connection_changed.emit(False)
        process, request_id = self.connection_slot.start_spec(spec, quiet_conflict=not manual)
        if process is None:
            set_label_text_style(self.status, "未连接" if manual else "未验证", CONNECTION_PENDING_STYLE)
            return
        process.readyReadStandardOutput.connect(lambda: self._read_connection_output(process, request_id))
        process.finished.connect(
            lambda exit_code, _status: self._connection_finished(process, request_id, exit_code, manual=manual)
        )
        process.start()

    def _read_connection_output(self, process: QProcess, request_id: int) -> bool:
        return self.connection_slot.read_available_output(process, request_id)

    def _connection_finished(self, process: QProcess, request_id: int, exit_code: int, manual: bool = True) -> bool:
        output = self.connection_slot.finish(process, request_id)
        if output is None:
            return False
        if exit_code == 0 and "ONLINE" in output:
            self.status.setToolTip("")
            set_label_text_style(self.status, "已连接", CONNECTION_OK_STYLE)
            self.connection_changed.emit(True)
        else:
            if manual:
                self.status.setToolTip("连接失败，请检查设备网络或登录信息。")
                set_label_text_style(self.status, "未连接", CONNECTION_PENDING_STYLE)
                self.connection_changed.emit(False)
            else:
                self.status.setToolTip("自动连接验证失败；功能区仍会直接尝试远端命令。")
                set_label_text_style(self.status, "未验证", CONNECTION_PENDING_STYLE)
        return True
