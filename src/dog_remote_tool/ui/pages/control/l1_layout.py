from __future__ import annotations

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QFrame, QHBoxLayout, QLabel, QLineEdit, QPushButton, QSizePolicy, QVBoxLayout, QWidget

from dog_remote_tool.modules import control
from dog_remote_tool.ui.pages.control import helpers as control_helpers


class ControlL1LayoutMixin:
    def _build_l1_controls_area(self) -> None:
        l1_widget = QWidget()
        self.l1_controls_widget = l1_widget
        l1_widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        l1_layout = QVBoxLayout(l1_widget)
        l1_layout.setContentsMargins(0, 0, 0, 0)
        l1_layout.setSpacing(12)
        self.body.addWidget(l1_widget, 1)

        self.l1_video_panel, self.l1_video_source_combo, self.l1_video_view, self.l1_video_btn = self._make_video_panel("l1")
        self.l1_video_btn.setMinimumHeight(42)
        self.l1_video_btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.l1_sdk_path_input = QLineEdit(control.L1_DEFAULT_REMOTE_SDK_PATH)
        self.l1_sdk_path_input.hide()
        self.l1_sdk_box = QWidget(l1_widget)
        self.l1_sdk_box.hide()

        self.l1_posture_box = self._build_l1_posture_panel()
        self.l1_realtime_box = self._build_l1_realtime_panel()
        self.l1_current_forward_label = QLabel("--")
        self.l1_current_forward_label.setObjectName("ControlVideoSpeedBadge")
        self.l1_current_forward_label.setMinimumHeight(42)
        self.l1_current_forward_label.setAlignment(Qt.AlignCenter)

        self.control_header_actions.addWidget(self.l1_posture_box, 4)
        self.control_header_actions.addWidget(self.l1_realtime_box, 3)
        self.control_header_actions.addWidget(self.l1_current_forward_label, 1)
        self.control_header_actions.addWidget(self.l1_video_btn, 1)
        l1_layout.addWidget(self.l1_video_panel, 1, alignment=Qt.AlignHCenter)

        hidden_metrics = QWidget(l1_widget)
        hidden_metrics.hide()
        hidden_layout = QVBoxLayout(hidden_metrics)
        hidden_layout.setContentsMargins(0, 0, 0, 0)
        hidden_layout.setSpacing(0)
        self.l1_target_forward_label = self._make_l1_metric_label("前后 --")
        self.l1_target_strafe_label = self._make_l1_metric_label("横移 --")
        self.l1_target_turn_label = self._make_l1_metric_label("转向 --")
        self.l1_sdk_limit_label = self._make_l1_metric_label("上限 --")
        self.l1_linear_speed_label = self._make_l1_metric_label("前后 --")
        self.l1_translate_speed_label = self._make_l1_metric_label("横移 --")
        self.l1_angular_speed_label = self._make_l1_metric_label("角速度 --")
        self.l1_ctrl_mode_label = self._make_l1_metric_label("控制模式 --")
        self.l1_ctrl_mode_label.setToolTip("SDK getCurrentCtrlmode：0 阻尼，1 站立，3 移动")
        for metric in (
            self.l1_target_forward_label,
            self.l1_target_strafe_label,
            self.l1_target_turn_label,
            self.l1_sdk_limit_label,
            self.l1_linear_speed_label,
            self.l1_translate_speed_label,
            self.l1_angular_speed_label,
            self.l1_ctrl_mode_label,
        ):
            hidden_layout.addWidget(metric)

    def _build_l1_posture_panel(self) -> QFrame:
        l1_action_box = QFrame()
        l1_action_box.setObjectName("ControlInlineGroup")
        l1_action_box.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Maximum)
        l1_action_layout = QHBoxLayout(l1_action_box)
        l1_action_layout.setContentsMargins(0, 0, 0, 0)
        l1_action_layout.setSpacing(10)
        l1_action_title = QLabel("姿态动作")
        l1_action_title.setObjectName("DiagSectionTitle")
        l1_action_layout.addWidget(l1_action_title)
        l1_stand_btn = QPushButton("站立/恢复")
        l1_stand_btn.setObjectName("Primary")
        l1_stand_btn.clicked.connect(lambda: self.run_l1_sdk_action("stand"))
        l1_lie_btn = QPushButton("低姿态")
        l1_lie_btn.setToolTip("SDK lieDown：降低机身高度")
        l1_lie_btn.clicked.connect(lambda: self.run_l1_sdk_action("lie"))
        l1_passive_btn = QPushButton("阻尼趴下")
        l1_passive_btn.setObjectName("Danger")
        l1_passive_btn.setToolTip("SDK passive：进入阻尼状态并完全趴下")
        l1_passive_btn.clicked.connect(lambda: self.run_l1_sdk_action("passive"))
        for button in (l1_stand_btn, l1_lie_btn, l1_passive_btn):
            button.setMinimumHeight(42)
            button.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            l1_action_layout.addWidget(button, 1)
        return l1_action_box

    def _build_l1_realtime_panel(self) -> QFrame:
        l1_keyboard_box = QFrame()
        self.l1_keyboard_box = l1_keyboard_box
        l1_keyboard_box.setObjectName("ControlInlineGroup")
        l1_keyboard_box.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Maximum)
        l1_keyboard_layout = QHBoxLayout(l1_keyboard_box)
        l1_keyboard_layout.setContentsMargins(0, 0, 0, 0)
        l1_keyboard_layout.setSpacing(10)
        self.l1_sdk_stream_status = QLabel("未连接")
        self.l1_sdk_stream_status.setObjectName("BagStatusWarn")
        self.l1_sdk_speed_value = QLabel(f"线速度 {control_helpers.LINEAR_SPEED_DEFAULT_MPS:.1f} m/s")
        self.l1_sdk_speed_value.setObjectName("ControlSpeedValue")
        self.l1_sdk_speed_value.setParent(l1_keyboard_box)
        self.l1_sdk_speed_value.hide()
        self.l1_start_stream_btn = QPushButton("开始遥控")
        self.l1_start_stream_btn.setObjectName("Primary")
        self.l1_start_stream_btn.clicked.connect(self.toggle_l1_sdk_stream)
        self.l1_start_stream_btn.setMinimumHeight(42)
        self.l1_start_stream_btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        l1_keyboard_layout.addWidget(self.l1_sdk_stream_status)
        l1_keyboard_layout.addWidget(self.l1_start_stream_btn, 1)
        return l1_keyboard_box
