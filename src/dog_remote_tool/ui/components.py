from __future__ import annotations

from PyQt5.QtCore import QSettings, QTimer, Qt, pyqtSignal
from PyQt5.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from ..core.runner import ProcessRunner
from dog_remote_tool.ui.command_confirm import command_display_command, confirm_command_spec, confirm_dangerous_action
from dog_remote_tool.ui.command_page import CommandPage, field_row
from dog_remote_tool.ui.device_bar_battery import (
    BATTERY_AUTO_PROBE_MIN_INTERVAL_SECONDS,
    DeviceBarBatteryMixin,
    battery_indicator_stylesheet,
)
from dog_remote_tool.ui.device_bar_connection import (
    CONNECTION_PENDING_STYLE,
    DeviceBarConnectionMixin,
)
from dog_remote_tool.ui.device_bar_profile import DeviceBarProfileMixin
from .log_panel import LOG_TIMESTAMP_PATTERN, LogHighlighter, LogPanel
from .process_utils import ProcessSlot
from .product_selector import ProductSelector, looks_accidental_stored_profile_value


__all__ = [
    "BATTERY_AUTO_PROBE_MIN_INTERVAL_SECONDS",
    "CommandPage",
    "DeviceBar",
    "LOG_TIMESTAMP_PATTERN",
    "LogHighlighter",
    "LogPanel",
    "ProductSelector",
    "command_display_command",
    "confirm_dangerous_action",
    "confirm_command_spec",
    "field_row",
    "looks_accidental_stored_profile_value",
]

BATTERY_REFRESH_INTERVAL_MS = 120_000


class DeviceBar(DeviceBarProfileMixin, DeviceBarBatteryMixin, DeviceBarConnectionMixin, QFrame):
    profile_changed = pyqtSignal(object)
    connection_changed = pyqtSignal(bool)

    def __init__(self, runner: ProcessRunner, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("TopBar")
        self.runner = runner
        self.battery_slot = ProcessSlot(self, reserve_runner=False)
        self.connection_slot = ProcessSlot(self, reserve_runner=False)
        self.battery_retry_count = 0
        self.battery_cache: dict[str, int] = {}
        self.battery_last_percent: int | None = None
        self.battery_last_charging = False
        self.last_battery_probe = 0.0
        self.last_battery_probe_target = ""
        self.last_auto_connection_probe = 0.0
        self.last_auto_connection_target = ""
        self.settings = QSettings()
        self.loading_profile = False
        self.selector = ProductSelector()
        last_key = self.settings.value("device_bar/current_key", "", type=str)
        if last_key:
            self.selector.set_key(last_key)
        self.host = QLineEdit()
        self.user = QLineEdit()
        self.password = QLineEdit()
        for edit in (self.host, self.user, self.password):
            edit.setMinimumWidth(0)
        self.password.setEchoMode(QLineEdit.Password)
        self.status = QLabel("未连接")
        self.status.setAlignment(Qt.AlignCenter)
        self.status.setMinimumWidth(88)
        self.status.setStyleSheet(CONNECTION_PENDING_STYLE)
        self.battery = QLabel("电量 --")
        self.battery.setAlignment(Qt.AlignCenter)
        self.battery.setMinimumWidth(108)
        self.battery.setToolTip("")
        self.battery.setStyleSheet(battery_indicator_stylesheet(None))

        self.battery_timer = QTimer(self)
        self.battery_timer.setInterval(BATTERY_REFRESH_INTERVAL_MS)
        self.battery_timer.timeout.connect(self.refresh_battery)
        self.connection_edit_timer = QTimer(self)
        self.connection_edit_timer.setSingleShot(True)
        self.connection_edit_timer.setInterval(1200)
        self.connection_edit_timer.timeout.connect(lambda: self.test_connection(manual=False))

        root = QVBoxLayout(self)
        root.setContentsMargins(10, 8, 10, 8)
        root.setSpacing(7)

        title = QLabel("当前设备")
        title.setObjectName("FieldLabel")
        ip_label = QLabel("IP")
        ip_label.setObjectName("FieldLabel")
        user_label = QLabel("用户")
        user_label.setObjectName("FieldLabel")
        password_label = QLabel("密码")
        password_label.setObjectName("FieldLabel")

        top_row = QHBoxLayout()
        top_row.setContentsMargins(0, 0, 0, 0)
        top_row.setSpacing(8)
        self.selector.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        top_row.addWidget(title)
        top_row.addWidget(self.selector, 1)
        top_row.addWidget(self.battery)
        top_row.addWidget(self.status)
        root.addLayout(top_row)

        fields = QGridLayout()
        fields.setContentsMargins(0, 0, 0, 0)
        fields.setHorizontalSpacing(6)
        fields.setVerticalSpacing(0)
        fields.setColumnStretch(1, 3)
        fields.setColumnStretch(3, 2)
        fields.setColumnStretch(5, 2)
        fields.addWidget(ip_label, 0, 0)
        fields.addWidget(self.host, 0, 1)
        fields.addWidget(user_label, 0, 2)
        fields.addWidget(self.user, 0, 3)
        fields.addWidget(password_label, 0, 4)
        fields.addWidget(self.password, 0, 5)
        root.addLayout(fields)

        for edit in (self.host, self.user, self.password):
            edit.textChanged.connect(self.schedule_connection_test)
        self.selector.changed.connect(self._load_profile)
        self._load_profile(self.selector.profile())
        self.battery_timer.start()

    def _stop_battery_process(self) -> None:
        self.battery_slot.stop()

    def _stop_connection_process(self) -> None:
        self.connection_slot.stop()

    def shutdown_processes(self) -> None:
        if self.battery_timer is not None:
            self.battery_timer.stop()
        self.connection_edit_timer.stop()
        self._stop_battery_process()
        self._stop_connection_process()
