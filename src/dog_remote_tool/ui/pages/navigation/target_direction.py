from __future__ import annotations

import math

from PyQt5.QtCore import QSignalBlocker
from PyQt5.QtGui import QTextCursor

from dog_remote_tool.ui.pages.navigation import point_text


class NavigationTargetDirectionMixin:
    def current_direction_yaw(self) -> float:
        return math.radians(float(self.direction_degrees.value()))

    def set_direction_degrees(self, degrees: float) -> None:
        self.direction_degrees.setValue(float(degrees))
        dialog = getattr(self, "workspace_dialog", None)
        if dialog is not None:
            dialog.set_direction_degrees(float(degrees))

    def on_direction_degrees_changed(self) -> None:
        if self._syncing_direction:
            return
        self._syncing_direction = True
        try:
            self.goal_yaw.setValue(self.current_direction_yaw())
        finally:
            self._syncing_direction = False
        self.update_nav_map_points()

    def on_goal_yaw_changed(self) -> None:
        if self._syncing_direction:
            return
        degrees = math.degrees(float(self.goal_yaw.value()))
        while degrees > 180.0:
            degrees -= 360.0
        while degrees <= -180.0:
            degrees += 360.0
        self._syncing_direction = True
        try:
            self.direction_degrees.setValue(degrees)
        finally:
            self._syncing_direction = False
        self.update_nav_map_points()

    def set_widget_value_blocked(self, widget, value) -> None:
        if widget is None or not callable(getattr(widget, "setValue", None)):
            return
        try:
            with QSignalBlocker(widget):
                widget.setValue(value)
        except TypeError:
            widget.setValue(value)

    def set_goal_fields_from_point(self, x: float, y: float, yaw: float) -> None:
        NavigationTargetDirectionMixin.set_widget_value_blocked(self, getattr(self, "goal_x", None), x)
        NavigationTargetDirectionMixin.set_widget_value_blocked(self, getattr(self, "goal_y", None), y)
        NavigationTargetDirectionMixin.set_widget_value_blocked(self, getattr(self, "goal_yaw", None), yaw)
        direction = getattr(self, "direction_degrees", None)
        if direction is None:
            return
        degrees = math.degrees(yaw)
        while degrees > 180.0:
            degrees -= 360.0
        while degrees <= -180.0:
            degrees += 360.0
        self._syncing_direction = True
        try:
            NavigationTargetDirectionMixin.set_widget_value_blocked(self, direction, degrees)
        finally:
            self._syncing_direction = False

    def update_direction_from_map_drag(self, yaw: float) -> bool:
        self.goal_yaw.setValue(yaw)
        if self.waypoints_text.toPlainText().strip():
            lines = point_text.waypoint_lines(self.waypoints_text.toPlainText())
            parts = [part.strip() for part in lines[-1].replace("，", ",").split(",")]
            if len(parts) >= 2:
                lines[-1] = point_text.format_waypoint_line(float(parts[0]), float(parts[1]), yaw)
                self.waypoints_text.setPlainText("\n".join(lines))
                cursor = self.waypoints_text.textCursor()
                cursor.movePosition(QTextCursor.End)
                self.waypoints_text.setTextCursor(cursor)
                self.refresh_navigation_points_list(selected_row=len(lines) - 1)
        else:
            self.update_nav_map_points()
        self.nav_status_note.setText(f"方向已设定：{self.direction_degrees.value():.0f}°")
        self.refresh_workspace_from_page()
        return True
