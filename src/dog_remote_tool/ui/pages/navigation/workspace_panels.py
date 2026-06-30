from __future__ import annotations

import math
from typing import TYPE_CHECKING

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QAbstractItemView,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
)

from dog_remote_tool.ui.pages.navigation.workspace_table import WaypointTableWidget
from dog_remote_tool.ui.widget_roles import widget_text, widget_tooltip

if TYPE_CHECKING:
    from dog_remote_tool.ui.pages.navigation.page import NavigationPage


class WorkspaceStatusCard(QFrame):
    TONE_STYLES = {
        "running": ("#eef6ff", "#b9d7f4"),
        "success": ("#effaf3", "#bfebcf"),
        "warning": ("#fff8ed", "#f3d6ad"),
        "danger": ("#fff1f2", "#efc0c6"),
        "neutral": ("#ffffff", "#dfe8f3"),
    }

    def __init__(self, text: str = "") -> None:
        super().__init__()
        self._text = ""
        self.setObjectName("WorkspaceStatusCard")
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setMinimumHeight(72)
        self.setMaximumHeight(104)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(2)
        self.eyebrow = QLabel()
        self.eyebrow.setObjectName("WorkspaceStatusEyebrow")
        self.eyebrow.setStyleSheet("color:#64748b;font-size:8pt;font-weight:700;")
        self.title = QLabel()
        self.title.setObjectName("WorkspaceStatusTitle")
        self.title.setWordWrap(False)
        self.title.setStyleSheet("color:#10233f;font-size:11pt;font-weight:800;")
        self.detail = QLabel()
        self.detail.setObjectName("WorkspaceStatusDetail")
        self.detail.setWordWrap(True)
        self.detail.setStyleSheet("color:#52677e;font-size:8pt;font-weight:500;")
        layout.addWidget(self.eyebrow)
        layout.addWidget(self.title)
        layout.addWidget(self.detail)
        self.set_status_text(text)
        self.set_tone("neutral")

    def set_status_text(self, text: str) -> bool:
        changed = self._text != text
        self._text = text
        lines = [line.strip() for line in str(text).splitlines() if line.strip()]
        self.eyebrow.setText(lines[0] if lines else "--")
        self.title.setText(lines[1] if len(lines) > 1 else "--")
        detail = " ".join(lines[2:])
        self.detail.setText(detail)
        self.detail.setVisible(bool(detail))
        return changed

    def text(self) -> str:
        return self._text

    def set_tone(self, tone: str) -> None:
        bg, border = self.TONE_STYLES.get(tone, self.TONE_STYLES["neutral"])
        self.setStyleSheet(f"QFrame#WorkspaceStatusCard{{background:{bg};border:1px solid {border};border-radius:8px;}}")


