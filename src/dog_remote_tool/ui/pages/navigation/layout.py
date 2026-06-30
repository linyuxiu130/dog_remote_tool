from __future__ import annotations

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QFrame, QGroupBox, QHBoxLayout, QLabel, QPushButton, QSizePolicy, QVBoxLayout, QWidget

from dog_remote_tool.ui.pages.navigation.action_panel import NavigationActionPanelMixin
from dog_remote_tool.ui.user_console import AdvancedDetails


class NavigationDetailLabel(QLabel):
    def __init__(self, text: str = "") -> None:
        super().__init__(text)
        self.detail_widget: AdvancedDetails | None = None
        self._detail_tooltip = ""

    def setText(self, text: str) -> None:
        super().setText(text)
        self._sync_details()

    def setToolTip(self, text: str) -> None:
        self._detail_tooltip = text
        super().setToolTip(text)
        self._sync_details()

    def _sync_details(self) -> None:
        if self.detail_widget is None:
            return
        text = self.text() or "导航状态：等待刷新"
        if self._detail_tooltip and self._detail_tooltip != text:
            text = f"{text}\n{self._detail_tooltip}"
        self.detail_widget.set_details(text)


class NavigationLayoutMixin(NavigationActionPanelMixin):
    def _build_navigation_box(self) -> QGroupBox:
        nav_box = QGroupBox("导航")
        self.nav_box = nav_box
        nav_layout = QVBoxLayout(nav_box)
        nav_layout.setContentsMargins(16, 14, 16, 14)
        nav_layout.setSpacing(12)

        selector_row = QHBoxLayout()
        selector_row.setSpacing(10)
        map_label = QLabel("历史图")
        map_label.setObjectName("FieldLabel")
        refresh_maps = QPushButton("刷新地图")
        refresh_maps.setToolTip("重新读取远端历史图")
        refresh_maps.clicked.connect(self.refresh_map_list)
        fullscreen_map = QPushButton("全屏地图")
        fullscreen_map.setObjectName("SoftPrimary")
        fullscreen_map.clicked.connect(self.open_navigation_map_preview)
        selector_row.addWidget(map_label)
        selector_row.addWidget(self.map_selector, 1)
        selector_row.addWidget(refresh_maps)
        selector_row.addWidget(fullscreen_map)
        nav_layout.addLayout(selector_row)
        nav_layout.addWidget(self.selected_map_detail)

        self.nav_current_state = self._status_card("当前状态\n等待刷新")
        self.nav_current_state.setMinimumHeight(74)
        self._set_card_style(self.nav_current_state, "cancelled")
        nav_layout.addWidget(self.nav_current_state)

        self._add_navigation_action_panel(nav_layout)

        status_detail_box = QFrame()
        status_detail_box.setObjectName("AdvancedDetails")
        status_detail_layout = QVBoxLayout(status_detail_box)
        status_detail_layout.setContentsMargins(0, 0, 0, 0)
        status_detail_layout.setSpacing(8)
        self.navigation_status_toggle = QPushButton("状态详情")
        self.navigation_status_toggle.setObjectName("AdvancedDetailsToggle")
        self.navigation_status_toggle.setCheckable(True)
        status_detail_content = QWidget()
        status_row = QHBoxLayout(status_detail_content)
        status_row.setContentsMargins(0, 0, 0, 0)
        status_row.setSpacing(10)
        self.map_state = self._status_card("地图\n读取中")
        self.localization_state = self._status_card("定位\n读取中")
        self.perception_state = self._status_card("授权/标定\n读取中")
        self.perception_state.hide()
        self.navigation_state = self._status_card("导航栈\n读取中")
        self.task_state = self._status_card("任务\n读取中")
        self.task_state.hide()
        for card in (self.map_state, self.localization_state, self.navigation_state):
            card.setMinimumHeight(56)
            status_row.addWidget(card, 1)
        status_detail_content.hide()
        self.navigation_status_toggle.toggled.connect(status_detail_content.setVisible)
        self.navigation_status_toggle.toggled.connect(
            lambda checked: self.navigation_status_toggle.setText("收起状态详情" if checked else "状态详情")
        )
        status_detail_layout.addWidget(self.navigation_status_toggle)
        status_detail_layout.addWidget(status_detail_content)
        nav_layout.addWidget(status_detail_box)

        target_row = QHBoxLayout()
        target_row.setSpacing(8)
        clear_points = QPushButton("清空点位")
        clear_points.clicked.connect(self.clear_navigation_points)
        clear_points.setToolTip("清空当前目标点列表")
        target_hint = QLabel("点击地图添加目标点；1 个点按点位导航，多个点按多点导航")
        target_hint.setObjectName("Muted")
        target_hint.setWordWrap(True)
        target_row.addWidget(target_hint, 1)
        target_row.addWidget(clear_points)
        nav_layout.addLayout(target_row)

        point_manager = QFrame()
        point_manager.setObjectName("PointManager")
        point_manager.setStyleSheet(
            "QFrame#PointManager{background:#ffffff;border:1px solid #e3eaf3;border-radius:8px;}"
            "QListWidget#WaypointList{background:#ffffff;border:0;color:#24384f;}"
        )
        point_layout = QVBoxLayout(point_manager)
        point_layout.setContentsMargins(10, 8, 10, 10)
        point_layout.setSpacing(8)
        point_header = QHBoxLayout()
        point_title = QLabel("点位管理")
        point_title.setObjectName("FieldLabel")
        point_header.addWidget(point_title)
        point_header.addStretch(1)
        point_header.addWidget(self.delete_waypoint_button)
        point_layout.addLayout(point_header)
        point_layout.addWidget(self.waypoints_list)
        nav_layout.addWidget(point_manager)

        visual_row = QWidget()
        visual_layout = QHBoxLayout(visual_row)
        visual_layout.setContentsMargins(0, 0, 0, 0)
        visual_layout.setSpacing(10)
        self.nav_map.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.nav_camera_panel = self._build_navigation_camera_panel()
        visual_layout.addWidget(self.nav_map, 1)
        visual_layout.addWidget(self.nav_camera_panel, 0)
        nav_layout.addWidget(visual_row, 1)

        self.nav_code_detail = NavigationDetailLabel("导航状态：等待刷新")
        self.nav_code_detail.setObjectName("Muted")
        self.nav_code_detail.setWordWrap(True)
        self.nav_code_detail.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.nav_code_detail.setAlignment(Qt.AlignVCenter | Qt.AlignLeft)
        self.nav_code_detail.setMinimumHeight(40)
        self.nav_code_detail.setStyleSheet(
            "background:#ffffff;color:#334155;border:1px solid #e3eaf3;border-radius:8px;padding:8px 10px;line-height:130%;"
        )
        self.nav_code_detail.hide()
        self.navigation_detail = AdvancedDetails("详细信息")
        self.nav_code_detail.detail_widget = self.navigation_detail
        self.navigation_detail.set_details("导航状态：等待刷新")
        nav_layout.addWidget(self.navigation_detail)

        self.nav_status_note = QLabel("等待状态刷新")
        self.nav_status_note.setObjectName("Muted")
        self.nav_status_note.setWordWrap(True)
        nav_layout.addWidget(self.nav_status_note)
        return nav_box
