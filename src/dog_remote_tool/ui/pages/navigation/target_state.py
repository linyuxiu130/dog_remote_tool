from __future__ import annotations

from PyQt5.QtCore import QSignalBlocker

from dog_remote_tool.modules import navigation
from dog_remote_tool.ui.pages.navigation import point_text


class NavigationTargetStateMixin:
    def current_target_mode(self) -> str:
        return "route" if getattr(self, "route_target_mode", False) else "points"

    def target_summary_text(self) -> str:
        points = NavigationTargetStateMixin.visible_navigation_points(self)
        return point_text.format_target_summary(
            points,
            route_target_mode=getattr(self, "route_target_mode", False),
            route_graph=getattr(self, "route_graph", None),
        )

    def navigation_point_rows(self) -> list[str]:
        return point_text.format_navigation_point_rows(
            NavigationTargetStateMixin.visible_navigation_points(self),
            route_target_mode=getattr(self, "route_target_mode", False),
        )

    def refresh_navigation_points_list(self, selected_row: int | None = None) -> None:
        list_widget = getattr(self, "waypoints_list", None)
        if list_widget is None:
            return
        rows = NavigationTargetStateMixin.navigation_point_rows(self)
        if selected_row is None:
            selected_row = list_widget.currentRow() if callable(getattr(list_widget, "currentRow", None)) else -1

        def apply_rows() -> None:
            list_widget.clear()
            list_widget.addItems(rows)
            if rows:
                list_widget.setCurrentRow(min(max(selected_row, 0), len(rows) - 1))

        try:
            with QSignalBlocker(list_widget):
                apply_rows()
        except TypeError:
            apply_rows()
        delete_button = getattr(self, "delete_waypoint_button", None)
        if delete_button is not None:
            delete_button.setEnabled(bool(rows) and list_widget.currentRow() >= 0)

    def robot_pose_summary_text(self) -> str:
        return point_text.robot_pose_summary_text(
            getattr(self, "robot_pose", None),
            getattr(self, "last_status_values", {}) or {},
        )

    def navigation_values(self) -> tuple[str, float, float, float, float, float]:
        return (
            self.map_pcd_path.text().strip() or navigation.default_goal_map_path(self.profile()),
            float(self.goal_x.value()),
            float(self.goal_y.value()),
            float(self.goal_yaw.value()),
            float(self.goal_speed.value()),
            float(self.goal_tolerance.value()),
        )

    def navigation_points(self) -> list[tuple[float, float, float]]:
        return point_text.parse_navigation_points(
            self.waypoints_text.toPlainText(),
            (float(self.goal_x.value()), float(self.goal_y.value()), float(self.goal_yaw.value())),
        )

    def visible_navigation_points(self) -> list[tuple[float, float, float]]:
        text = self.waypoints_text.toPlainText()
        fallback = (
            (0.0, 0.0, 0.0)
            if text.strip()
            else (float(self.goal_x.value()), float(self.goal_y.value()), float(self.goal_yaw.value()))
        )
        return point_text.visible_navigation_points(
            text,
            getattr(self, "goal_point_selected", True),
            fallback,
        )
