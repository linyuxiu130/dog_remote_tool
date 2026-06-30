from __future__ import annotations

from importlib import import_module

from PyQt5.QtCore import Qt, QProcess

from dog_remote_tool.core.log_format import log_line
from dog_remote_tool.core.shell import CommandSpec
from dog_remote_tool.modules.remote_access import wifi as remote_wifi
from dog_remote_tool.ui.label_status import set_label_text_style
from dog_remote_tool.ui.pages.remote_access.layout import STATUS_ACTIVE, STATUS_ERROR, STATUS_INFO, STATUS_OK, STATUS_PENDING
from dog_remote_tool.ui.widget_roles import widget_enabled


def _remote_access_page_module():
    return import_module("dog_remote_tool.ui.pages.remote_access.page")


class RemoteAccessWifiStatusMixin:
    def _refresh_wifi_controls(self) -> bool:
        supported = remote_wifi.supports_3588_wifi(self.profile())
        current_scan = widget_enabled(self.wifi_scan_btn)
        current_connect = widget_enabled(self.wifi_connect_btn)
        current_combo = widget_enabled(self.wifi_combo)
        changed = current_scan != supported or current_connect != supported or current_combo != supported
        self.wifi_scan_btn.setEnabled(supported)
        self.wifi_connect_btn.setEnabled(supported)
        self.wifi_combo.setEnabled(supported)
        if not supported:
            changed = set_label_text_style(self.wifi_status, "WiFi状态：请选择 RK3588 目标", STATUS_INFO) or changed
        return changed

    def scan_wifi_networks(self) -> bool:
        if not self.page_active:
            return False
        if not remote_wifi.supports_3588_wifi(self.profile()):
            self._refresh_wifi_controls()
            return False
        if self.wifi_scan_slot.is_running():
            return False
        self.wifi_scan_btn.setEnabled(False)
        set_label_text_style(self.wifi_status, "WiFi状态：扫描中...", STATUS_ACTIVE)
        process, request_id = self.wifi_scan_slot.start_spec(
            CommandSpec("扫描 3588 WiFi", remote_wifi.scan_command(self.profile()), concurrency="parallel", locks=("remote-wifi",))
        )
        if process is None:
            self.wifi_scan_btn.setEnabled(True)
            return False
        process.readyReadStandardOutput.connect(lambda: self._read_wifi_scan_output(process, request_id))
        process.finished.connect(lambda exit_code, _status: self._wifi_scan_finished(process, request_id, exit_code))
        process.start()
        return True

    def _read_wifi_scan_output(self, process: QProcess, request_id: int) -> bool:
        return bool(self.wifi_scan_slot.read_available_text(process, request_id))

    def _wifi_scan_finished(self, process: QProcess, request_id: int, exit_code: int) -> bool:
        output = self.wifi_scan_slot.finish(process, request_id)
        if output is None:
            return False
        self.wifi_scan_btn.setEnabled(remote_wifi.supports_3588_wifi(self.profile()))
        if exit_code != 0:
            reason = next((line.strip() for line in output.splitlines() if line.strip()), "")
            suffix = f"：{reason[:80]}" if reason else ""
            set_label_text_style(self.wifi_status, f"WiFi状态：扫描失败{suffix}", STATUS_ERROR)
            return True
        networks = remote_wifi.parse_scan_output(output)
        current = self.wifi_combo.currentText().strip()
        self.wifi_combo.clear()
        for network in networks:
            self.wifi_combo.addItem(network.ssid, network.ssid)
            if network.signal:
                self.wifi_combo.setItemData(self.wifi_combo.count() - 1, f"信号 {network.signal} dBm", Qt.ToolTipRole)
        if current:
            index = self.wifi_combo.findText(current)
            if index >= 0:
                self.wifi_combo.setCurrentIndex(index)
        if networks:
            set_label_text_style(self.wifi_status, f"WiFi状态：已发现 {len(networks)} 个网络", STATUS_INFO)
        else:
            set_label_text_style(self.wifi_status, "WiFi状态：未发现网络", STATUS_PENDING)
        return True

    def connect_selected_wifi(self) -> bool:
        ssid = self.wifi_combo.currentData() or self.wifi_combo.currentText().strip()
        if not ssid:
            return self.scan_wifi_networks()
        page_module = _remote_access_page_module()
        password, ok = page_module.QInputDialog.getText(
            self,
            "连接 3588 WiFi",
            f"请输入 {ssid} 的密码",
            page_module.QLineEdit.Password,
        )
        if not ok:
            return False
        return self.connect_wifi(str(ssid), password)

    def connect_wifi(self, ssid: str, password: str) -> bool:
        if self.wifi_connect_slot.is_running():
            return False
        self.wifi_connect_btn.setEnabled(False)
        set_label_text_style(self.wifi_status, f"WiFi状态：正在连接 {ssid}", STATUS_ACTIVE)
        self.runner.output.emit(log_line("info", f"开始连接 3588 WiFi：{ssid} via {remote_wifi.DEFAULT_WIFI_IFACE}", scope="远程访问"))
        process, request_id = self.wifi_connect_slot.start_spec(
            CommandSpec("连接 3588 WiFi", remote_wifi.connect_command(self.profile(), ssid, password), locks=("remote-wifi",))
        )
        if process is None:
            self.wifi_connect_btn.setEnabled(True)
            return False
        process.readyReadStandardOutput.connect(lambda: self._read_wifi_connect_output(process, request_id))
        process.finished.connect(lambda exit_code, _status: self._wifi_connect_finished(process, request_id, exit_code))
        process.start()
        return True

    def _read_wifi_connect_output(self, process: QProcess, request_id: int) -> bool:
        data = self.wifi_connect_slot.read_available_text(process, request_id)
        if data:
            self.runner.output.emit(data)
            return True
        return False

    def _wifi_connect_finished(self, process: QProcess, request_id: int, exit_code: int) -> bool:
        data = self.wifi_connect_slot.read_available_text(process, request_id)
        if data:
            self.runner.output.emit(data)
        output = self.wifi_connect_slot.finish(process, request_id)
        if output is None:
            return False
        self.wifi_connect_btn.setEnabled(remote_wifi.supports_3588_wifi(self.profile()))
        values = remote_wifi.parse_status_output(output)
        if exit_code == 0 and values.get("STATE") == "connected":
            self.runner.output.emit(log_line("success", "3588 WiFi 已连接", scope="远程访问"))
            self._set_wifi_state(values)
            self.schedule_public_status_refresh(800)
            return True
        self.runner.output.emit(log_line("failure", "3588 WiFi 连接失败", scope="远程访问"))
        technical_output = getattr(self.runner, "technical_output", None)
        emit = getattr(technical_output, "emit", None)
        if callable(emit):
            emit(log_line("failure", f"3588 WiFi 连接失败，返回码 {exit_code}", scope="远程访问"))
        set_label_text_style(self.wifi_status, "WiFi状态：连接失败", STATUS_ERROR)
        return True

    def refresh_wifi_status(self) -> bool:
        if not self.page_active or not remote_wifi.supports_3588_wifi(self.profile()):
            self._refresh_wifi_controls()
            return False
        if self.wifi_status_slot.is_running():
            return False
        process, request_id = self.wifi_status_slot.start_spec(
            CommandSpec("刷新 3588 WiFi 状态", remote_wifi.status_command(self.profile()), concurrency="parallel", locks=("remote-wifi",))
        )
        if process is None:
            return False
        process.readyReadStandardOutput.connect(lambda: self._read_wifi_status_output(process, request_id))
        process.finished.connect(lambda exit_code, _status: self._wifi_status_finished(process, request_id, exit_code))
        process.start()
        return True

    def _read_wifi_status_output(self, process: QProcess, request_id: int) -> bool:
        return bool(self.wifi_status_slot.read_available_text(process, request_id))

    def _wifi_status_finished(self, process: QProcess, request_id: int, exit_code: int) -> bool:
        output = self.wifi_status_slot.finish(process, request_id)
        if output is None:
            return False
        if exit_code != 0:
            return set_label_text_style(self.wifi_status, "WiFi状态：检测失败", STATUS_PENDING)
        return self._set_wifi_state(remote_wifi.parse_status_output(output))

    def _set_wifi_state(self, values: dict[str, str]) -> bool:
        if values.get("STATE") != "connected":
            return set_label_text_style(self.wifi_status, "WiFi状态：未连接", STATUS_PENDING)
        ssid = values.get("SSID") or "-"
        ip = values.get("IP") or "-"
        suffix = "，公网可达" if values.get("PUBLIC_TCP") == "ok" else "，公网待确认"
        text = f"WiFi状态：已连接 {ssid} / {ip}{suffix}"
        return set_label_text_style(self.wifi_status, text, STATUS_OK)
