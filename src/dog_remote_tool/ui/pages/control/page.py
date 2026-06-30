from __future__ import annotations

from PyQt5.QtCore import QProcess, QTimer, Qt
from PyQt5.QtWidgets import (
    QApplication,
    QComboBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from dog_remote_tool.core.runner import ProcessRunner
from dog_remote_tool.ui.components import CommandPage, DeviceBar
from dog_remote_tool.ui.process_utils import kill_process_tree, safe_delete_process, stop_process_async, stop_process_safely
from dog_remote_tool.ui.pages.control.arc import ControlArcMixin
from dog_remote_tool.ui.pages.control.l2_gamepad import ControlL2GamepadMixin
from dog_remote_tool.ui.pages.control.l1_sdk import ControlL1SdkMixin
from dog_remote_tool.ui.pages.control.l1_layout import ControlL1LayoutMixin
from dog_remote_tool.ui.pages.control.layout import ControlLayoutMixin
from dog_remote_tool.ui.pages.control.runtime import ControlRuntimeMixin
from dog_remote_tool.ui.pages.control.state import ControlStateMixin
from dog_remote_tool.ui.pages.control.stream_ui import set_button_role, write_json_line
from dog_remote_tool.ui.pages.control.lifecycle import ControlLifecycleMixin
from dog_remote_tool.ui.pages.control.telemetry import ControlTelemetryMixin
from dog_remote_tool.ui.pages.control.video import ControlVideoMixin


# Mixins and tests patch these symbols via dog_remote_tool.ui.pages.control.page.
_CONTROL_PAGE_EXPORTS = (
    QApplication,
    QComboBox,
    QDialog,
    QMessageBox,
    QProcess,
    QTimer,
    kill_process_tree,
    safe_delete_process,
    set_button_role,
    stop_process_async,
    stop_process_safely,
    write_json_line,
)


class ControlPage(
    ControlLayoutMixin,
    ControlRuntimeMixin,
    CommandPage,
    ControlStateMixin,
    ControlL1LayoutMixin,
    ControlL2GamepadMixin,
    ControlVideoMixin,
    ControlTelemetryMixin,
    ControlLifecycleMixin,
    ControlArcMixin,
    ControlL1SdkMixin,
):
    def __init__(self, runner: ProcessRunner, device_bar: DeviceBar) -> None:
        super().__init__("遥控控制", runner, device_bar)
        self._init_control_state()

        self._build_control_header()

        columns_widget = QWidget()
        self.l2_controls_widget = columns_widget
        columns_widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        controls_layout = QVBoxLayout(columns_widget)
        controls_layout.setContentsMargins(0, 0, 0, 0)
        controls_layout.setSpacing(12)
        self.body.addWidget(columns_widget, 1)

        operation_cards = QVBoxLayout()
        operation_cards.setSpacing(12)
        controls_layout.addLayout(operation_cards, 1)

        action_bar_layout = self.control_header_actions

        self.body_video_panel, self.body_video_source_combo, self.body_video_view, self.body_video_btn = self._make_video_panel("body")
        action_bar_layout.addWidget(self._build_l2_posture_panel(), 4)
        realtime_box = self._build_l2_realtime_panel()
        action_bar_layout.addWidget(realtime_box, 1)
        self.l2_current_forward_label = QLabel("--")
        self.l2_current_forward_label.setObjectName("ControlVideoSpeedBadge")
        self.l2_current_forward_label.setMinimumHeight(42)
        self.l2_current_forward_label.setAlignment(Qt.AlignCenter)
        action_bar_layout.addWidget(self.l2_current_forward_label, 1)
        self.body_video_btn.setMinimumHeight(42)
        self.body_video_btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        action_bar_layout.addWidget(self.body_video_btn, 1)
        operation_cards.addWidget(self.body_video_panel, 1, alignment=Qt.AlignHCenter)

        self._build_l1_controls_area()

        self._build_unsupported_panel()
        self.device_bar.profile_changed.connect(self.on_control_profile_changed)
        self.update_l1_target_speed_labels()
        self.update_l2_target_speed_labels()
        self.reset_l2_telemetry()
        self.refresh_video_sources()
        self.update_l2_nav_target()
