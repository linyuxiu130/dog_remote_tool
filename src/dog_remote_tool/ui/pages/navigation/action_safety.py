from __future__ import annotations

from dog_remote_tool.modules.navigation import route_network
from dog_remote_tool.ui.pages.navigation.page_refs import navigation_page_class, navigation_page_module


class NavigationActionSafetyMixin:
    def single_goal_ready(self) -> bool:
        return bool(getattr(self, "goal_point_selected", True))

    def warn_single_goal_missing(self) -> bool:
        navigation_page = navigation_page_module()
        message = "请先在地图上点击一个目标点，或手动输入目标坐标后再开始单点导航。"
        navigation_page.QMessageBox.information(self, "目标点未选择", message)
        self.nav_status_note.setText("单点导航未下发：请先选择目标点")
        self.refresh_workspace_from_page()
        return False

    def warn_point_goal_missing(self) -> bool:
        navigation_page = navigation_page_module()
        message = "请先在地图上点击一个目标点。"
        navigation_page.QMessageBox.information(self, "目标点未选择", message)
        self.nav_status_note.setText("点位导航未下发：请先选择目标点")
        self.refresh_workspace_from_page()
        return False

    def validate_navigation_points_safety(self, points: list[tuple[float, float, float]], operation: str) -> bool:
        page = navigation_page_class()
        for index, (x, y, _yaw) in enumerate(points, start=1):
            status = page.navigation_point_safety_status(self, x, y)
            if status in {"free", "unchecked"}:
                continue
            reason = page.navigation_safety_reason(status)
            message = f"{operation}未下发：第 {index} 个目标点{reason}"
            self.nav_status_note.setText(message)
            self.refresh_workspace_from_page()
            navigation_page_module().QMessageBox.information(self, "目标点不可用", f"第 {index} 个目标点 x={x:.3f}, y={y:.3f} {reason}。")
            return False
        return True

    def validate_route_loop_closure(self) -> bool:
        graph = getattr(self, "route_graph", None)
        node_ids = list(getattr(self, "route_target_node_ids", []) or [])
        if graph is None or len(node_ids) < 2:
            return True
        start_id = int(node_ids[0])
        end_id = int(node_ids[-1])
        if start_id == end_id:
            return True
        path = route_network.shortest_path(graph, end_id, start_id)
        if path.reachable:
            return True
        message = f"循环不可闭合：最后目标节点 {end_id} 无法沿路网回到第一个目标节点 {start_id}。"
        self.nav_status_note.setText(message)
        self.refresh_workspace_from_page()
        navigation_page_module().QMessageBox.information(
            self,
            "循环不可闭合",
            message + "请补充闭合边、调整边方向，或把最后一个目标点改到可回到起点的位置。",
        )
        return False

    def navigation_point_safety_status(self, x: float, y: float) -> str:
        nav_map = getattr(self, "nav_map", None)
        if nav_map is None:
            return "unchecked"
        source_pixmap = getattr(nav_map, "source_pixmap", None)
        if source_pixmap is None or (callable(getattr(source_pixmap, "isNull", None)) and source_pixmap.isNull()):
            return "unchecked"
        checker = getattr(nav_map, "safety_status_at_world", None)
        if not callable(checker):
            return "unchecked"
        return str(checker(float(x), float(y)))

    @staticmethod
    def navigation_safety_reason(status: str) -> str:
        if status == "outside":
            return "不在地图范围内"
        if status == "blocked":
            return "在障碍区内"
        if status == "inflated":
            return "在障碍/未知膨胀区内"
        return "在未知/不可通行区域内"
