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
    QSizePolicy,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from dog_remote_tool.modules.navigation import route_network


class RouteNetworkInspectorPanelMixin:
    def _make_right_panel(self) -> QWidget:
        panel = QFrame(self)
        panel.setObjectName("RouteInspector")
        panel.setMinimumWidth(260)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)
        tabs = QTabWidget()
        tabs.setObjectName("RouteInspectorTabs")

        properties_tab = QWidget()
        properties_layout = QVBoxLayout(properties_tab)
        properties_layout.setContentsMargins(0, 0, 0, 0)
        properties_layout.setSpacing(10)
        properties = QGroupBox("对象属性")
        prop_grid = QGridLayout(properties)
        prop_grid.setHorizontalSpacing(8)
        prop_grid.setVerticalSpacing(8)
        self.object_label = QLabel("未选择")
        self.object_label.setObjectName("RouteInspectorTitle")
        self.object_id = QLineEdit()
        self.object_id.setReadOnly(True)
        self.object_start = QLineEdit()
        self.object_start.setReadOnly(True)
        self.object_end = QLineEdit()
        self.object_end.setReadOnly(True)
        self.object_passable_width = QDoubleSpinBox()
        self.object_passable_width.setRange(route_network.MIN_ROUTE_PASSABLE_WIDTH, route_network.MAX_ROUTE_PASSABLE_WIDTH)
        self.object_passable_width.setDecimals(2)
        self.object_passable_width.setSingleStep(0.1)
        self.object_passable_width.setSuffix(" m")
        self.object_passable_width.setEnabled(False)
        self.object_passable_width.setToolTip("写入 GeoJSON 边属性 passable_width；导航包用它决定路网可通行走廊宽度")
        self.object_passable_width.valueChanged.connect(self.apply_passable_width)
        self.object_road_class_buttons = QWidget()
        road_class_layout = QHBoxLayout(self.object_road_class_buttons)
        road_class_layout.setContentsMargins(0, 0, 0, 0)
        road_class_layout.setSpacing(6)
        self.object_road_class_group = QButtonGroup(self)
        self.object_road_class_group.setExclusive(True)
        self.object_road_class_buttons_by_value = {}
        for value, label in route_network.ROUTE_ROAD_CLASS_MODE_OPTIONS:
            button = QPushButton(label)
            button.setCheckable(True)
            button.setMinimumHeight(30)
            button.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            button.setToolTip("road_class 0/1/2 使用对膝 WALK；road_class 3 会切换同膝 WALK")
            self.object_road_class_group.addButton(button, value)
            self.object_road_class_buttons_by_value[value] = button
            road_class_layout.addWidget(button)
            button.clicked.connect(lambda _checked=False, selected=value: self.apply_road_class(selected))
        self.object_road_class_buttons.setEnabled(False)
        self.object_direction_buttons = QWidget()
        direction_layout = QHBoxLayout(self.object_direction_buttons)
        direction_layout.setContentsMargins(0, 0, 0, 0)
        direction_layout.setSpacing(6)
        self.object_direction_group = QButtonGroup(self)
        self.object_direction_group.setExclusive(True)
        self.object_direction_both = QPushButton("双向")
        self.object_direction_forward = QPushButton("单向")
        for button, value, tooltip in (
            (self.object_direction_both, route_network.ROUTE_DIRECTION_BOTH, "允许 startid 和 endid 两个方向通行"),
            (self.object_direction_forward, route_network.ROUTE_DIRECTION_FORWARD, "只允许 startid 到 endid 方向通行"),
        ):
            button.setCheckable(True)
            button.setMinimumHeight(30)
            button.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            button.setToolTip(tooltip)
            self.object_direction_group.addButton(button)
            self.object_direction_group.setId(button, 0 if value == route_network.ROUTE_DIRECTION_BOTH else 1)
            direction_layout.addWidget(button)
        self.object_direction_both.clicked.connect(lambda: self.apply_direction(route_network.ROUTE_DIRECTION_BOTH))
        self.object_direction_forward.clicked.connect(lambda: self.apply_direction(route_network.ROUTE_DIRECTION_FORWARD))
        self.object_metric = QLabel("--")
        self.object_metric.setObjectName("Muted")
        prop_grid.addWidget(self.object_label, 0, 0, 1, 2)
        prop_grid.addWidget(QLabel("ID"), 1, 0)
        prop_grid.addWidget(self.object_id, 1, 1)
        prop_grid.addWidget(QLabel("起点"), 2, 0)
        prop_grid.addWidget(self.object_start, 2, 1)
        prop_grid.addWidget(QLabel("终点"), 3, 0)
        prop_grid.addWidget(self.object_end, 3, 1)
        prop_grid.addWidget(QLabel("路宽"), 4, 0)
        prop_grid.addWidget(self.object_passable_width, 4, 1)
        prop_grid.addWidget(QLabel("运动模式"), 5, 0)
        prop_grid.addWidget(self.object_road_class_buttons, 5, 1)
        prop_grid.addWidget(QLabel("方向"), 6, 0)
        prop_grid.addWidget(self.object_direction_buttons, 6, 1)
        prop_grid.addWidget(self.object_metric, 7, 0, 1, 2)
        properties_layout.addWidget(properties)

        field_ops = QGroupBox("现场联动")
        ops_layout = QHBoxLayout(field_ops)
        emergency_stop = QPushButton("急停")
        emergency_stop.setObjectName("Danger")
        emergency_stop.setMinimumHeight(38)
        emergency_stop.clicked.connect(self.emergency_stop)
        ops_layout.addWidget(emergency_stop, 1)
        properties_layout.addWidget(field_ops)
        properties_layout.addStretch(1)
        tabs.addTab(properties_tab, "属性")

        preview_tab = QWidget()
        preview_tab_layout = QVBoxLayout(preview_tab)
        preview_tab_layout.setContentsMargins(0, 0, 0, 0)
        preview_tab_layout.setSpacing(10)
        preview = QGroupBox("路径预览")
        preview_grid = QGridLayout(preview)
        self.start_node = QLineEdit()
        self.start_node.setPlaceholderText("起点节点 ID")
        self.goal_node = QLineEdit()
        self.goal_node.setPlaceholderText("终点节点 ID")
        use_start = QPushButton("设为起点")
        use_start.clicked.connect(lambda: self.use_selected_node("start"))
        use_goal = QPushButton("设为终点")
        use_goal.clicked.connect(lambda: self.use_selected_node("goal"))
        run_preview = QPushButton("预览最短路")
        run_preview.setObjectName("Primary")
        run_preview.clicked.connect(self.preview_path)
        self.preview_result = QLabel("选择起终点后预览")
        self.preview_result.setObjectName("Muted")
        self.preview_result.setWordWrap(True)
        preview_grid.addWidget(QLabel("起点"), 0, 0)
        preview_grid.addWidget(self.start_node, 0, 1)
        preview_grid.addWidget(use_start, 0, 2)
        preview_grid.addWidget(QLabel("终点"), 1, 0)
        preview_grid.addWidget(self.goal_node, 1, 1)
        preview_grid.addWidget(use_goal, 1, 2)
        preview_grid.addWidget(run_preview, 2, 0, 1, 3)
        preview_grid.addWidget(self.preview_result, 3, 0, 1, 3)
        preview_tab_layout.addWidget(preview)
        preview_tab_layout.addStretch(1)
        tabs.addTab(preview_tab, "路径")

        issue_tab = QWidget()
        issue_tab_layout = QVBoxLayout(issue_tab)
        issue_tab_layout.setContentsMargins(0, 0, 0, 0)
        issue_tab_layout.setSpacing(8)
        issue_box = QGroupBox("校验结果")
        issue_layout = QVBoxLayout(issue_box)
        self.issue_summary = QLabel("尚未校验")
        self.issue_summary.setObjectName("Muted")
        self.issue_list = QListWidget()
        self.issue_list.itemClicked.connect(self.focus_issue)
        issue_layout.addWidget(self.issue_summary)
        issue_layout.addWidget(self.issue_list, 1)
        issue_tab_layout.addWidget(issue_box, 1)
        tabs.addTab(issue_tab, "校验")

        layout.addWidget(tabs, 1)
        self.inspector_tabs = tabs
        self.issue_tab = issue_tab
        return panel
