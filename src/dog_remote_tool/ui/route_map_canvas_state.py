from __future__ import annotations

from PyQt5.QtGui import QPixmap

from ..modules.navigation import route_network
from ..modules.navigation.route_network import MapMetadata, RouteGraph, ValidationIssue


class RouteMapCanvasStateMixin:
    def set_map(self, pixmap: QPixmap, metadata: MapMetadata | None) -> None:
        self.pixmap = pixmap
        self.map_metadata = metadata
        self.reset_view()
        self.update()

    def set_inflation_overlay(self, pixmap: QPixmap | None, label: str = "") -> None:
        self.inflation_overlay = pixmap
        self.inflation_overlay_label = label
        self.update()

    def set_show_inflation_overlay(self, visible: bool) -> None:
        self.show_inflation_overlay = visible
        self.update()

    def set_new_edge_passable_width(self, width: float) -> None:
        self.new_edge_passable_width = route_network.normalized_passable_width(width)

    def set_robot_pose(self, pose: tuple[float, float, float] | None) -> None:
        self.robot_pose = pose
        self.update()

    def set_graph(self, graph: RouteGraph) -> None:
        self.graph = graph
        self.selected_type = ""
        self.selected_id = None
        self.pending_node_id = None
        self.path_edge_ids = set()
        self.update()

    def set_mode(self, mode: str) -> None:
        self.mode = mode
        self.pending_node_id = None
        self.update()

    def set_display_options(
        self,
        *,
        show_nodes: bool | None = None,
        show_node_labels: bool | None = None,
        show_direction_arrows: bool | None = None,
    ) -> None:
        if show_nodes is not None:
            self.show_nodes = show_nodes
        if show_node_labels is not None:
            self.show_node_labels = show_node_labels
        if show_direction_arrows is not None:
            self.show_direction_arrows = show_direction_arrows
        self.update()

    def set_path_edges(self, edge_ids: list[int]) -> None:
        self.path_edge_ids = set(edge_ids)
        self.update()

    def set_issues(self, issues: list[ValidationIssue]) -> None:
        levels: dict[tuple[str, int], str] = {}
        for issue in issues:
            if issue.object_id is None or not issue.object_type:
                continue
            key = (issue.object_type, issue.object_id)
            current = levels.get(key)
            if issue.severity == "error" or current is None:
                levels[key] = issue.severity
        self.issue_target_levels = levels
        self.issue_targets = set(levels)
        self.update()
