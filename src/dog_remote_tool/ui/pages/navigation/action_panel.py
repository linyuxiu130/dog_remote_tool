from __future__ import annotations

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QFrame, QGridLayout, QGroupBox, QHBoxLayout, QLabel, QPushButton, QSizePolicy, QVBoxLayout, QWidget


class NavigationActionPanelMixin:
    def _navigation_action_section(self, title: str) -> tuple[QFrame, QVBoxLayout]:
        section = QFrame()
        section.setObjectName("NavActionSection")
        layout = QVBoxLayout(section)
        layout.setContentsMargins(10, 8, 10, 10)
        layout.setSpacing(6)
        label = QLabel(title)
        label.setObjectName("NavActionSectionTitle")
        layout.addWidget(label)
        return section, layout

    def _navigation_action_row(self, *buttons: QPushButton) -> QWidget:
        row = QWidget()
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)
        for button in buttons:
            button.setMinimumHeight(34)
            button.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            layout.addWidget(button, 1)
        return row

    def _add_navigation_action_panel(self, nav_layout) -> None:
        self.point_nav_button = QPushButton("点位导航")
        self.point_nav_button.setObjectName("SoftPrimary")
        self.point_nav_button.clicked.connect(self.make_start_point_navigation)
        self.loop_button = QPushButton("循环")
        self.loop_button.setCheckable(True)
        self.loop_button.setObjectName("LoopSwitchOff")
        self.loop_button.setToolTip("打开或关闭循环模式；开启后再点击点位/路网开始按钮才会按循环方式下发")
        self.loop_button.clicked.connect(self.toggle_navigation_loop)
        self.route_mode_button = QPushButton("进入路网导航")
        self.route_mode_button.setObjectName("SoftPrimary")
        self.route_mode_button.clicked.connect(self.toggle_route_target_mode)
        self.route_goal_button = QPushButton("开始路网导航")
        self.route_goal_button.setObjectName("SoftPrimary")
        self.route_goal_button.clicked.connect(self.make_start_route_goal)
        self.choose_route_file_button = QPushButton("编辑路网")
        self.choose_route_file_button.setToolTip("基于当前历史图打开路网编辑器；保存后默认同步到机器人当前历史图目录")
        self.choose_route_file_button.clicked.connect(self.open_local_route_editor)
        self.upload_route_file_button = QPushButton("上传路网")
        self.upload_route_file_button.setToolTip("选择本地 GeoJSON 并上传到机器人当前历史图目录")
        self.upload_route_file_button.clicked.connect(lambda _checked=False: self.upload_selected_route_geojson())
        self.export_route_file_button = QPushButton("导出路网")
        self.export_route_file_button.setToolTip("把当前历史图对应的本地 map.geojson 另存到指定位置")
        self.export_route_file_button.clicked.connect(self.export_selected_route_geojson)
        self.relocalize_button = QPushButton("重新定位")
        self.relocalize_button.setObjectName("SoftPrimary")
        self.relocalize_button.setToolTip("重新加载当前地图定位")
        self.relocalize_button.clicked.connect(self.make_relocalize_selected_map)
        self.arc_calibration_button = QPushButton("标定充电桩")
        self.arc_calibration_button.setObjectName("SoftPrimary")
        self.arc_calibration_button.clicked.connect(self.make_start_arc_calibration)
        self.arc_mark_button = QPushButton("标记充电桩")
        self.arc_mark_button.setObjectName("SoftPrimary")
        self.arc_mark_button.clicked.connect(self.make_mark_charging_dock)
        self.mapped_recharge_button = QPushButton("有图进桩")
        self.mapped_recharge_button.setObjectName("Primary")
        self.mapped_recharge_button.clicked.connect(self.make_mapped_recharge_action)
        self.stop_button = QPushButton("停止")
        self.stop_button.setObjectName("Danger")
        self.stop_button.clicked.connect(self.make_stop_navigation)
        self.pause_resume_button = QPushButton("暂停")
        self.pause_resume_button.setObjectName("SoftPrimary")
        self.pause_resume_button.setToolTip("暂停当前导航任务；暂停后再次点击继续")
        self.pause_resume_button.clicked.connect(self.make_toggle_navigation_pause)
        self.obstacle_overlay_button = QPushButton("障碍 ON")
        self.obstacle_overlay_button.setCheckable(True)
        self.obstacle_overlay_button.setChecked(True)
        self.obstacle_overlay_button.setObjectName("SoftPrimary")
        self.obstacle_overlay_button.setToolTip("显示或隐藏实时障碍点云；关闭后停止轻量转发通道")
        self.obstacle_overlay_button.clicked.connect(self.toggle_obstacle_overlay)
        all_buttons = (
            self.point_nav_button,
            self.loop_button,
            self.route_mode_button,
            self.route_goal_button,
            self.choose_route_file_button,
            self.upload_route_file_button,
            self.export_route_file_button,
            self.relocalize_button,
            self.arc_calibration_button,
            self.arc_mark_button,
            self.mapped_recharge_button,
            self.pause_resume_button,
            self.obstacle_overlay_button,
            self.stop_button,
        )
        for button in all_buttons:
            button.setMinimumHeight(34)
            button.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        mission_section, mission_layout = self._navigation_action_section("主要导航")
        mission_layout.addWidget(
            self._navigation_action_row(
                self.point_nav_button,
                self.route_mode_button,
                self.route_goal_button,
            )
        )
        nav_layout.addWidget(mission_section)

        control_section, control_layout = self._navigation_action_section("运行控制")
        control_layout.addWidget(
            self._navigation_action_row(
                self.loop_button,
                self.pause_resume_button,
                self.obstacle_overlay_button,
                self.stop_button,
                self.mapped_recharge_button,
            )
        )
        nav_layout.addWidget(control_section)

        tools_box = QFrame()
        tools_box.setObjectName("AdvancedDetails")
        tools_layout = QVBoxLayout(tools_box)
        tools_layout.setContentsMargins(0, 0, 0, 0)
        tools_layout.setSpacing(8)
        self.navigation_tools_toggle = QPushButton("更多工具")
        self.navigation_tools_toggle.setObjectName("AdvancedDetailsToggle")
        self.navigation_tools_toggle.setCheckable(True)
        tools_content = QWidget()
        tools_grid = QGridLayout(tools_content)
        tools_grid.setContentsMargins(0, 0, 0, 0)
        tools_grid.setHorizontalSpacing(10)
        tools_grid.setVerticalSpacing(8)
        tool_buttons = (
            self.relocalize_button,
            self.choose_route_file_button,
            self.upload_route_file_button,
            self.export_route_file_button,
            self.arc_calibration_button,
            self.arc_mark_button,
        )
        for index, button in enumerate(tool_buttons):
            tools_grid.addWidget(button, index // 3, index % 3)
        for column in range(3):
            tools_grid.setColumnStretch(column, 1)
        tools_content.hide()
        tools_layout.addWidget(self.navigation_tools_toggle)
        tools_layout.addWidget(tools_content)
        self.navigation_tools_toggle.toggled.connect(tools_content.setVisible)
        self.navigation_tools_toggle.toggled.connect(
            lambda checked: self.navigation_tools_toggle.setText("收起更多工具" if checked else "更多工具")
        )
        nav_layout.addWidget(tools_box)

        self.nav_action_status = QLabel("导航状态确认中")
        self.nav_action_status.setObjectName("Muted")
        self.nav_action_status.setWordWrap(True)
        self.nav_action_status.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.nav_action_status.setStyleSheet(
            "background:#ffffff;color:#334155;border:1px solid #e3eaf3;border-radius:8px;padding:8px 10px;"
        )
        nav_layout.addWidget(self.nav_action_status)
