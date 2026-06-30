from __future__ import annotations

from PyQt5.QtWidgets import (
    QButtonGroup,
    QDoubleSpinBox,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QPushButton,
    QTabWidget,
    QTableWidget,
    QVBoxLayout,
    QWidget,
)

from dog_remote_tool.modules.navigation import route_network


class RouteEditorSidePanelMixin:
    def _make_manual_coordinate_box(self) -> QGroupBox:
        manual_box = QGroupBox("按坐标加点")
        manual_grid = QGridLayout(manual_box)
        manual_grid.setHorizontalSpacing(8)
        manual_grid.setVerticalSpacing(8)
        self.manual_route_x = QLineEdit()
        self.manual_route_x.setPlaceholderText("2.806028840")
        self.manual_route_x.setToolTip("输入地图坐标 x；也可在 X 输入框粘贴 'x y'")
        self.manual_route_y = QLineEdit()
        self.manual_route_y.setPlaceholderText("-7.476321017")
        self.manual_route_y.setToolTip("输入地图坐标 y")
        add_manual = QPushButton("新增并连接最近点")
        add_manual.setObjectName("Primary")
        add_manual.setToolTip("按输入坐标新增路网节点，并自动连接到最近的已有路网节点")
        add_manual.clicked.connect(self.add_manual_coordinate_node)
        manual_grid.addWidget(QLabel("X"), 0, 0)
        manual_grid.addWidget(self.manual_route_x, 0, 1)
        manual_grid.addWidget(QLabel("Y"), 1, 0)
        manual_grid.addWidget(self.manual_route_y, 1, 1)
        manual_grid.addWidget(add_manual, 2, 0, 1, 2)
        return manual_box

    def _make_side_panel(self) -> QWidget:
        panel = QFrame()
        panel.setObjectName("RouteEditorSidePanel")
        panel.setMinimumWidth(380)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)
        layout.addWidget(self._make_manual_coordinate_box())
        tabs = QTabWidget()
        tabs.setObjectName("RouteInspectorTabs")

        properties_tab = QWidget()
        properties_layout = QVBoxLayout(properties_tab)
        properties_layout.setContentsMargins(0, 0, 0, 0)
        properties_layout.setSpacing(10)
        property_box = QGroupBox("对象信息")
        grid = QGridLayout(property_box)
        grid.setHorizontalSpacing(8)
        grid.setVerticalSpacing(8)
        self.editor_object_label = QLabel("未选择")
        self.editor_object_label.setObjectName("RouteInspectorTitle")
        self.editor_object_id = QLineEdit()
        self.editor_object_id.setReadOnly(True)
        self.editor_node_x = QLineEdit()
        self.editor_node_x.editingFinished.connect(self.apply_editor_node_coordinates)
        self.editor_node_y = QLineEdit()
        self.editor_node_y.editingFinished.connect(self.apply_editor_node_coordinates)
        self.editor_edge_start = QLineEdit()
        self.editor_edge_start.setReadOnly(True)
        self.editor_edge_end = QLineEdit()
        self.editor_edge_end.setReadOnly(True)
        self.editor_passable_width = QDoubleSpinBox()
        self.editor_passable_width.setRange(route_network.MIN_ROUTE_PASSABLE_WIDTH, route_network.MAX_ROUTE_PASSABLE_WIDTH)
        self.editor_passable_width.setDecimals(2)
        self.editor_passable_width.setSingleStep(0.1)
        self.editor_passable_width.setSuffix(" m")
        self.editor_passable_width.setEnabled(False)
        self.editor_passable_width.setToolTip("写入 GeoJSON 边属性 passable_width；导航包用它决定路网可通行走廊宽度")
        self.editor_passable_width.valueChanged.connect(self.apply_editor_passable_width)
        self.editor_road_class_buttons = QWidget()
        road_class_layout = QHBoxLayout(self.editor_road_class_buttons)
        road_class_layout.setContentsMargins(0, 0, 0, 0)
        road_class_layout.setSpacing(6)
        self.editor_road_class_group = QButtonGroup(self)
        self.editor_road_class_group.setExclusive(True)
        self.editor_road_class_buttons_by_value = {}
        for value, label in route_network.ROUTE_ROAD_CLASS_MODE_OPTIONS:
            button = QPushButton(label)
            button.setCheckable(True)
            button.setMinimumHeight(30)
            button.setToolTip("road_class 0/1/2 使用对膝 WALK；road_class 3 会切换同膝 WALK")
            self.editor_road_class_group.addButton(button, value)
            self.editor_road_class_buttons_by_value[value] = button
            road_class_layout.addWidget(button)
            button.clicked.connect(lambda _checked=False, selected=value: self.apply_editor_road_class(selected))
        self.editor_road_class_buttons.setEnabled(False)
        self.editor_direction_buttons = QWidget()
        direction_layout = QHBoxLayout(self.editor_direction_buttons)
        direction_layout.setContentsMargins(0, 0, 0, 0)
        direction_layout.setSpacing(6)
        self.editor_direction_group = QButtonGroup(self)
        self.editor_direction_group.setExclusive(True)
        self.editor_direction_both = QPushButton("双向")
        self.editor_direction_forward = QPushButton("单向")
        for button, value, tooltip in (
            (self.editor_direction_both, route_network.ROUTE_DIRECTION_BOTH, "允许 startid 和 endid 两个方向通行"),
            (self.editor_direction_forward, route_network.ROUTE_DIRECTION_FORWARD, "只允许 startid 到 endid 方向通行"),
        ):
            button.setCheckable(True)
            button.setMinimumHeight(30)
            button.setToolTip(tooltip)
            self.editor_direction_group.addButton(button)
            self.editor_direction_group.setId(button, 0 if value == route_network.ROUTE_DIRECTION_BOTH else 1)
            direction_layout.addWidget(button)
        self.editor_direction_both.clicked.connect(lambda: self.apply_editor_direction(route_network.ROUTE_DIRECTION_BOTH))
        self.editor_direction_forward.clicked.connect(lambda: self.apply_editor_direction(route_network.ROUTE_DIRECTION_FORWARD))
        self.editor_metric = QLabel("--")
        self.editor_metric.setObjectName("Muted")
        delete = QPushButton("删除所选")
        delete.setObjectName("Danger")
        delete.clicked.connect(self.delete_selected)
        grid.addWidget(self.editor_object_label, 0, 0, 1, 2)
        grid.addWidget(QLabel("ID"), 1, 0)
        grid.addWidget(self.editor_object_id, 1, 1)
        grid.addWidget(QLabel("X"), 2, 0)
        grid.addWidget(self.editor_node_x, 2, 1)
        grid.addWidget(QLabel("Y"), 3, 0)
        grid.addWidget(self.editor_node_y, 3, 1)
        grid.addWidget(QLabel("起点"), 4, 0)
        grid.addWidget(self.editor_edge_start, 4, 1)
        grid.addWidget(QLabel("终点"), 5, 0)
        grid.addWidget(self.editor_edge_end, 5, 1)
        grid.addWidget(QLabel("路宽"), 6, 0)
        grid.addWidget(self.editor_passable_width, 6, 1)
        grid.addWidget(QLabel("运动模式"), 7, 0)
        grid.addWidget(self.editor_road_class_buttons, 7, 1)
        grid.addWidget(QLabel("方向"), 8, 0)
        grid.addWidget(self.editor_direction_buttons, 8, 1)
        grid.addWidget(self.editor_metric, 9, 0, 1, 2)
        grid.addWidget(delete, 10, 0, 1, 2)
        properties_layout.addWidget(property_box)
        properties_layout.addStretch(1)
        tabs.addTab(properties_tab, "属性")

        issue_tab = QWidget()
        issue_layout = QVBoxLayout(issue_tab)
        issue_layout.setContentsMargins(0, 0, 0, 0)
        self.editor_issue_summary = QLabel("尚未校验")
        self.editor_issue_summary.setObjectName("Muted")
        fix_crossings = QPushButton("自动补交点")
        fix_crossings.setToolTip("为相交但未共享节点的边新增交点，并把边拆成共享该节点的线段")
        fix_crossings.clicked.connect(self.auto_mark_crossing_points)
        fix_isolated = QPushButton("自动接孤立点")
        fix_isolated.setToolTip("为孤立节点新增一条到最近节点的连接边，不改动已有路径")
        fix_isolated.clicked.connect(self.auto_attach_isolated_nodes)
        self.editor_issue_list = QListWidget()
        self.editor_issue_list.itemClicked.connect(self.focus_issue)
        issue_layout.addWidget(self.editor_issue_summary)
        issue_layout.addWidget(fix_crossings)
        issue_layout.addWidget(fix_isolated)
        issue_layout.addWidget(self.editor_issue_list, 1)
        tabs.addTab(issue_tab, "校验")

        history_tab = QWidget()
        history_layout = QVBoxLayout(history_tab)
        history_layout.setContentsMargins(0, 0, 0, 0)
        history_layout.setSpacing(10)
        history_actions = QHBoxLayout()
        undo_button = QPushButton("撤销上一步")
        undo_button.setObjectName("Primary")
        undo_button.setToolTip("快捷键 Ctrl+Z")
        undo_button.clicked.connect(self.undo_history)
        revert_button = QPushButton("回退到选中")
        revert_button.clicked.connect(self.revert_selected_history)
        history_actions.addWidget(undo_button)
        history_actions.addWidget(revert_button)
        history_layout.addLayout(history_actions)
        self.history_table = QTableWidget(0, 4)
        self.history_table.setHorizontalHeaderLabels(["时间", "改动", "点", "边"])
        self.history_table.verticalHeader().setVisible(False)
        self.history_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.history_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.history_table.setAlternatingRowColors(True)
        self.history_table.cellClicked.connect(lambda row, _column: self.jump_to_history_row(row))
        history_layout.addWidget(self.history_table, 1)
        tabs.addTab(history_tab, "历史")

        self.editor_tabs = tabs
        self.editor_issue_tab = issue_tab
        layout.addWidget(tabs, 1)
        return panel
