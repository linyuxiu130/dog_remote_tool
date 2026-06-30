from __future__ import annotations

from importlib import import_module

from PyQt5.QtCore import QProcess

from dog_remote_tool.core.shell import CommandSpec
from dog_remote_tool.core.parsers import parse_key_values
from dog_remote_tool.modules import remote_access
from dog_remote_tool.ui.label_status import label_stylesheet, label_text, set_label_text_style
from dog_remote_tool.ui.pages.remote_access.layout import STATUS_ERROR, STATUS_INFO, STATUS_OK, STATUS_PENDING
from dog_remote_tool.ui.widget_roles import set_button_role, widget_object_name, widget_text


def _remote_access_page_module():
    return import_module("dog_remote_tool.ui.pages.remote_access.page")


class RemoteAccessPublicStatusMixin:
    def schedule_public_status_refresh(self, delay_ms: int) -> bool:
        if not self.page_active:
            return False
        _remote_access_page_module().QTimer.singleShot(
            delay_ms,
            lambda: self.refresh_public_status() if self.page_active else False,
        )
        return True

    def refresh_public_status(self) -> bool:
        if not self.page_active:
            return False
        if self.public_status_shutdown:
            return False
        if self.public_status_slot.is_running():
            return False
        process, request_id = self.public_status_slot.start_spec(
            CommandSpec(
                "刷新公网状态",
                remote_access.public_access_probe_command(self.profile()),
                concurrency="parallel",
                locks=("remote-access-status",),
            )
        )
        if process is None:
            return False
        process.readyReadStandardOutput.connect(lambda: self._read_public_status(process, request_id))
        process.finished.connect(lambda exit_code, _status: self._public_status_finished(process, request_id, exit_code))
        process.start()
        return True

    def refresh_public_ssid(self) -> bool:
        if not self.page_active:
            return False
        if self.public_status_shutdown:
            return False
        if self.public_ssid_slot.is_running():
            return False
        process, request_id = self.public_ssid_slot.start_spec(
            CommandSpec(
                "刷新公网 SSID",
                remote_access.public_ssid_probe_command(self.profile()),
                concurrency="parallel",
                locks=("remote-access-status",),
            )
        )
        if process is None:
            return False
        process.readyReadStandardOutput.connect(lambda: self._read_public_ssid(process, request_id))
        process.finished.connect(lambda exit_code, _status: self._public_ssid_finished(process, request_id, exit_code))
        process.start()
        return True

    def _read_public_ssid(self, process: QProcess, request_id: int) -> bool:
        if self.public_status_shutdown:
            return False
        return bool(self.public_ssid_slot.read_available_text(process, request_id))

    def _public_ssid_finished(self, process: QProcess, request_id: int, exit_code: int) -> bool:
        if self.public_status_shutdown:
            self.public_ssid_slot.finish(process, request_id)
            return False
        output = self.public_ssid_slot.finish(process, request_id)
        if output is None:
            return False
        if exit_code != 0:
            return False
        ssid = parse_key_values(output).get("SSID", "")
        if ssid:
            current = widget_text(self.public_ssid)
            self.public_ssid.setText(ssid)
            return current != ssid
        return False

    def _read_public_status(self, process: QProcess, request_id: int) -> bool:
        if self.public_status_shutdown:
            return False
        return bool(self.public_status_slot.read_available_text(process, request_id))

    def _public_status_finished(self, process: QProcess, request_id: int, exit_code: int) -> bool:
        if self.public_status_shutdown:
            self.public_status_slot.finish(process, request_id)
            return False
        output = self.public_status_slot.finish(process, request_id)
        if output is None:
            return False
        if exit_code != 0:
            return self._set_public_state("unknown", "")
        values = parse_key_values(output)
        return self._set_public_state(
            values.get("STATE", "unknown"),
            values.get("PORT", ""),
            values.get("VERSION", "unknown"),
            values.get("LAUNCH_STATE", "unknown"),
        )

    def _set_public_state(self, state: str, port: str, version: str = "unknown", launch_state: str = "unknown") -> bool:
        version_text = "新版本" if version == "new" else "旧版本" if version == "old" else "版本未知"
        launch_text = f"，launch:{launch_state}" if launch_state not in {"", "unknown"} else ""
        if state == "running":
            suffix = f"：已打开 {port}" if port else "：已打开"
            text = f"公网状态{suffix}（{version_text}{launch_text}）"
            style = STATUS_OK
            button_text = "关闭公网连接"
            object_name = "Danger"
        elif state == "errored":
            text = f"公网状态：异常（{version_text}{launch_text}）"
            style = STATUS_ERROR
            button_text = "打开公网连接"
            object_name = "Primary"
        elif state == "stopped":
            text = f"公网状态：未打开（{version_text}{launch_text}）"
            style = STATUS_PENDING
            button_text = "打开公网连接"
            object_name = "Primary"
        else:
            text = "公网状态：未知"
            style = STATUS_INFO
            button_text = "打开公网连接"
            object_name = "Primary"
        current_state = getattr(self, "public_state", "")
        current_button = widget_text(self.public_button)
        current_object = widget_object_name(self.public_button)
        changed = (
            current_state != state
            or label_text(self.public_status) != text
            or label_stylesheet(self.public_status) != style
            or current_button != button_text
            or current_object != object_name
        )
        self.public_state = state
        set_label_text_style(self.public_status, text, style)
        set_button_role(self.public_button, button_text, object_name)
        return changed
