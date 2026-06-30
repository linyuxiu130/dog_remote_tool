from __future__ import annotations

import time

from PyQt5.QtCore import QProcess, QTimer

from dog_remote_tool.core.profiles import ProductProfile
from dog_remote_tool.modules.device_status import power
from dog_remote_tool.ui.widget_roles import set_widget_text_tooltip


BATTERY_AUTO_PROBE_MIN_INTERVAL_SECONDS = 20.0


def battery_indicator_stylesheet(percent: int | None, charging: bool = False) -> str:
    if charging:
        fill, rest, fg, border, weight = "#bfdbfe", "#e8f7ff", "#075985", "#93c5fd", 800
    elif percent is None:
        fill, rest, fg, border, weight = "#ffffff", "#ffffff", "#46566b", "#e3eaf3", 700
    elif percent < 20:
        fill, rest, fg, border, weight = "#fecaca", "#fff1f2", "#9f2d2d", "#f2c7c7", 700
    elif percent < 50:
        fill, rest, fg, border, weight = "#fed7aa", "#fff8ed", "#8b4513", "#f5dec0", 700
    else:
        fill, rest, fg, border, weight = "#bbf7d0", "#edf8f0", "#22623a", "#c9ead2", 700
    fill_stop = 0.0 if percent is None else max(0.0, min(1.0, percent / 100.0))
    rest_stop = min(1.0, fill_stop + 0.001)
    return (
        "background:qlineargradient(x1:0,y1:0,x2:1,y2:0,"
        f"stop:0 {fill},stop:{fill_stop:.3f} {fill},stop:{rest_stop:.3f} {rest},stop:1 {rest});"
        f"color:{fg};border:1px solid {border};border-radius:8px;padding:5px 9px;font-weight:{weight};"
    )


class DeviceBarBatteryMixin:
    def refresh_battery(self, request_id: int | None = None, *, force: bool = False) -> None:
        if request_id is not None and request_id != self.battery_slot.request_id:
            return
        if self.battery_slot.is_running():
            return
        if request_id is None:
            self.battery_retry_count = 0
        profile = self.current_profile()
        if not force and self._should_skip_battery_probe(profile):
            return
        spec = power.battery_command(profile)
        self.battery.setToolTip("")
        process, request_id = self.battery_slot.start_spec(spec, quiet_conflict=True)
        if process is None:
            return
        process.readyReadStandardOutput.connect(lambda: self._read_battery_output(process, request_id))
        process.finished.connect(lambda exit_code, _status: self._battery_finished(process, request_id, exit_code))
        process.start()

    def _should_skip_battery_probe(self, profile: ProductProfile) -> bool:
        now = time.monotonic()
        target = self._battery_cache_key(profile)
        if target == self.last_battery_probe_target and now - self.last_battery_probe < BATTERY_AUTO_PROBE_MIN_INTERVAL_SECONDS:
            return True
        self.last_battery_probe_target = target
        self.last_battery_probe = now
        return False

    def _read_battery_output(self, process: QProcess, request_id: int) -> bool:
        return self.battery_slot.read_available_output(process, request_id)

    def _battery_finished(self, process: QProcess, request_id: int, exit_code: int) -> bool:
        output = self.battery_slot.finish(process, request_id)
        if output is None:
            return False
        status = power.parse_battery_status_output(output)
        if exit_code != 0:
            self.battery.setText("电量失败")
            self._set_battery_style(None)
            return True
        if status is None:
            self._retry_battery_read(request_id)
            return True
        self.battery_retry_count = 0
        self.battery_cache[self._battery_cache_key(self.current_profile())] = status.percent
        self._show_battery(status.percent, status.charging)
        return True

    def _battery_cache_key(self, profile: ProductProfile) -> str:
        source = power.battery_source_profile(profile)
        return f"{source.user}@{source.host}"

    def _retry_battery_read(self, request_id: int) -> None:
        if request_id != self.battery_slot.request_id:
            return
        self.battery_retry_count += 1
        if self.battery_retry_count > 2:
            return
        QTimer.singleShot(10_000, lambda: self.refresh_battery(request_id, force=True))

    def _show_battery(self, percent: int, charging: bool = False) -> None:
        self.battery_last_percent = percent
        self.battery_last_charging = charging
        if charging:
            set_widget_text_tooltip(self.battery, f"充电中 {percent}%", "远端报告正在充电")
        else:
            set_widget_text_tooltip(self.battery, f"电量 {percent}%", "")
        self._set_battery_style(percent, charging)

    def mark_battery_charging_hint(self) -> bool:
        self.battery_last_charging = True
        if self.battery_last_percent is not None:
            self._show_battery(self.battery_last_percent, True)
        else:
            set_widget_text_tooltip(self.battery, "充电中 --", "ARC 回充已完成，等待电量百分比刷新")
            self._set_battery_style(None, True)
        return True

    def _set_battery_style(self, percent: int | None, charging: bool = False) -> None:
        self.battery.setStyleSheet(battery_indicator_stylesheet(percent, charging))

    def clear_battery_charging_hint(self) -> bool:
        if not self.battery_last_charging:
            return False
        if self.battery_last_percent is not None:
            self._show_battery(self.battery_last_percent, False)
        else:
            self.battery_last_charging = False
            set_widget_text_tooltip(self.battery, "电量 --", "")
            self._set_battery_style(None, False)
        return True
