from __future__ import annotations

from dog_remote_tool.modules.navigation import route_network
from dog_remote_tool.modules.navigation.route_network import RouteEdge, RouteNode, node_coordinate_tuple
from . import route_map_canvas_geometry as _canvas_geometry


class RouteMapCanvasEditingMixin:
    def _move_dragging_node_to(self, x: float, y: float) -> None:
        if self.dragging_node_id is None or self.dragging_node_id not in self.graph.nodes:
            return
        if not self.drag_history_recorded:
            self.push_history("拖动节点")
            self.drag_history_recorded = True
        node = self.graph.nodes[self.dragging_node_id]
        node.x = x
        node.y = y
        for edge in self.graph.edges.values():
            if edge.startid == node.id and edge.coordinates:
                edge.coordinates[0] = node_coordinate_tuple(node)
            if edge.endid == node.id and edge.coordinates:
                edge.coordinates[-1] = node_coordinate_tuple(node)
        self.graph.dirty = True
        self.graph_changed.emit()

    def _add_node(self, x: float, y: float) -> None:
        snapped = self._nearest_node_at(x, y)
        if snapped is not None:
            self._select("node", snapped)
            return
        self.push_history("新增节点")
        node_id = self.graph.next_node_id()
        self.graph.nodes[node_id] = RouteNode(node_id, x, y, {"id": node_id})
        self.graph.dirty = True
        self._select("node", node_id)
        self.graph_changed.emit()

    def _edge_click(self, x: float, y: float) -> None:
        node_id = self._nearest_node_at(x, y)
        if node_id is None:
            self._add_node(x, y)
            node_id = self.selected_id
        if node_id is None:
            return
        if self.pending_node_id is None:
            self.pending_node_id = node_id
            self._select("node", node_id)
            return
        if self.pending_node_id == node_id:
            return
        start = self.graph.nodes[self.pending_node_id]
        end = self.graph.nodes[node_id]
        self.push_history("新增连边")
        edge_id = self.graph.next_edge_id()
        coords = [node_coordinate_tuple(start), node_coordinate_tuple(end)]
        passable_width = route_network.normalized_passable_width(
            getattr(self, "new_edge_passable_width", route_network.DEFAULT_ROUTE_PASSABLE_WIDTH)
        )
        self.graph.edges[edge_id] = RouteEdge(
            edge_id,
            start.id,
            end.id,
            coords,
            direction="both",
            cost=route_network.polyline_length(coords),
            properties={
                "id": edge_id,
                "startid": start.id,
                "endid": end.id,
                "direction": "both",
                "passable_width": passable_width,
            },
        )
        self.pending_node_id = node_id
        self.graph.dirty = True
        self._select("edge", edge_id)
        self.graph_changed.emit()

    def _delete_at(self, x: float, y: float) -> None:
        hit_type, hit_id = self._hit_test(x, y)
        if hit_type == "node" and hit_id is not None:
            self.push_history("删除节点")
            self.graph.nodes.pop(hit_id, None)
            for edge_id in [edge.id for edge in self.graph.edges.values() if edge.startid == hit_id or edge.endid == hit_id]:
                self.graph.edges.pop(edge_id, None)
            if self.pending_node_id == hit_id:
                self.pending_node_id = None
        elif hit_type == "edge" and hit_id is not None:
            self.push_history("删除连边")
            self.graph.edges.pop(hit_id, None)
        else:
            return
        self.graph.dirty = True
        self._select("", None)
        self.graph_changed.emit()

    def _select(self, object_type: str, object_id: int | None) -> None:
        self.selected_type = object_type
        self.selected_id = object_id
        self.selection_changed.emit(object_type, object_id or -1)
        self.update()

    def _hit_test(self, x: float, y: float) -> tuple[str, int | None]:
        node_id = self._nearest_node_at(x, y)
        if node_id is not None:
            return "node", node_id
        best_edge: int | None = None
        best_dist = self._screen_radius_to_world(self.edge_hit_pixels)
        for edge in self.graph.edges.values():
            dist = _canvas_geometry.point_to_polyline_distance(x, y, edge.coordinates)
            if dist <= best_dist:
                best_dist = dist
                best_edge = edge.id
        if best_edge is not None:
            return "edge", best_edge
        return "", None

    def _nearest_node_at(self, x: float, y: float) -> int | None:
        return route_network.nearest_node(self.graph, x, y, self._screen_radius_to_world(self.node_hit_pixels))
