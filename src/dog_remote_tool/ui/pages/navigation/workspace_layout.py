from __future__ import annotations

from typing import TYPE_CHECKING

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QKeySequence
from PyQt5.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QShortcut, QSplitter, QVBoxLayout

from dog_remote_tool.ui.pages.navigation.camera_overlay import NavigationCameraView
from dog_remote_tool.ui.pages.navigation.map_widgets import NavigationMapLabel
from dog_remote_tool.ui.pages.navigation.workspace_panels import NavigationWorkspacePanelsMixin

if TYPE_CHECKING:
    from dog_remote_tool.ui.pages.navigation.page import NavigationPage


class WorkspaceMapPipView(NavigationMapLabel):
    clicked = pyqtSignal()

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.LeftButton:
            self.clicked.emit()
            event.accept()
            return
        super().mousePressEvent(event)


class NavigationWorkspaceLayoutMixin(NavigationWorkspacePanelsMixin):
    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._position_workspace_camera()

    def _build_ui(self, page: "NavigationPage") -> None:
        undo_shortcut = QShortcut(QKeySequence.Undo, self)
        undo_shortcut.activated.connect(page.undo_last_added_navigation_point)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 14)
        layout.setSpacing(10)

        header = QHBoxLayout()
        title = QLabel("导航工作台")
        title.setObjectName("DialogTitle")
        self.detail_label = QLabel(page.workspace_map_title())
        self.detail_label.setObjectName("Muted")
        self.detail_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.detail_label.setWordWrap(True)
        close_button = QPushButton("退出全屏")
        close_button.clicked.connect(self.close)
        header.addWidget(title)
        header.addWidget(self.detail_label, 1)
        header.addWidget(close_button)
        layout.addLayout(header)

        workspace_splitter = QSplitter(Qt.Vertical)
        workspace_splitter.setChildrenCollapsible(False)
        splitter = QSplitter(Qt.Horizontal)
        splitter.setChildrenCollapsible(False)
        self.canvas = NavigationMapLabel()
        self.canvas.setMinimumHeight(620)
        self.canvas.setStyleSheet("background:transparent;border:0;color:#64748b;")
        self.canvas.point_clicked.connect(page.on_map_point_clicked)
        self.canvas.point_rejected.connect(page.on_map_point_rejected)
        self.canvas.point_delete_requested.connect(page.delete_navigation_point)
        self.canvas.direction_dragged.connect(page.update_direction_from_map_drag)
        if page.nav_map.source_pixmap and not page.nav_map.source_pixmap.isNull():
            self.canvas.set_map(page.nav_map.source_pixmap, page.nav_map.resolution, page.nav_map.origin)
            self.canvas.copy_safety_overlay_from(page.nav_map)
            self._nudge_workspace_map_view_right()
        else:
            self.canvas.setText("地图加载中")
        self.canvas.set_robot_pose(page.robot_pose)
        self.canvas.set_global_route(page.navigation_global_route)
        self.canvas.set_realtime_plan(page.navigation_realtime_plan)
        self.canvas.set_obstacle_points(page.navigation_obstacle_points)
        self.canvas.set_charging_docks(page.charging_docks)
        self.canvas.set_route_graph(page.route_graph)
        self.canvas.set_route_target_node_ids(page.route_target_node_ids)
        self.canvas.set_points(page.visible_navigation_points())
        self.workspace_camera_expanded = False
        self.camera_backdrop = QFrame(self.canvas)
        self.camera_backdrop.setObjectName("WorkspaceCameraBackdrop")
        self.camera_backdrop.setStyleSheet("QFrame#WorkspaceCameraBackdrop{background:#ffffff;border:0;}")
        self.camera_backdrop.hide()
        self.camera_view = NavigationCameraView()
        self.camera_view.setParent(self.canvas)
        self.camera_view.setObjectName("WorkspaceCameraOverlay")
        self.camera_view.setMinimumSize(360, 203)
        self.camera_view.resize(480, 270)
        self.camera_view.setText("")
        self.camera_view.clicked.connect(self.toggle_workspace_camera_focus)
        self.camera_view.setStyleSheet(
            "QLabel#WorkspaceCameraOverlay{background:#020617;border:0;"
            "border-radius:8px;color:#dbeafe;font-size:10pt;font-weight:700;}"
        )
        self.map_pip_view = WorkspaceMapPipView()
        self.map_pip_view.setParent(self.canvas)
        self.map_pip_view.setObjectName("WorkspaceMapPipOverlay")
        self.map_pip_view.setMinimumSize(300, 220)
        self.map_pip_view.clicked.connect(self.toggle_workspace_camera_focus)
        self.map_pip_view.hide()
        self.map_pip_view.setStyleSheet(
            "QLabel#WorkspaceMapPipOverlay{background:transparent;border:0;border-radius:8px;}"
        )
        self._sync_workspace_map_pip()
        self._position_workspace_camera()
        splitter.addWidget(self.canvas)

        side_panel = self._build_workspace_side_panel(page)
        splitter.addWidget(side_panel)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 0)
        splitter.setSizes([1300, 700])
        workspace_splitter.addWidget(splitter)

        log_panel = self._build_workspace_log_panel(page)
        workspace_splitter.addWidget(log_panel)
        workspace_splitter.setStretchFactor(0, 1)
        workspace_splitter.setStretchFactor(1, 0)
        workspace_splitter.setSizes([960, 190])
        layout.addWidget(workspace_splitter, 1)
        self.refresh_from_page()
        page.update_navigation_action_buttons(page.last_status_values)

    def _nudge_workspace_map_view_right(self) -> None:
        pixmap = getattr(self.canvas, "source_pixmap", None)
        if pixmap is None or pixmap.isNull():
            return
        self.canvas.view_widget_offset_ratio_x = 0.16
        center = getattr(self.canvas, "view_center_px", None) or (pixmap.width() / 2.0, pixmap.height() / 2.0)
        self.canvas.view_center_px = self.canvas._clamp_center((center[0] - pixmap.width() * 0.03, center[1]))

    def toggle_workspace_camera_focus(self) -> bool:
        self.workspace_camera_expanded = not bool(getattr(self, "workspace_camera_expanded", False))
        self._sync_workspace_map_pip()
        self._position_workspace_camera()
        return self.workspace_camera_expanded

    def _sync_workspace_map_pip(self) -> None:
        pip = getattr(self, "map_pip_view", None)
        canvas = getattr(self, "canvas", None)
        if pip is None or canvas is None:
            return
        pixmap = getattr(canvas, "source_pixmap", None)
        if pixmap is not None and not pixmap.isNull():
            pip.set_map(pixmap, canvas.resolution, canvas.origin)
            pip.copy_safety_overlay_from(canvas)
            pip.view_widget_offset_ratio_x = 0.0
            pip.set_robot_pose(canvas.robot_pose)
            pip.set_global_route(canvas.global_route)
            pip.set_realtime_plan(canvas.realtime_plan)
            pip.set_obstacle_points(canvas.obstacle_points)
            pip.set_charging_docks(canvas.charging_docks)
            pip.set_route_graph(canvas.route_graph)
            pip.set_route_target_node_ids(canvas.route_target_node_ids)
            pip.set_points(canvas.points)
        pip.setVisible(bool(getattr(self, "workspace_camera_expanded", False)))

    def _position_workspace_camera(self) -> None:
        view = getattr(self, "camera_view", None)
        canvas = getattr(self, "canvas", None)
        if view is None or canvas is None:
            return
        margin = 22
        expanded = bool(getattr(self, "workspace_camera_expanded", False))
        backdrop = getattr(self, "camera_backdrop", None)
        if backdrop is not None:
            backdrop.setGeometry(0, 0, canvas.width(), canvas.height())
            backdrop.setVisible(expanded)
        if getattr(self, "workspace_camera_expanded", False):
            max_width = max(320, canvas.width() - margin * 2)
            max_height = max(240, canvas.height() - margin * 2)
            width = max_width
            height = int(width * 9 / 16)
            if height > max_height:
                height = max_height
                width = int(height * 16 / 9)
            x = margin + max(0, (max_width - width) // 2)
            y = margin + max(0, (max_height - height) // 2)
        else:
            width = max(480, min(620, int(canvas.width() * 0.36)))
            height = int(width * 9 / 16)
            x = margin
            y = margin
        view.setGeometry(x, y, width, height)
        if backdrop is not None and expanded:
            backdrop.raise_()
        view.raise_()
        pip = getattr(self, "map_pip_view", None)
        if pip is not None:
            pip_width = max(300, min(420, int(canvas.width() * 0.28)))
            pip_height = max(220, int(pip_width * 0.72))
            pip.setGeometry(margin, margin, pip_width, pip_height)
            pip.raise_()
