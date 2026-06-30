from __future__ import annotations

from typing import TYPE_CHECKING

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QDialog

from dog_remote_tool.ui.pages.navigation.workspace_layout import NavigationWorkspaceLayoutMixin
from dog_remote_tool.ui.pages.navigation.workspace_points import NavigationWorkspacePointsMixin
from dog_remote_tool.ui.pages.navigation.workspace_table import WaypointTableWidget as _WaypointTableWidget

if TYPE_CHECKING:
    from dog_remote_tool.ui.pages.navigation.page import NavigationPage


WaypointTableWidget = _WaypointTableWidget


class NavigationWorkspaceDialog(NavigationWorkspaceLayoutMixin, NavigationWorkspacePointsMixin, QDialog):
    def __init__(self, page: "NavigationPage") -> None:
        super().__init__(None)
        self.page = page
        self.setObjectName("ToolDialog")
        self.setWindowTitle("导航地图")
        self.setWindowFlag(Qt.Window, True)
        self._build_ui(page)

    def show_workspace_fullscreen(self) -> None:
        screen = self.page.screen() if callable(getattr(self.page, "screen", None)) else None
        if screen is not None:
            self.setGeometry(screen.availableGeometry())
        self.showFullScreen()
        self.raise_()
        self.activateWindow()

    def set_workspace_target_mode(self, target: str) -> None:
        self.refresh_from_page()

    def set_direction_degrees(self, degrees: float) -> None:
        return None

    def refresh_from_page(self) -> None:
        self.detail_label.setText(self.page.workspace_map_title())
        self.update_route_button()
        self.point_summary.setText(self.page.target_summary_text())
        self.robot_summary.setText(self.page.robot_pose_summary_text())
        for card, source in zip(
            self.status_cards,
            (
                self.page.nav_current_state,
                self.page.map_state,
                self.page.localization_state,
                self.page.navigation_state,
            ),
        ):
            self._sync_workspace_status_card(card, source)
        self.canvas.set_points(self.page.visible_navigation_points())
        self.canvas.set_charging_docks(self.page.charging_docks)
        self.canvas.set_route_graph(self.page.route_graph)
        self.canvas.set_route_target_node_ids(self.page.route_target_node_ids)
        self.canvas.set_robot_pose(self.page.robot_pose)
        self.canvas.set_global_route(self.page.navigation_global_route)
        self.canvas.set_realtime_plan(self.page.navigation_realtime_plan)
        self.canvas.set_obstacle_points(self.page.navigation_obstacle_points)
        sync_map_pip = getattr(self, "_sync_workspace_map_pip", None)
        if callable(sync_map_pip):
            sync_map_pip()
        self.refresh_point_list()
        self.status_label.setText(self.page.nav_status_note.text())
        self.status_label.setVisible(self.status_label.text() not in {"", "等待状态刷新"})
        self.log_view.setPlainText(self.page.navigation_log_text())
        self.log_view.moveCursor(self.log_view.textCursor().End)

    def update_route_button(self) -> None:
        label = self.page.route_action_label()
        self.route_button.setText(label)
        self.route_button.setEnabled(True)
        if label == "检查路网":
            self.route_button.setToolTip("检查所选历史图目录下是否已有 map.geojson")
        else:
            self.route_button.setToolTip("")