class NavigationWorkspacePanelsMixin:
    def _build_workspace_side_panel(self, page: "NavigationPage") -> QFrame:
        side_panel = QFrame()
        side_panel.setObjectName("NavigationWorkspaceSide")
        side_panel.setMinimumWidth(660)
        side_panel.setMaximumWidth(780)
        side_panel.setStyleSheet(
            "QFrame#NavigationWorkspaceSide{background:#f8fbff;border:1px solid #dbe6f2;border-radius:8px;}"
            "QLabel#SideSectionTitle{color:#123b63;font-weight:800;font-size:12pt;}"
            "QLabel#TargetSummary{background:#ffffff;border:1px solid #dbe6f2;border-radius:7px;padding:8px 12px;color:#334155;}"
            "QLabel#RobotSummary{background:#fff7ed;border:1px solid #fed7aa;border-radius:7px;padding:8px 12px;color:#9a3412;font-weight:700;}"
            "QListWidget#WaypointList{background:#ffffff;border:1px solid #dbe6f2;border-radius:7px;color:#24384f;}"
            "QTableWidget#WaypointTable{background:#ffffff;border:1px solid #dbe6f2;border-radius:7px;color:#24384f;gridline-color:#eef2f7;selection-background-color:#dbeafe;}"
            "QFrame#WaypointCell{background:transparent;border:0;}"
            "QFrame#WaypointCell[selected='true']{background:#dbeafe;border-radius:5px;}"
            "QLabel#WaypointIndex{color:#64748b;font-size:8pt;font-weight:700;}"
            "QLabel#WaypointValue{color:#1f3349;font-size:9pt;font-weight:500;}"
            "QPlainTextEdit#WorkspaceLog{background:#ffffff;color:#24384f;border:1px solid #dbe6f2;border-radius:8px;padding:8px;}"
        )
        side_layout = QVBoxLayout(side_panel)
        side_layout.setContentsMargins(10, 10, 10, 10)
        side_layout.setSpacing(10)
        side_layout.addLayout(self._build_workspace_status_grid(page))
        side_layout.addWidget(self._build_workspace_target_panel(page))
        side_layout.addSpacing(6)
        self._add_workspace_action_panel(side_layout, page)
        return side_panel

    def _build_workspace_status_grid(self, page: "NavigationPage") -> QGridLayout:
        status_grid = QGridLayout()
        status_grid.setHorizontalSpacing(8)
        status_grid.setVerticalSpacing(8)
        status_grid.setColumnStretch(0, 1)
        status_grid.setColumnStretch(1, 1)
        self.status_cards: list[QLabel] = []
        for index, source in enumerate(
            (
                page.nav_current_state,
                page.map_state,
                page.localization_state,
                page.navigation_state,
            )
        ):
            card = self._workspace_status_card(source)
            self.status_cards.append(card)
            if index == 0:
                status_grid.addWidget(card, 0, 0, 1, 2)
            else:
                status_grid.addWidget(card, 1 + (index - 1) // 2, (index - 1) % 2)
        return status_grid

    def _build_workspace_target_panel(self, page: "NavigationPage") -> QFrame:
        target_panel = QFrame()
        target_panel.setObjectName("NavigationTargetPanel")
        target_panel.setMinimumHeight(350)
        target_layout = QVBoxLayout(target_panel)
        target_layout.setContentsMargins(10, 8, 10, 8)
        target_layout.setSpacing(8)
        target_title = QLabel("目标")
        target_title.setObjectName("SideSectionTitle")
        target_layout.addWidget(target_title)

        mode_row = QHBoxLayout()
        mode_row.setSpacing(8)
        self.delete_selected_point = QPushButton("删除选中")
        self.delete_selected_point.setMinimumHeight(36)
        self.delete_selected_point.setToolTip("删除列表中选中的目标点")
        self.delete_selected_point.clicked.connect(lambda: page.delete_navigation_point(self.selected_point_index()))
        save_route = QPushButton("保存路线")
        save_route.setMinimumHeight(36)
        save_route.setToolTip("将当前路网目标节点顺序保存到本地")
        save_route.clicked.connect(lambda _checked=False: page.save_current_route_history())
        load_route = QPushButton("加载路线")
        load_route.setMinimumHeight(36)
        load_route.setToolTip("从本地历史路线恢复当前地图的路网目标节点")
        load_route.clicked.connect(lambda _checked=False: page.choose_route_history())
        clear_points = QPushButton("清空")
        clear_points.setMinimumHeight(36)
        clear_points.setToolTip("清空当前目标点")
        clear_points.clicked.connect(page.clear_navigation_points)
        add_hint = QLabel("点击地图添加目标点")
        add_hint.setObjectName("Muted")
        add_hint.setWordWrap(True)
        mode_row.addWidget(add_hint, 1)
        mode_row.addWidget(save_route)
        mode_row.addWidget(load_route)
        mode_row.addWidget(self.delete_selected_point)
        mode_row.addWidget(clear_points)
        target_layout.addLayout(mode_row)

        self.point_table_columns = 3
        self.point_table = WaypointTableWidget(0, self.point_table_columns)
        self.point_table.setObjectName("WaypointTable")
        self.point_table.setFixedHeight(192)
        self.point_table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.point_table.setSelectionBehavior(QAbstractItemView.SelectItems)
        self.point_table.setAlternatingRowColors(False)
        self.point_table.verticalHeader().hide()
        self.point_table.horizontalHeader().hide()
        self.point_table.setShowGrid(False)
        self.point_table.setWordWrap(False)
        self.point_table.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.point_table.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.point_table.currentCellChanged.connect(
            lambda row, column, _prev_row, _prev_column: self.on_point_table_selection_changed(row, column)
        )
        self.point_table.point_moved.connect(page.reorder_navigation_point)
        target_layout.addWidget(self.point_table)

        self.point_summary = QLabel(page.target_summary_text())
        self.point_summary.setObjectName("TargetSummary")
        self.point_summary.setWordWrap(True)
        self.robot_summary = QLabel(page.robot_pose_summary_text())
        self.robot_summary.setObjectName("RobotSummary")
        self.robot_summary.setWordWrap(True)
        target_layout.addWidget(self.point_summary)
        target_layout.addWidget(self.robot_summary)
        return target_panel

    def _add_workspace_action_panel(self, side_layout: QVBoxLayout, page: "NavigationPage") -> None:
        action_title = QLabel("导航操作")
        action_title.setObjectName("SideSectionTitle")
        side_layout.addWidget(action_title)
        action_grid = QGridLayout()
        action_grid.setHorizontalSpacing(8)
        action_grid.setVerticalSpacing(8)
        action_grid.setColumnStretch(0, 1)
        action_grid.setColumnStretch(1, 1)
        action_grid.setColumnStretch(2, 1)

        self.point_nav_button = QPushButton("点位导航")
        self.point_nav_button.setObjectName("SoftPrimary")
        self.point_nav_button.clicked.connect(page.make_start_point_navigation)
        self.loop_button = QPushButton("循环")
        self.loop_button.setCheckable(True)
        self.loop_button.setObjectName("LoopSwitchOff")
        self.loop_button.setToolTip("打开或关闭循环模式；开启后再点击点位/路网开始按钮才会按循环方式下发")
        self.loop_button.clicked.connect(page.toggle_navigation_loop)
        self.relocalize_button = QPushButton("重新定位")
        self.relocalize_button.setObjectName("SoftPrimary")
        self.relocalize_button.setToolTip("重新加载当前地图定位")
        self.relocalize_button.clicked.connect(page.make_relocalize_selected_map)
        self.route_mode_button = QPushButton("进入路网导航")
        self.route_mode_button.setObjectName("SoftPrimary")
        self.route_mode_button.clicked.connect(page.toggle_route_target_mode)
        self.route_goal_button = QPushButton("开始路网导航")
        self.route_goal_button.setObjectName("SoftPrimary")
        self.route_goal_button.clicked.connect(page.make_start_route_goal)
        self.route_button = QPushButton(page.route_action_label())
        self.route_button.setObjectName("SoftPrimary")
        self.route_button.clicked.connect(page.open_route_editor_for_selected_map)
        self.mapped_recharge_button = QPushButton("有图进桩")
        self.mapped_recharge_button.setObjectName("Primary")
        self.mapped_recharge_button.clicked.connect(page.make_mapped_recharge_action)
        self.arc_calibration_button = QPushButton("标定充电桩")
        self.arc_calibration_button.setObjectName("SoftPrimary")
        self.arc_calibration_button.setToolTip("发送 ARC 充电桩标定请求；这不是地图桩位标记")
        self.arc_calibration_button.clicked.connect(page.make_start_arc_calibration)
        self.arc_mark_button = QPushButton("标记充电桩")
        self.arc_mark_button.setObjectName("SoftPrimary")
        self.arc_mark_button.setToolTip("将当前识别到的充电桩位置写入所选地图；这不是 ARC 标定")
        self.arc_mark_button.clicked.connect(page.make_mark_charging_dock)
        self.stop_button = QPushButton("停止")
        self.stop_button.setObjectName("Danger")
        self.stop_button.clicked.connect(page.make_stop_navigation)
        self.pause_resume_button = QPushButton("暂停")
        self.pause_resume_button.setObjectName("SoftPrimary")
        self.pause_resume_button.clicked.connect(page.make_toggle_navigation_pause)

        route_action_buttons = (
            self.point_nav_button,
            self.loop_button,
            self.relocalize_button,
            self.route_mode_button,
            self.route_goal_button,
            self.route_button,
            self.arc_calibration_button,
            self.arc_mark_button,
            self.mapped_recharge_button,
            self.pause_resume_button,
        )
        action_columns = 3
        for index, button in enumerate(route_action_buttons):
            button.setMinimumHeight(38)
            button.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            action_grid.addWidget(button, index // action_columns, index % action_columns)
        self.stop_button.setMinimumHeight(38)
        self.stop_button.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        action_grid.addWidget(self.stop_button, math.ceil(len(route_action_buttons) / action_columns), 0, 1, action_columns)
        side_layout.addLayout(action_grid)

        self.action_status_label = QLabel("导航状态确认中")
        self.action_status_label.setObjectName("ActionStatus")
        self.action_status_label.setWordWrap(True)
        self.action_status_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.action_status_label.hide()

        self.status_label = QLabel(page.nav_status_note.text())
        self.status_label.setObjectName("Muted")
        self.status_label.setWordWrap(True)
        self.status_label.setVisible(self.status_label.text() not in {"", "等待状态刷新"})
        side_layout.addWidget(self.status_label)

    def _build_workspace_log_panel(self, page: "NavigationPage") -> QFrame:
        log_panel = QFrame()
        log_panel.setObjectName("NavigationWorkspaceLogPanel")
        log_panel.setStyleSheet(
            "QFrame#NavigationWorkspaceLogPanel{background:#f8fbff;border:1px solid #dbe6f2;border-radius:8px;}"
            "QPlainTextEdit#WorkspaceLog{background:#ffffff;color:#24384f;border:1px solid #dbe6f2;border-radius:8px;padding:8px;}"
            "QLabel#SideSectionTitle{color:#123b63;font-weight:800;font-size:12pt;}"
        )
        log_layout = QVBoxLayout(log_panel)
        log_layout.setContentsMargins(10, 8, 10, 10)
        log_layout.setSpacing(6)
        log_title = QLabel("任务日志")
        log_title.setObjectName("SideSectionTitle")
        log_layout.addWidget(log_title)
        self.log_view = QPlainTextEdit()
        self.log_view.setObjectName("WorkspaceLog")
        self.log_view.setReadOnly(True)
        self.log_view.setLineWrapMode(QPlainTextEdit.WidgetWidth)
        self.log_view.setMaximumBlockCount(180)
        self.log_view.setMinimumHeight(126)
        self.log_view.setPlainText(page.navigation_log_text())
        log_layout.addWidget(self.log_view, 1)
        return log_panel

    def _sync_workspace_status_card(self, label, source: QLabel) -> bool:
        tone_getter = getattr(source, "property", None)
        tone = str(tone_getter("tone") if callable(tone_getter) else "neutral")
        if isinstance(label, WorkspaceStatusCard):
            changed = label.set_status_text(widget_text(source))
            label.set_tone(tone)
        else:
            changed = False
        label.setToolTip(widget_tooltip(source))
        return changed

    def _workspace_status_card(self, source: QLabel):
        label = WorkspaceStatusCard(widget_text(source))
        self._sync_workspace_status_card(label, source)
        return label
