from __future__ import annotations

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QSizePolicy, QSlider, QVBoxLayout, QWidget

class ControlLayoutMixin:
    def _build_control_header(self) -> None:
        self.page_header.setObjectName("ControlHero")
        self.page_header_layout.removeWidget(self.page_title_label)
        header_row = QHBoxLayout()
        header_row.setSpacing(12)
        header_row.addWidget(self.page_title_label)
        overview = QWidget()
        self.l2_overview = overview
        overview_layout = QHBoxLayout(overview)
        overview_layout.setContentsMargins(0, 0, 0, 0)
        overview_layout.setSpacing(10)
        self.control_target_badge = QLabel("")
        self.control_target_badge.setObjectName("ControlBadge")
        self.control_target_badge.setMinimumWidth(132)
        self.control_target_badge.setAlignment(Qt.AlignCenter)
        stop_all_btn = QPushButton("急停")
        stop_all_btn.setObjectName("Danger")
        stop_all_btn.clicked.connect(self.stop_control_tasks)
        stop_all_btn.setToolTip("立即归零/回中当前遥控，并停止正在运行的遥控任务")
        self.arc_action_status = QLabel("")
        self.arc_action_status.hide()
        self.arc_action_btn = QPushButton("回充")
        self.arc_action_btn.setObjectName("SoftPrimary")
        self.arc_action_btn.setMinimumHeight(36)
        self.arc_action_btn.setMinimumWidth(96)
        self.arc_action_btn.clicked.connect(self.run_arc_action)
        self.arc_action_btn.hide()
        overview_layout.addWidget(self.control_target_badge)
        header_row.addWidget(overview)
        self.control_header_actions = QHBoxLayout()
        self.control_header_actions.setSpacing(10)
        header_row.addLayout(self.control_header_actions, 1)
        header_row.addWidget(self.arc_action_btn)
        header_row.addWidget(stop_all_btn)
        self.page_header_layout.addLayout(header_row)

    def _build_l2_posture_panel(self) -> QFrame:
        posture_box = QFrame()
        self.posture_box = posture_box
        posture_box.setObjectName("ControlInlineGroup")
        posture_box.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Maximum)
        posture_layout = QHBoxLayout(posture_box)
        posture_layout.setContentsMargins(0, 0, 0, 0)
        posture_layout.setSpacing(10)
        posture_title = QLabel("姿态动作")
        posture_title.setObjectName("DiagSectionTitle")
        posture_layout.addWidget(posture_title)
        stand_btn = QPushButton("站立")
        stand_btn.setObjectName("Primary")
        stand_btn.clicked.connect(lambda: self.run_l2_gamepad("stand"))
        crawl_btn = QPushButton("匍匐")
        crawl_btn.clicked.connect(lambda: self.run_l2_gamepad("crawl"))
        head_btn = QPushButton("原地")
        head_btn.clicked.connect(lambda: self.run_l2_gamepad("head"))
        opposite_knee_btn = QPushButton("对膝WALK")
        opposite_knee_btn.setToolTip("导航待命时发布零速 mc_mode_cmd=1，用于路网同膝段结束后的手动复位。")
        opposite_knee_btn.clicked.connect(lambda: self.run_navigation_mc_mode(1))
        same_knee_btn = QPushButton("同膝WALK")
        same_knee_btn.setToolTip("导航待命时发布零速 mc_mode_cmd=3，只切换导航运控模式链路。")
        same_knee_btn.clicked.connect(lambda: self.run_navigation_mc_mode(3))
        lie_btn = QPushButton("趴下")
        lie_btn.setObjectName("Danger")
        lie_btn.clicked.connect(lambda: self.run_l2_gamepad("lie"))
        for button in (stand_btn, opposite_knee_btn, same_knee_btn, lie_btn, crawl_btn, head_btn):
            button.setMinimumHeight(42)
            button.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            posture_layout.addWidget(button, 1)
        return posture_box

    def _build_l2_realtime_panel(self) -> QFrame:
        realtime_box = QFrame()
        self.realtime_box = realtime_box
        realtime_box.setObjectName("ControlInlineGroup")
        realtime_box.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Maximum)
        realtime_layout = QHBoxLayout(realtime_box)
        realtime_layout.setContentsMargins(0, 0, 0, 0)
        realtime_layout.setSpacing(10)
        self.gamepad_stream_status = QLabel("未连接")
        self.gamepad_stream_status.setObjectName("BagStatusWarn")
        self.gamepad_stream_status.hide()

        hidden_controls = QWidget(realtime_box)
        hidden_controls.hide()
        hidden_layout = QVBoxLayout(hidden_controls)
        hidden_layout.setContentsMargins(0, 0, 0, 0)
        hidden_layout.setSpacing(0)
        self.realtime_speed_value = QLabel("速度 60%")
        self.realtime_speed_value.setObjectName("ControlSpeedValue")
        self.realtime_speed_slider = QSlider(Qt.Horizontal)
        self.realtime_speed_slider.setRange(5, 100)
        self.realtime_speed_slider.setSingleStep(5)
        self.realtime_speed_slider.setPageStep(10)
        self.realtime_speed_slider.setValue(60)
        self.realtime_speed_slider.setToolTip("拖动后立即影响 W/S/A/D/Q/E 的遥控速度。")
        self.realtime_speed_slider.valueChanged.connect(self.realtime_speed_changed)
        slower_btn = QPushButton("-")
        slower_btn.setObjectName("TinyButton")
        slower_btn.clicked.connect(lambda: self.adjust_realtime_speed(-5))
        faster_btn = QPushButton("+")
        faster_btn.setObjectName("TinyButton")
        faster_btn.clicked.connect(lambda: self.adjust_realtime_speed(5))
        self.l2_target_forward_label = self._make_l1_metric_label("前后 --")
        self.l2_target_strafe_label = self._make_l1_metric_label("横移 --")
        self.l2_target_turn_label = self._make_l1_metric_label("转向 --")
        self.l2_remote_limit_label = self._make_l1_metric_label("上限 --")
        self.l2_current_strafe_label = self._make_l1_metric_label("横移 0.00 m/s")
        self.l2_current_turn_label = self._make_l1_metric_label("角速度 0.00 rad/s")
        self.l2_current_mode_label = self._make_l1_metric_label("来源 --")
        self.key_hint = QLabel("")
        for hidden_widget in (
            self.realtime_speed_value,
            slower_btn,
            self.realtime_speed_slider,
            faster_btn,
            self.l2_target_forward_label,
            self.l2_target_strafe_label,
            self.l2_target_turn_label,
            self.l2_remote_limit_label,
            self.l2_current_strafe_label,
            self.l2_current_turn_label,
            self.l2_current_mode_label,
            self.key_hint,
        ):
            hidden_layout.addWidget(hidden_widget)

        self.start_stream_btn = QPushButton("开始遥控")
        self.start_stream_btn.setObjectName("Primary")
        self.start_stream_btn.clicked.connect(self.toggle_gamepad_stream)
        self.start_stream_btn.setMinimumHeight(42)
        self.start_stream_btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        realtime_layout.addWidget(self.start_stream_btn, 1)
        return realtime_box

    def _build_unsupported_panel(self) -> None:
        unsupported_box = QFrame()
        self.unsupported_box = unsupported_box
        unsupported_box.setObjectName("Panel")
        unsupported_layout = QVBoxLayout(unsupported_box)
        unsupported_layout.setContentsMargins(18, 16, 18, 16)
        unsupported_layout.setSpacing(8)
        unsupported_title = QLabel("当前设备未开放遥控功能")
        unsupported_title.setObjectName("DiagSectionTitle")
        unsupported_hint = QLabel("请选择已适配遥控的设备后，此页面会显示速度参数、姿态控制和实时遥控。")
        unsupported_hint.setObjectName("Muted")
        unsupported_hint.setWordWrap(True)
        unsupported_layout.addWidget(unsupported_title)
        unsupported_layout.addWidget(unsupported_hint)
        self.body.addWidget(unsupported_box)
