from __future__ import annotations

import math

from PyQt5.QtCore import QSignalBlocker

from dog_remote_tool.modules.navigation import route_network
from dog_remote_tool.ui.pages.navigation.target_edits import NavigationTargetEditsMixin
from dog_remote_tool.ui.pages.navigation.target_route_points import NavigationRouteTargetPointsMixin


class NavigationTargetPointsMixin(
    NavigationTargetEditsMixin,
    NavigationRouteTargetPointsMixin,
):
    def on_goal_coordinate_changed(self) -> None:
        self.goal_point_selected = True
        self.update_nav_map_points()

    def on_waypoints_text_changed(self) -> None:
        self.goal_point_selected = bool(self.waypoints_text.toPlainText().strip()) or bool(
            getattr(self, "goal_point_selected", False)
        )
        if getattr(self, "route_target_mode", False):
            line_count = len([line for line in self.waypoints_text.toPlainText().splitlines() if line.strip()])
            if line_count != len(getattr(self, "route_target_node_ids", [])):
                self.route_target_node_ids = []
                self.added_waypoint_undo_stack = []
        self.update_nav_map_points()
        self.refresh_workspace_from_page()

    def on_navigation_point_selection_changed(self, row: int) -> None:
        points = NavigationTargetPointsMixin.visible_navigation_points(self)
        delete_button = getattr(self, "delete_waypoint_button", None)
        if delete_button is not None:
            delete_button.setEnabled(0 <= row < len(points))
        if not (0 <= row < len(points)):
            return
        x, y, yaw = points[row]
        NavigationTargetPointsMixin.set_goal_fields_from_point(self, x, y, yaw)

    def update_target_hint(self) -> None:
        if getattr(self, "route_target_mode", False):
            hint = "路网目标模式：点击路网节点附近设定目标，使用“开始路网导航”下发"
        else:
            hint = "点击地图添加目标点，按住拖动设置最后一个目标方向"
        self.nav_map.setToolTip(hint)
        dialog = getattr(self, "workspace_dialog", None)
        if dialog is not None:
            dialog.canvas.setToolTip(hint)
        self.refresh_workspace_from_page()

    def on_map_point_clicked(self, x: float, y: float) -> bool:
        if getattr(self, "route_target_mode", False):
            graph = getattr(self, "route_graph", None)
            if graph is None or not graph.nodes:
                self.nav_status_note.setText("路网目标模式未加载路网，请先点击“路网导航”加载路网")
                self.refresh_workspace_from_page()
                return False
            node_id = route_network.nearest_node(graph, x, y, max_distance=0.60)
            if node_id is None:
                self.nav_status_note.setText("未命中路网节点，请点击路网节点附近重新选择")
                self.refresh_workspace_from_page()
                return False
            if getattr(self, "route_target_node_ids", []) and self.route_target_node_ids[-1] == node_id:
                self.nav_status_note.setText(f"路网目标节点 {node_id} 已是最后一个目标，不能连续重复添加")
                self.refresh_workspace_from_page()
                return False
            node = graph.nodes[node_id]
            snapped_x, snapped_y = node.x, node.y
            previous_line_restore, previous_yaw = NavigationTargetPointsMixin.update_previous_route_target_yaw(
                self, graph, node_id
            )
            yaw = NavigationTargetPointsMixin.route_target_yaw(self, graph, node_id)
            if yaw is None:
                yaw = self.current_direction_yaw() if callable(getattr(self, "current_direction_yaw", None)) else 0.0
            NavigationTargetPointsMixin.set_goal_fields_from_point(self, snapped_x, snapped_y, yaw)
            self.goal_point_selected = True
            NavigationTargetPointsMixin.add_waypoint_from_map(
                self,
                snapped_x,
                snapped_y,
                route_node_id=node_id,
                yaw=yaw,
                previous_line_restore=previous_line_restore,
            )
            NavigationTargetPointsMixin.update_nav_map_points(self, selected_row=len(self.route_target_node_ids) - 1)
            note = f"已添加路网目标节点 {node_id}：x={snapped_x:.3f}, y={snapped_y:.3f}, 方向={math.degrees(yaw):.0f}°"
            if previous_yaw is not None:
                note += f"；上一目标方向已更新为 {math.degrees(previous_yaw):.0f}°"
            self.nav_status_note.setText(note)
            warmup = getattr(self, "ensure_navigation_helpers", None)
            if callable(warmup):
                warmup()
            self.refresh_workspace_from_page()
            update_buttons = getattr(self, "update_navigation_action_buttons", None)
            if callable(update_buttons):
                update_buttons(getattr(self, "last_status_values", {}))
            return True
        with QSignalBlocker(self.goal_x):
            self.goal_x.setValue(x)
        with QSignalBlocker(self.goal_y):
            self.goal_y.setValue(y)
        self.goal_point_selected = True
        NavigationTargetPointsMixin.add_waypoint_from_map(self, x, y)
        self.nav_status_note.setText(f"已添加目标点：x={x:.3f}, y={y:.3f}, 方向={self.direction_degrees.value():.0f}°")
        self.refresh_workspace_from_page()
        return True

    def on_map_point_rejected(self, message: str) -> bool:
        self.nav_status_note.setText(message)
        self.refresh_workspace_from_page()
        return True

    def update_nav_map_points(self, selected_row: int | None = None) -> None:
        points = NavigationTargetPointsMixin.visible_navigation_points(self)
        self.nav_map.set_points(points)
        if callable(getattr(self.nav_map, "set_route_target_node_ids", None)):
            self.nav_map.set_route_target_node_ids(getattr(self, "route_target_node_ids", []))
        NavigationTargetPointsMixin.refresh_navigation_points_list(self, selected_row=selected_row)
        dialog = getattr(self, "workspace_dialog", None)
        if dialog is not None:
            dialog.canvas.set_points(points)
            if callable(getattr(dialog.canvas, "set_route_target_node_ids", None)):
                dialog.canvas.set_route_target_node_ids(getattr(self, "route_target_node_ids", []))
            refresh_list = getattr(dialog, "refresh_point_list", None)
            if callable(refresh_list):
                refresh_list()

    def update_robot_pose_on_maps(self) -> None:
        self.nav_map.set_robot_pose(self.robot_pose)
        dialog = getattr(self, "workspace_dialog", None)
        if dialog is not None:
            dialog.canvas.set_robot_pose(self.robot_pose)
            dialog.robot_summary.setText(self.robot_pose_summary_text())
