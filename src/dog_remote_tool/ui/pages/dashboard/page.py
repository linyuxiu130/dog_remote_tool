from __future__ import annotations

from pathlib import Path

from PyQt5 import QtWidgets as _qt_widgets
from PyQt5.QtCore import QTimer, Qt
from PyQt5.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from dog_remote_tool.core.runner import ProcessRunner
from dog_remote_tool.modules import device_status as _device_status
from dog_remote_tool.ui import components as _components
from dog_remote_tool.ui import widget_roles as _widget_roles
from dog_remote_tool.ui.pages.dashboard.rows import DashboardRowsMixin
from dog_remote_tool.ui.pages.dashboard.status import DashboardStatusMixin
from dog_remote_tool.ui.process_utils import ProcessSlot


DeviceBar = _components.DeviceBar
confirm_command_spec = _components.confirm_command_spec
device_status = _device_status
widget_text = _widget_roles.widget_text
widget_tooltip = _widget_roles.widget_tooltip
QPushButton = _qt_widgets.QPushButton


class DashboardPage(DashboardRowsMixin, DashboardStatusMixin, QWidget):
    def __init__(self, app_root: Path, runner: ProcessRunner, device_bar: DeviceBar) -> None:
        super().__init__()
        _ = app_root
        self.runner = runner
        self.device_bar = device_bar
        self.status_slot = ProcessSlot(self, reserve_runner=False)
        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        content = QWidget()
        content.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        scroll.setWidget(content)
        root_layout.addWidget(scroll)

        layout = QVBoxLayout(content)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(12)

        title = QLabel("设备总览")
        title.setObjectName("AppTitle")

        header = QFrame()
        header.setObjectName("PageHeader")
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(18, 12, 18, 12)
        header_layout.setSpacing(12)
        header_layout.addWidget(title)
        self.release_title_label = QLabel(self._release_title(device_bar.current_profile()))
        self.release_title_label.setObjectName("FieldLabel")
        self.device_release_label = QLabel("读取中")
        self.device_release_label.setObjectName("MetricValue")
        self.device_release_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        header_layout.addWidget(self.release_title_label)
        header_layout.addWidget(self.device_release_label)
        header_layout.addStretch(1)
        layout.addWidget(header)

        status_box = QFrame()
        status_box.setObjectName("Panel")
        status_layout = QVBoxLayout(status_box)
        status_layout.setContentsMargins(16, 16, 16, 16)
        status_layout.setSpacing(12)

        cards = QHBoxLayout()
        cards.setContentsMargins(0, 0, 0, 0)
        cards.setSpacing(12)

        package_card = QFrame()
        package_card.setObjectName("StatusCard")
        package_card.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        package_layout = QVBoxLayout(package_card)
        package_layout.setContentsMargins(16, 14, 16, 14)
        package_layout.setSpacing(10)
        package_title = QLabel("小包版本")
        package_title.setObjectName("FieldLabel")
        self.package_summary_label = QLabel("读取中")
        self.package_summary_label.setObjectName("MetricValue")
        self.package_summary_label.setWordWrap(True)
        self.package_rows_widget = QWidget()
        self.package_rows_widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)
        self.package_rows = QGridLayout(self.package_rows_widget)
        self.package_rows.setContentsMargins(0, 0, 0, 0)
        self.package_rows.setHorizontalSpacing(14)
        self.package_rows.setVerticalSpacing(5)
        package_layout.addWidget(package_title)
        package_layout.addWidget(self.package_summary_label)
        package_layout.addWidget(self.package_rows_widget)
        package_layout.addStretch(1)

        launch_card = QFrame()
        launch_card.setObjectName("StatusCard")
        launch_card.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        launch_layout = QVBoxLayout(launch_card)
        launch_layout.setContentsMargins(16, 14, 16, 14)
        launch_layout.setSpacing(10)
        launch_title = QLabel("运行状态")
        launch_title.setObjectName("FieldLabel")
        self.launch_summary_label = QLabel("读取中")
        self.launch_summary_label.setObjectName("MetricValue")
        self.launch_summary_label.setWordWrap(True)
        self.launch_rows_widget = QWidget()
        self.launch_rows_widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)
        self.launch_rows = QGridLayout(self.launch_rows_widget)
        self.launch_rows.setContentsMargins(0, 0, 0, 0)
        self.launch_rows.setHorizontalSpacing(8)
        self.launch_rows.setVerticalSpacing(5)
        launch_layout.addWidget(launch_title)
        launch_layout.addWidget(self.launch_summary_label)
        launch_layout.addWidget(self.launch_rows_widget)
        launch_layout.addStretch(1)

        cards.addWidget(package_card, 6)
        cards.addWidget(launch_card, 8)
        status_layout.addLayout(cards)
        status_box.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        layout.addWidget(status_box)
        layout.addStretch(1)

        self.page_active = False
        self._set_current_device(device_bar.current_profile())
        device_bar.profile_changed.connect(self._set_current_device)
        self.runner.finished.connect(lambda _code: QTimer.singleShot(800, self.refresh_status) if self.page_active else None)
