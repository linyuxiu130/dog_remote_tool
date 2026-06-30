from __future__ import annotations

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QComboBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from dog_remote_tool.modules.navigation import route_network
from dog_remote_tool.ui.pages.route_network.inspector_panel import RouteNetworkInspectorPanelMixin


class RouteNetworkLayoutMixin(RouteNetworkInspectorPanelMixin):
    def _make_top_panel(self) -> QWidget:
        top = QFrame()
        top.setObjectName("RouteWorkbenchHeader")
        top_layout = QGridLayout(top)
        top_layout.setContentsMargins(12, 10, 12, 10)
        top_layout.setHorizontalSpacing(8)
        top_layout.setVerticalSpacing(6)
        top_layout.setColumnStretch(1, 3)
        top_layout.setColumnStretch(4, 2)

        self.map_path = QLineEdit()
        self.map_path.setPlaceholderText("选择 map.yaml")
        self.geojson_path = QLineEdit()
        self.geojson_path.setPlaceholderText("选择或保存 map.geojson")
        self.remote_route_path = QLineEdit(route_network.DEFAULT_REMOTE_ROUTE_FILE)
        self.history_map_selector = QComboBox()
        self.history_map_selector.hide()
        self.history_map_selector.setMinimumWidth(0)
        self.history_map_selector.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.history_map_selector.currentIndexChanged.connect(self.on_history_map_changed)
        self.history_map_cards_empty = QLabel("暂无历史图")
        self.history_map_cards_empty.setObjectName("Muted")
        self.history_map_cards_empty.setAlignment(Qt.AlignCenter)
        self.history_map_cards_empty.setMinimumHeight(208)
        self.history_map_cards_panel = QWidget()
        self.history_map_cards_layout = QHBoxLayout(self.history_map_cards_panel)
        self.history_map_cards_layout.setContentsMargins(0, 0, 0, 0)
        self.history_map_cards_layout.setSpacing(10)
        self.selected_history_detail = QLabel("远端目录：--")
        self.selected_history_detail.setObjectName("Muted")
        self.selected_history_detail.setWordWrap(True)
        self.status_label = QLabel("未加载路网")
        self.status_label.setObjectName("RouteStatusNeutral")
        self.status_label.setMinimumWidth(92)
        self.status_label.setAlignment(Qt.AlignCenter)
        for line_edit in (self.map_path, self.geojson_path, self.remote_route_path):
            line_edit.setMinimumWidth(0)
            line_edit.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        open_map = QPushButton("打开底图")
        open_map.clicked.connect(self.open_map)
        open_geojson = QPushButton("打开路网")
        open_geojson.clicked.connect(self.open_geojson)
        pull = QPushButton("拉取路网")
        pull.setToolTip("从选中地图目录拉取 map.geojson 到本地")
        pull.clicked.connect(self.pull_remote_route)
        remote_status = QPushButton("检查状态")
        remote_status.setToolTip("检查远端路网文件和 update_graph 服务")
        remote_status.clicked.connect(self.check_remote_status)
        refresh_history = QPushButton("刷新地图")
        refresh_history.setToolTip("读取远端地图列表")
        refresh_history.clicked.connect(self.refresh_history_map_list)
        new_online = QPushButton("新建路网")
        new_online.setObjectName("Primary")
        new_online.setToolTip("基于所选历史地图创建对应的 map.geojson")
        new_online.clicked.connect(self.new_route_for_selected_history)
        edit_online = QPushButton("编辑路网")
        edit_online.setToolTip("打开全屏路网编辑器")
        edit_online.clicked.connect(self.open_route_editor)
        upload = QPushButton("上传路网")
        upload.setToolTip("上传当前路网文件到选中地图目录")
        upload.clicked.connect(self.upload_route)
        load = QPushButton("加载路网")
        load.setToolTip("调用 /RouteGraphPlanner/update_graph 加载远端 map.geojson；建图轨迹 map.txt 不能直接作为路网加载")
        load.clicked.connect(self.load_remote_graph)

        map_header = QHBoxLayout()
        map_header.setContentsMargins(0, 0, 0, 0)
        map_header.setSpacing(8)
        map_title = QLabel("地图")
        map_title.setObjectName("RouteInspectorTitle")
        map_header.addWidget(map_title)
        map_header.addStretch(1)
        refresh_history.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self.status_label.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        map_header.addWidget(refresh_history)
        map_header.addWidget(self.status_label)
        top_layout.addLayout(map_header, 0, 0, 1, 6)
        top_layout.addWidget(self.history_map_cards_empty, 1, 0, 1, 6)
        top_layout.addWidget(self.history_map_cards_panel, 1, 0, 1, 6)
        self.history_map_cards_panel.hide()
        top_layout.addWidget(self.selected_history_detail, 2, 0, 1, 6)
        top_layout.addWidget(QLabel("远端路网"), 3, 0)
        top_layout.addWidget(self.remote_route_path, 3, 1, 1, 5)
        online_row = QHBoxLayout()
        online_row.setSpacing(6)
        for button in (new_online, edit_online, pull, upload, load, remote_status):
            button.setMinimumHeight(28)
            button.setMinimumWidth(78)
            button.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            online_row.addWidget(button)
        top_layout.addLayout(online_row, 4, 1, 1, 5)
        top_layout.addWidget(QLabel("路网操作"), 4, 0)
        top_layout.addWidget(QLabel("本地底图"), 5, 0)
        top_layout.addWidget(self.map_path, 5, 1)
        top_layout.addWidget(open_map, 5, 2)
        top_layout.addWidget(QLabel("本地路网"), 5, 3)
        top_layout.addWidget(self.geojson_path, 5, 4)
        top_layout.addWidget(open_geojson, 5, 5)
        return top

    def _make_info_strip(self) -> QWidget:
        strip = QFrame()
        strip.setObjectName("RouteInfoStrip")
        layout = QHBoxLayout(strip)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(8)
        self.scale_state_label = QLabel("比例：等待加载")
        self.scale_state_label.setObjectName("RouteInfoBadge")
        self.map_scale_label = QLabel("底图：--")
        self.map_scale_label.setObjectName("RouteInfoText")
        self.graph_summary_label = QLabel("路网：0 点 / 0 边")
        self.graph_summary_label.setObjectName("RouteInfoText")
        self.inflation_state_label = QLabel("膨胀：未读取")
        self.inflation_state_label.setObjectName("RouteInfoText")
        self.inflation_state_label.setToolTip("路网编辑障碍显示使用默认障碍膨胀半径")
        self.cursor_label = QLabel("坐标：--")
        self.cursor_label.setObjectName("RouteInfoText")
        self.tool_hint_label = QLabel("方向键/WASD 平移，+/- 缩放，0 复位")
        self.tool_hint_label.setObjectName("RouteInfoText")
        self.tool_hint_label.setMinimumWidth(0)
        self.tool_hint_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        for label in (
            self.map_scale_label,
            self.graph_summary_label,
            self.inflation_state_label,
            self.cursor_label,
            self.tool_hint_label,
        ):
            label.setMinimumHeight(28)
        layout.addWidget(self.scale_state_label)
        layout.addWidget(self.map_scale_label)
        layout.addWidget(self.graph_summary_label)
        layout.addWidget(self.inflation_state_label)
        layout.addWidget(self.cursor_label)
        layout.addWidget(self.tool_hint_label, 1)
        return strip

    def _make_toolbar(self) -> QWidget:
        box = QFrame()
        box.setObjectName("RouteToolRail")
        box.setFixedWidth(76)
        layout = QVBoxLayout(box)
        layout.setContentsMargins(6, 8, 6, 8)
        layout.setSpacing(6)
        self.tool_buttons: dict[str, QPushButton] = {}
        tools = [
            ("select", "选取\n移动", "点击点或边查看属性；拖动节点会同步更新连线"),
            ("edge", "加点\n连线", "左键加点/连线；右键删除命中的点或边"),
        ]
        for key, label, tooltip in tools:
            button = QPushButton(label)
            button.setCheckable(True)
            button.setToolTip(tooltip)
            button.setObjectName("RouteToolButton")
            button.clicked.connect(lambda _checked=False, mode=key: self.set_tool(mode))
            layout.addWidget(button)
            self.tool_buttons[key] = button
        layout.addStretch(1)
        return box
