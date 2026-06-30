from __future__ import annotations

from dog_remote_tool.modules.navigation import route_network
from dog_remote_tool.ui.pages.navigation import point_text
from dog_remote_tool.ui.pages.navigation import route_target_geometry


class NavigationRouteTargetPointsMixin:
    def route_target_yaw(self, graph: route_network.RouteGraph, node_id: int) -> float | None:
        route_targets = list(getattr(self, "route_target_node_ids", []))
        if route_targets:
            yaw = NavigationRouteTargetPointsMixin.route_path_yaw(graph, route_targets[-1], node_id)
            if yaw is not None:
                return yaw
        robot_pose = getattr(self, "robot_pose", None)
        if robot_pose is not None:
            start_id = route_network.nearest_node(graph, float(robot_pose[0]), float(robot_pose[1]), max_distance=1.50)
            if start_id is not None:
                yaw = NavigationRouteTargetPointsMixin.route_path_yaw(graph, start_id, node_id)
                if yaw is not None:
                    return yaw
        return NavigationRouteTargetPointsMixin.route_node_outgoing_yaw(graph, node_id)

    @staticmethod
    def route_path_yaw(graph: route_network.RouteGraph, start_id: int, goal_id: int) -> float | None:
        return route_target_geometry.route_path_yaw(graph, start_id, goal_id)

    @staticmethod
    def route_path_start_yaw(graph: route_network.RouteGraph, start_id: int, goal_id: int) -> float | None:
        return route_target_geometry.route_path_start_yaw(graph, start_id, goal_id)

    @staticmethod
    def route_node_outgoing_yaw(graph: route_network.RouteGraph, node_id: int) -> float | None:
        return route_target_geometry.route_node_outgoing_yaw(graph, node_id)

    @staticmethod
    def route_segment_yaw(
        graph: route_network.RouteGraph,
        from_id: int,
        to_id: int,
        edge_id: int | None = None,
        *,
        final_segment: bool = True,
    ) -> float | None:
        return route_target_geometry.route_segment_yaw(
            graph,
            from_id,
            to_id,
            edge_id,
            final_segment=final_segment,
        )

    def update_previous_route_target_yaw(
        self,
        graph: route_network.RouteGraph,
        node_id: int,
    ) -> tuple[tuple[int, str] | None, float | None]:
        route_targets = list(getattr(self, "route_target_node_ids", []))
        if not route_targets:
            return None, None
        previous_node_id = route_targets[-1]
        previous_yaw = NavigationRouteTargetPointsMixin.route_path_start_yaw(graph, previous_node_id, node_id)
        if previous_yaw is None:
            return None, None
        previous_row = len(route_targets) - 1
        restore = NavigationRouteTargetPointsMixin.rewrite_waypoint_line_yaw(self, previous_row, previous_yaw)
        if restore is not None:
            refresh_points = getattr(self, "refresh_navigation_points_list", None)
            if callable(refresh_points):
                refresh_points(selected_row=previous_row)
        return restore, previous_yaw

    def rewrite_waypoint_line_yaw(self, row: int, yaw: float) -> tuple[int, str] | None:
        lines = point_text.waypoint_lines(self.waypoints_text.toPlainText())
        if not (0 <= row < len(lines)):
            return None
        try:
            points = self.navigation_points()
        except AttributeError:
            points = point_text.parse_navigation_points(
                self.waypoints_text.toPlainText(),
                (float(self.goal_x.value()), float(self.goal_y.value()), float(self.goal_yaw.value())),
            )
        except ValueError:
            return None
        if row >= len(points):
            return None
        x, y, _old_yaw = points[row]
        previous_line = lines[row]
        new_line = point_text.format_waypoint_line(x, y, yaw)
        if previous_line == new_line:
            return None
        lines[row] = new_line
        self.waypoints_text.setPlainText("\n".join(lines))
        return row, previous_line
