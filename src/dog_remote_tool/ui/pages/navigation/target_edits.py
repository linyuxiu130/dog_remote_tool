from __future__ import annotations

from PyQt5.QtGui import QTextCursor

from dog_remote_tool.ui.pages.navigation import point_text
from dog_remote_tool.ui.pages.navigation.target_direction import NavigationTargetDirectionMixin
from dog_remote_tool.ui.pages.navigation.target_state import NavigationTargetStateMixin


class NavigationTargetEditsMixin(NavigationTargetStateMixin, NavigationTargetDirectionMixin):
    @staticmethod
    def _refresh_navigation_points_list(self, selected_row: int | None = None) -> None:
        refresh_list = getattr(self, "refresh_navigation_points_list", None)
        if callable(refresh_list):
            refresh_list(selected_row=selected_row)
        else:
            NavigationTargetEditsMixin.refresh_navigation_points_list(self, selected_row=selected_row)

    @staticmethod
    def _update_nav_map_points(self, selected_row: int | None = None) -> None:
        update_points = getattr(self, "update_nav_map_points", None)
        if callable(update_points):
            update_points(selected_row=selected_row)
            return
        points = NavigationTargetEditsMixin.visible_navigation_points(self)
        self.nav_map.set_points(points)
        if callable(getattr(self.nav_map, "set_route_target_node_ids", None)):
            self.nav_map.set_route_target_node_ids(getattr(self, "route_target_node_ids", []))
        NavigationTargetEditsMixin._refresh_navigation_points_list(self, selected_row=selected_row)
        dialog = getattr(self, "workspace_dialog", None)
        if dialog is not None:
            dialog.canvas.set_points(points)
            if callable(getattr(dialog.canvas, "set_route_target_node_ids", None)):
                dialog.canvas.set_route_target_node_ids(getattr(self, "route_target_node_ids", []))
            refresh_list = getattr(dialog, "refresh_point_list", None)
            if callable(refresh_list):
                refresh_list()

    def clear_navigation_points(self) -> bool:
        self.goal_point_selected = False
        self.route_target_node_ids = []
        self.added_waypoint_undo_stack = []
        self.waypoints_text.setPlainText("")
        self.nav_map.set_points([])
        if callable(getattr(self.nav_map, "set_route_target_node_ids", None)):
            self.nav_map.set_route_target_node_ids([])
        NavigationTargetEditsMixin._refresh_navigation_points_list(self)
        self.nav_status_note.setText("点位已清空")
        self.refresh_workspace_from_page()
        return True

    def delete_selected_navigation_point(self) -> bool:
        list_widget = getattr(self, "waypoints_list", None)
        row = list_widget.currentRow() if list_widget is not None and callable(getattr(list_widget, "currentRow", None)) else -1
        return NavigationTargetEditsMixin.delete_navigation_point(self, row)

    def delete_navigation_point(self, row: int) -> bool:
        points = NavigationTargetEditsMixin.visible_navigation_points(self)
        if not (0 <= row < len(points)):
            self.nav_status_note.setText("请先在点位列表中选中要删除的目标点")
            self.refresh_workspace_from_page()
            return False
        lines = point_text.waypoint_lines(self.waypoints_text.toPlainText())
        if not lines:
            NavigationTargetEditsMixin.clear_navigation_points(self)
            return True
        if row >= len(lines):
            return False
        self.added_waypoint_undo_stack = []
        removed = points[row]
        del lines[row]
        if getattr(self, "route_target_mode", False) and row < len(getattr(self, "route_target_node_ids", [])):
            del self.route_target_node_ids[row]
        self.waypoints_text.setPlainText("\n".join(lines))
        selected_row = min(row, len(lines) - 1)
        if lines:
            remaining = NavigationTargetEditsMixin.navigation_points(self)
            x, y, yaw = remaining[selected_row]
            NavigationTargetEditsMixin.set_goal_fields_from_point(self, x, y, yaw)
            self.goal_point_selected = True
        else:
            self.goal_point_selected = False
        NavigationTargetEditsMixin._update_nav_map_points(self, selected_row=selected_row)
        x, y, _yaw = removed
        self.nav_status_note.setText(f"已删除目标点 {row + 1}：x={x:.3f}, y={y:.3f}")
        self.refresh_workspace_from_page()
        return True

    def reorder_navigation_point(self, from_row: int, to_row: int) -> bool:
        points = NavigationTargetEditsMixin.visible_navigation_points(self)
        if not (0 <= from_row < len(points)) or not (0 <= to_row < len(points)) or from_row == to_row:
            return False
        self.added_waypoint_undo_stack = []
        lines = point_text.waypoint_lines(self.waypoints_text.toPlainText())
        if len(lines) != len(points):
            lines = [point_text.format_waypoint_line(x, y, yaw) for x, y, yaw in points]
        moved = lines.pop(from_row)
        lines.insert(to_row, moved)
        if getattr(self, "route_target_mode", False) and len(getattr(self, "route_target_node_ids", [])) == len(points):
            moved_node_id = self.route_target_node_ids.pop(from_row)
            self.route_target_node_ids.insert(to_row, moved_node_id)
        self.waypoints_text.setPlainText("\n".join(lines))
        x, y, yaw = NavigationTargetEditsMixin.navigation_points(self)[to_row]
        NavigationTargetEditsMixin.set_goal_fields_from_point(self, x, y, yaw)
        self.goal_point_selected = True
        NavigationTargetEditsMixin._update_nav_map_points(self, selected_row=to_row)
        self.nav_status_note.setText(f"已调整目标点顺序：{from_row + 1} → {to_row + 1}")
        self.refresh_workspace_from_page()
        return True

    def add_waypoint_from_map(
        self,
        x: float,
        y: float,
        route_node_id: int | None = None,
        yaw: float | None = None,
        previous_line_restore: tuple[int, str] | None = None,
    ) -> bool:
        if yaw is None:
            yaw = self.current_direction_yaw() if callable(getattr(self, "current_direction_yaw", None)) else 0.0
        lines = point_text.waypoint_lines(self.waypoints_text.toPlainText())
        lines.append(point_text.format_waypoint_line(x, y, yaw))
        row = len(lines) - 1
        if getattr(self, "route_target_mode", False) and route_node_id is not None:
            self.route_target_node_ids.append(route_node_id)
        self.waypoints_text.setPlainText("\n".join(lines))
        undo_stack = getattr(self, "added_waypoint_undo_stack", None)
        if undo_stack is None:
            undo_stack = []
            self.added_waypoint_undo_stack = undo_stack
        undo_stack.append((row, lines[-1], route_node_id, previous_line_restore))
        cursor = self.waypoints_text.textCursor()
        cursor.movePosition(QTextCursor.End)
        self.waypoints_text.setTextCursor(cursor)
        NavigationTargetEditsMixin._refresh_navigation_points_list(self, selected_row=row)
        return True

    def undo_last_added_navigation_point(self) -> bool:
        undo_stack = getattr(self, "added_waypoint_undo_stack", [])
        if not undo_stack:
            self.nav_status_note.setText("没有可撤销的新增目标点")
            self.refresh_workspace_from_page()
            return False
        entry = undo_stack.pop()
        row, expected_line, route_node_id = entry[:3]
        previous_line_restore = entry[3] if len(entry) >= 4 else None
        lines = point_text.waypoint_lines(self.waypoints_text.toPlainText())
        if not (0 <= row < len(lines)) or lines[row] != expected_line:
            self.added_waypoint_undo_stack = []
            self.nav_status_note.setText("新增目标点已被修改，无法撤销")
            self.refresh_workspace_from_page()
            return False
        removed = lines.pop(row)
        if row < len(getattr(self, "route_target_node_ids", [])):
            if route_node_id is not None and self.route_target_node_ids[row] != route_node_id:
                self.added_waypoint_undo_stack = []
                self.nav_status_note.setText("路网目标点顺序已变化，无法撤销")
                self.refresh_workspace_from_page()
                return False
            del self.route_target_node_ids[row]
        if previous_line_restore is not None:
            previous_row, previous_line = previous_line_restore
            if 0 <= previous_row < len(lines):
                lines[previous_row] = previous_line
        self.waypoints_text.setPlainText("\n".join(lines))
        if lines:
            selected_row = min(row, len(lines) - 1)
            x, y, yaw = NavigationTargetEditsMixin.navigation_points(self)[selected_row]
            NavigationTargetEditsMixin.set_goal_fields_from_point(self, x, y, yaw)
            self.goal_point_selected = True
        else:
            selected_row = -1
            self.goal_point_selected = False
        NavigationTargetEditsMixin._update_nav_map_points(self, selected_row=selected_row)
        parts = [part.strip() for part in removed.split(",")]
        detail = f"x={parts[0]}, y={parts[1]}" if len(parts) >= 2 else removed
        self.nav_status_note.setText(f"已撤销新增目标点：{detail}")
        self.refresh_workspace_from_page()
        return True
