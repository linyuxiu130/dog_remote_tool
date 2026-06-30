from __future__ import annotations

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QComboBox,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from dog_remote_tool.ui.pages.mapping.map_history import MapHistoryCard
from dog_remote_tool.ui.user_console import ActionCard, AlertBanner, ConsoleStatusCard, InfoMetric

from dog_remote_tool.modules import mapping


class MappingLayoutMixin:
    def _build_preview_box(self) -> QFrame:
        preview_box = QFrame()
        preview_box.setObjectName("AdvancedDetails")
        preview_box.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        outer_layout = QVBoxLayout(preview_box)
        outer_layout.setContentsMargins(0, 0, 0, 0)
        outer_layout.setSpacing(8)

        self.map_preview_content = QGroupBox("地图预览")
        preview_layout = QVBoxLayout(self.map_preview_content)
        preview_layout.setContentsMargins(16, 14, 16, 14)
        preview_layout.setSpacing(12)
        self.map_selector = QComboBox(self)
        self.map_selector.hide()
        self.map_selector.setMaxVisibleItems(12)
        self.map_selector.currentIndexChanged.connect(self.on_map_selection_changed)
        self.map_cards: dict[str, MapHistoryCard] = {}
        self.map_cards_empty = QLabel("暂无历史图")
        self.map_cards_empty.setAlignment(Qt.AlignCenter)
        self.map_cards_empty.setObjectName("Muted")
        self.map_cards_empty.setMinimumHeight(130)
        self.map_cards_panel = QWidget()
        self.map_cards_layout = QHBoxLayout(self.map_cards_panel)
        self.map_cards_layout.setContentsMargins(0, 0, 0, 0)
        self.map_cards_layout.setSpacing(10)
        preview_layout.addWidget(self.map_cards_empty)
        preview_layout.addWidget(self.map_cards_panel)
        self.map_cards_panel.hide()
        self.edit_map_pgm_button = QPushButton("编辑 map.pgm")
        self.edit_map_pgm_button.setToolTip("用圆形画笔编辑当前选中历史图，并保存回远端 map.pgm")
        self.edit_map_pgm_button.clicked.connect(self.open_map_pgm_editor)
        self.edit_map_pgm_button.setEnabled(False)
        delete_selected = QPushButton("删除选中图")
        delete_selected.setToolTip("删除卡片选中的远端地图目录")
        delete_selected.setObjectName("Danger")
        delete_selected.clicked.connect(self.make_delete_selected_map)
        self.selected_map_detail = QLabel("远端目录：--")
        self.selected_map_detail.setObjectName("Muted")
        self.selected_map_detail.setWordWrap(True)
        self.selected_map_detail.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.preview_status = QLabel("未加载")
        self.preview_status.setObjectName("Muted")
        self.preview_status.setWordWrap(True)
        preview_action_row = QHBoxLayout()
        preview_action_row.setSpacing(10)
        for button in (self.edit_map_pgm_button, delete_selected):
            button.setMinimumHeight(34)
            button.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        preview_action_row.addWidget(self.edit_map_pgm_button, 1)
        preview_action_row.addWidget(delete_selected, 1)
        preview_layout.addLayout(preview_action_row)
        preview_layout.addWidget(self.selected_map_detail)
        preview_layout.addWidget(self.preview_status)

        outer_layout.addWidget(self.map_preview_content)
        return preview_box

    def _build_config_box(self) -> QFrame:
        config_box = QFrame()
        config_box.setObjectName("Panel")
        self.sensor_type = QLineEdit(mapping.default_sensor_type(self.profile()))
        self.save_map_path = QLineEdit(mapping.default_save_map_path(self.profile()))
        self.calibration_file_path = QLineEdit(mapping.default_calibration_file_path(self.profile()))
        self.arc_calibration_file_path = QLineEdit(mapping.default_arc_calibration_file_path(self.profile()))
        for widget in (
            self.sensor_type,
            self.save_map_path,
            self.calibration_file_path,
            self.arc_calibration_file_path,
        ):
            widget.hide()
            widget.setParent(config_box)
        config_box.hide()
        config_box.setMaximumHeight(0)
        return config_box

    def _build_action_box(self) -> QFrame:
        action_box = QFrame()
        action_box.setObjectName("Panel")
        action_box.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        action_layout = QVBoxLayout(action_box)
        action_layout.setContentsMargins(14, 10, 14, 10)
        action_layout.setSpacing(10)

        self.mapping_alert = AlertBanner()
        action_layout.addWidget(self.mapping_alert)

        status_row = QHBoxLayout()
        status_row.setSpacing(10)
        self.mapping_state = ConsoleStatusCard("当前状态", "读取中", "正在读取远端建图状态。")
        self.mapping_operation = ConsoleStatusCard("操作", "空闲", "等待用户操作。")
        self.mapping_alg_state = ConsoleStatusCard("Alg 状态", "--", "")
        self.mapping_alg_state.badge.hide()
        for card in (self.mapping_state, self.mapping_operation, self.mapping_alg_state):
            card.setMinimumHeight(108)
            card.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            status_row.addWidget(card, 1)
        action_layout.addLayout(status_row)

        action_row = QHBoxLayout()
        action_row.setSpacing(10)
        self.start_mapping_btn = QPushButton("开始建图")
        self.start_mapping_btn.setObjectName("Primary")
        self.start_mapping_btn.setToolTip("远端未处于建图中时启动建图")
        self.start_mapping_btn.clicked.connect(self.make_start_mapping)
        self.finish_mapping_btn = QPushButton("结束保存")
        self.finish_mapping_btn.setObjectName("Primary")
        self.finish_mapping_btn.setFocusPolicy(Qt.NoFocus)
        self.finish_mapping_btn.setAutoDefault(False)
        self.finish_mapping_btn.setDefault(False)
        self.finish_mapping_btn.setToolTip("保存地图并刷新历史地图列表")
        self.finish_mapping_btn.clicked.connect(self.make_finish_mapping)
        self.cancel_mapping_btn = QPushButton("取消建图")
        self.cancel_mapping_btn.setObjectName("Danger")
        self.cancel_mapping_btn.setFocusPolicy(Qt.NoFocus)
        self.cancel_mapping_btn.setAutoDefault(False)
        self.cancel_mapping_btn.setDefault(False)
        self.cancel_mapping_btn.setToolTip("放弃当前建图结果")
        self.cancel_mapping_btn.clicked.connect(self.make_cancel_mapping)
        self.refresh_status_btn = QPushButton("刷新状态")
        self.refresh_status_btn.clicked.connect(self.refresh_mapping_page)
        buttons = (
            self.start_mapping_btn,
            self.finish_mapping_btn,
            self.cancel_mapping_btn,
            self.refresh_status_btn,
        )
        for button in buttons:
            button.setMinimumHeight(40)
            button.setMinimumWidth(120)
            button.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        action_row.addWidget(self.start_mapping_btn, 2)
        action_row.addWidget(self.finish_mapping_btn, 2)
        action_row.addWidget(self.cancel_mapping_btn, 2)
        action_row.addWidget(self.refresh_status_btn, 1)
        action_layout.addLayout(action_row)

        action_layout.addWidget(self._build_next_steps_box())

        self.mapping_result_panel = QFrame()
        result_layout = QGridLayout(self.mapping_result_panel)
        result_layout.setContentsMargins(0, 0, 0, 0)
        result_layout.setHorizontalSpacing(10)
        result_layout.setVerticalSpacing(10)
        self.map_count_metric = InfoMetric("历史地图", "--")
        self.latest_map_metric = InfoMetric("最新地图", "--")
        self.disk_metric = InfoMetric("存储空间", "--")
        self.map_save_metric = InfoMetric("保存状态", "读取中")
        result_layout.addWidget(self.map_save_metric, 0, 0)
        result_layout.addWidget(self.latest_map_metric, 0, 1)
        result_layout.addWidget(self.map_count_metric, 0, 2)
        result_layout.addWidget(self.disk_metric, 0, 3)
        for column in range(4):
            result_layout.setColumnStretch(column, 1)
        action_layout.addWidget(self.mapping_result_panel)

        return action_box

    def _build_next_steps_box(self) -> QGroupBox:
        self.next_steps_box = QGroupBox("建图完成后的下一步")
        next_steps_layout = QVBoxLayout(self.next_steps_box)
        next_steps_layout.setContentsMargins(12, 10, 12, 10)
        next_steps_layout.setSpacing(6)
        self.next_steps_hint = QLabel("地图已保存，可继续编辑路网或进入导航。")
        self.next_steps_hint.setObjectName("Muted")
        self.next_steps_hint.setWordWrap(True)
        self.next_steps_hint.hide()
        next_steps_layout.addWidget(self.next_steps_hint)
        next_steps_row = QHBoxLayout()
        next_steps_row.setSpacing(8)
        open_route = ActionCard("编辑路网", "为当前地图添加点位、路线和充电桩信息。", "编辑路网")
        open_route.clicked.connect(lambda: self.open_page_requested.emit("导航"))
        open_navigation = ActionCard("进入导航", "使用当前地图开始初始化定位和导航。", "进入导航", tone="primary")
        open_navigation.clicked.connect(lambda: self.open_page_requested.emit("导航"))
        next_steps_row.addWidget(open_route, 1)
        next_steps_row.addWidget(open_navigation, 1)
        next_steps_layout.addLayout(next_steps_row)
        self.next_steps_box.hide()
        return self.next_steps_box
