from __future__ import annotations

from PyQt5.QtWidgets import (
    QCheckBox,
    QDoubleSpinBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QSizePolicy,
    QWidget,
)

from dog_remote_tool.modules.navigation import route_network
from dog_remote_tool.ui.route_editor_side_panel import RouteEditorSidePanelMixin


class RouteEditorLayoutMixin(RouteEditorSidePanelMixin):
    def _make_header(self) -> QFrame:
        header = QFrame()
        header.setObjectName("RouteEditorHeader")
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(14, 10, 14, 10)
        header_layout.setSpacing(8)
        title = QLabel("路网详细编辑")
        title.setObjectName("RouteEditorTitle")
        self.editor_status = QLabel("选择工具后在地图上操作")
        self.editor_status.setObjectName("RouteInfoText")
        self.editor_status.setMinimumWidth(260)
        self.editor_status.setMaximumWidth(360)
        self.editor_summary = QLabel("--")
        self.editor_summary.setObjectName("RouteInfoText")
        self.remote_save_progress = QProgressBar()
        self.remote_save_progress.setRange(0, 100)
        self.remote_save_progress.setValue(0)
        self.remote_save_progress.setFormat("待上传")
        self.remote_save_progress.setFixedWidth(118)
        self.remote_save_progress.setFixedHeight(28)
        self.remote_save_progress.setVisible(remote_save_default := self._save_to_remote_by_default())
        show_labels = QCheckBox("显示ID")
        show_labels.setObjectName("RouteEditorCheck")
        show_labels.toggled.connect(lambda checked: self.canvas.set_display_options(show_node_labels=checked))
        show_arrows = QCheckBox("方向箭头")
        show_arrows.setObjectName("RouteEditorCheck")
        show_arrows.setChecked(True)
        show_arrows.toggled.connect(lambda checked: self.canvas.set_display_options(show_direction_arrows=checked))
        show_inflation = QCheckBox("膨胀边缘")
        show_inflation.setObjectName("RouteEditorCheck")
        show_inflation.setChecked(bool(self.page.canvas.show_inflation_overlay))
        show_inflation.toggled.connect(self.set_inflation_visible)
        self.inflation_label = QLabel(self.page.canvas.inflation_overlay_label or "膨胀：未读取")
        self.inflation_label.setObjectName("RouteInfoText")
        self.inflation_label.setMinimumHeight(28)
        self.inflation_label.setToolTip("当前路网障碍膨胀显示使用默认障碍膨胀半径")
        new_graph = QPushButton("新建")
        new_graph.setToolTip("清空当前路网并创建新图")
        new_graph.clicked.connect(self.new_editor_graph)
        add_pose = QPushButton("当前位置加点")
        add_pose.setToolTip("持续定位正常时，读取当前车在地图上的位置并添加节点")
        add_pose.clicked.connect(self.add_current_pose_node)
        self.keyboard_remote_btn = QPushButton("开始键盘遥控")
        self.keyboard_remote_btn.setObjectName("SoftPrimary")
        self.keyboard_remote_btn.setToolTip("启动或关闭键盘遥控，W/S/A/D/Q/E 控制移动，X 回中")
        self.keyboard_remote_btn.clicked.connect(self.toggle_keyboard_remote)
        self.save_route_button = QPushButton("上传远端")
        self.save_route_button.setObjectName("Primary")
        self.save_route_button.setToolTip("上传当前本地 map.geojson 到机器人当前历史图目录")
        self.save_route_button.setVisible(remote_save_default)
        self.save_route_button.clicked.connect(self.save_editor_geojson)
        close = QPushButton("关闭")
        close.clicked.connect(self.accept)
        header_layout.addWidget(title)
        header_layout.addWidget(self.editor_status, 1)
        header_layout.addWidget(self.editor_summary)
        header_layout.addWidget(self.remote_save_progress)
        header_layout.addWidget(show_labels)
        header_layout.addWidget(show_arrows)
        header_layout.addWidget(show_inflation)
        header_layout.addWidget(self.inflation_label)
        header_layout.addWidget(new_graph)
        header_layout.addWidget(add_pose)
        header_layout.addWidget(self.keyboard_remote_btn)
        header_layout.addWidget(self.save_route_button)
        header_layout.addWidget(close)
        return header

    def _make_toolbar(self) -> QWidget:
        box = QFrame()
        box.setObjectName("RouteToolRail")
        box.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        layout = QHBoxLayout(box)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(8)
        self.editor_tool_buttons: dict[str, QPushButton] = {}
        tools = [
            ("select", "选取移动", "点击点或边查看属性；拖动节点会同步更新连线"),
            ("edge", "加点连线", "左键加点/连线；右键删除命中的点或边"),
        ]
        for key, label, tooltip in tools:
            button = QPushButton(label)
            button.setCheckable(True)
            button.setToolTip(tooltip)
            button.setObjectName("RouteToolButton")
            button.setMinimumSize(112, 38)
            button.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
            button.clicked.connect(lambda _checked=False, mode=key: self.set_tool(mode))
            layout.addWidget(button)
            self.editor_tool_buttons[key] = button
        default_width_label = QLabel("新边路宽")
        default_width_label.setObjectName("Muted")
        self.new_edge_width_spin = QDoubleSpinBox()
        self.new_edge_width_spin.setRange(route_network.MIN_ROUTE_PASSABLE_WIDTH, route_network.MAX_ROUTE_PASSABLE_WIDTH)
        self.new_edge_width_spin.setDecimals(2)
        self.new_edge_width_spin.setSingleStep(0.1)
        self.new_edge_width_spin.setSuffix(" m")
        self.new_edge_width_spin.setValue(
            route_network.normalized_passable_width(
                getattr(self.canvas, "new_edge_passable_width", route_network.DEFAULT_ROUTE_PASSABLE_WIDTH)
            )
        )
        self.new_edge_width_spin.setToolTip("之后新建连边默认写入的 passable_width；已有连边在右侧属性里单独修改")
        self.new_edge_width_spin.valueChanged.connect(self.set_new_edge_passable_width)
        layout.addWidget(default_width_label)
        layout.addWidget(self.new_edge_width_spin)
        usage_note = QLabel("左键加点/连线，方向键/WASD 平移，+/- 缩放，Ctrl+Z 撤销")
        usage_note.setObjectName("Muted")
        usage_note.setToolTip("靠近已有节点时会选中节点；0 或 Home 可复位视图；Ctrl+Z 撤销上一步")
        layout.addWidget(usage_note)
        layout.addStretch(1)
        return box

    def set_new_edge_passable_width(self, width: float) -> None:
        normalized = route_network.normalized_passable_width(width)
        self.canvas.set_new_edge_passable_width(normalized)
        page_canvas = getattr(getattr(self, "page", None), "canvas", None)
        if page_canvas is not None and callable(getattr(page_canvas, "set_new_edge_passable_width", None)):
            page_canvas.set_new_edge_passable_width(normalized)
