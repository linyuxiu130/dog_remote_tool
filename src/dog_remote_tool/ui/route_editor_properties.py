from __future__ import annotations

from PyQt5.QtWidgets import QMessageBox

from dog_remote_tool.modules.navigation import route_network
from dog_remote_tool.modules.navigation.route_network import node_coordinate_tuple


class RouteEditorPropertiesMixin:
    def _properties_update_locked(self) -> bool:
        try:
            return bool(getattr(self, "_updating_properties", False))
        except RuntimeError:
            return False

    def update_properties(self, object_type: str, object_id: int) -> None:
        self._updating_properties = True
        try:
            if object_type == "node" and object_id in self.canvas.graph.nodes:
                node = self.canvas.graph.nodes[object_id]
                self.editor_object_label.setText("节点")
                self.editor_object_id.setText(str(node.id))
                self.editor_node_x.setText(f"{node.x:.9f}")
                self.editor_node_y.setText(f"{node.y:.9f}")
                self.editor_node_x.setReadOnly(False)
                self.editor_node_y.setReadOnly(False)
                self.editor_edge_start.clear()
                self.editor_edge_end.clear()
                self.editor_direction_buttons.setEnabled(False)
                self.editor_passable_width.setEnabled(False)
                self.editor_passable_width.setValue(route_network.DEFAULT_ROUTE_PASSABLE_WIDTH)
                self.editor_road_class_buttons.setEnabled(False)
                self._set_road_class_buttons(route_network.DEFAULT_ROUTE_ROAD_CLASS)
                z_text = f"；z={node.z:.3f}" if node.z is not None else ""
                self.editor_metric.setText(f"节点位置可在上方 X/Y 修改{z_text}")
                self.editor_tabs.setCurrentIndex(0)
                return
            if object_type == "edge" and object_id in self.canvas.graph.edges:
                edge = self.canvas.graph.edges[object_id]
                self.editor_object_label.setText("边")
                self.editor_object_id.setText(str(edge.id))
                self.editor_node_x.clear()
                self.editor_node_y.clear()
                self.editor_node_x.setReadOnly(True)
                self.editor_node_y.setReadOnly(True)
                self.editor_edge_start.setText(str(edge.startid))
                self.editor_edge_end.setText(str(edge.endid))
                self.editor_direction_buttons.setEnabled(True)
                self._set_direction_buttons(edge.direction)
                self.editor_passable_width.setEnabled(True)
                self.editor_passable_width.setValue(route_network.edge_passable_width(edge))
                self.editor_road_class_buttons.setEnabled(True)
                self._set_road_class_buttons(route_network.edge_road_class(edge))
                self.editor_metric.setText(self._edge_metric_text(edge))
                self.editor_tabs.setCurrentIndex(0)
                return
            self.editor_object_label.setText("未选择")
            self.editor_object_id.clear()
            self.editor_node_x.clear()
            self.editor_node_y.clear()
            self.editor_edge_start.clear()
            self.editor_edge_end.clear()
            self.editor_direction_buttons.setEnabled(False)
            self.editor_passable_width.setEnabled(False)
            self.editor_passable_width.setValue(route_network.DEFAULT_ROUTE_PASSABLE_WIDTH)
            self.editor_road_class_buttons.setEnabled(False)
            self._set_road_class_buttons(route_network.DEFAULT_ROUTE_ROAD_CLASS)
            self.editor_metric.setText("--")
        finally:
            self._updating_properties = False

    def apply_object_changes(self) -> None:
        if self.canvas.selected_type == "node":
            self.apply_editor_node_coordinates()
            return
        if self.canvas.selected_type == "edge":
            self.apply_editor_edge_properties()

    def apply_editor_node_coordinates(self) -> None:
        if self._properties_update_locked():
            return
        object_id = self.canvas.selected_id
        if self.canvas.selected_type == "node" and object_id in self.canvas.graph.nodes:
            try:
                x = float(self.editor_node_x.text().strip())
                y = float(self.editor_node_y.text().strip())
            except ValueError:
                QMessageBox.information(self, "坐标无效", "请输入有效的 X/Y 数值。")
                return
            node = self.canvas.graph.nodes[object_id]
            if abs(node.x - x) <= 1e-9 and abs(node.y - y) <= 1e-9:
                return
            self.canvas.push_history("修改节点坐标")
            node.x = x
            node.y = y
            for edge in self.canvas.graph.edges.values():
                if edge.startid == node.id and edge.coordinates:
                    edge.coordinates[0] = node_coordinate_tuple(node)
                    edge.cost = edge.length()
                if edge.endid == node.id and edge.coordinates:
                    edge.coordinates[-1] = node_coordinate_tuple(node)
                    edge.cost = edge.length()
            self.on_graph_changed()
            self.update_properties("node", object_id)
            return

    def apply_editor_edge_properties(self) -> None:
        if self._properties_update_locked():
            return
        object_id = self.canvas.selected_id
        if self.canvas.selected_type == "edge" and object_id in self.canvas.graph.edges:
            edge = self.canvas.graph.edges[object_id]
            target = route_network.ROUTE_DIRECTION_BOTH if self.editor_direction_both.isChecked() else route_network.ROUTE_DIRECTION_FORWARD
            change = route_network.edge_direction_change(edge, target)
            width = route_network.normalized_passable_width(self.editor_passable_width.value())
            width_changed = abs(route_network.edge_passable_width(edge) - width) > 1e-6
            road_class = self._current_editor_road_class(edge)
            road_class_changed = route_network.edge_road_class(edge) != road_class
            if change == "none" and not width_changed and not road_class_changed:
                return
            self.canvas.push_history("修改连边属性")
            if change != "none":
                route_network.apply_edge_direction(edge, target)
                edge.cost = edge.length()
            if width_changed:
                route_network.set_edge_passable_width(edge, width)
            if road_class_changed:
                route_network.set_edge_road_class(edge, road_class)
            self.on_graph_changed()
            self.update_properties("edge", object_id)

    def apply_editor_passable_width(self, width: float | None = None) -> None:
        if self._properties_update_locked():
            return
        edge_id = self.canvas.selected_id
        if self.canvas.selected_type != "edge" or edge_id not in self.canvas.graph.edges:
            return
        edge = self.canvas.graph.edges[edge_id]
        value = self.editor_passable_width.value() if width is None else width
        normalized = route_network.normalized_passable_width(value)
        if abs(route_network.edge_passable_width(edge) - normalized) <= 1e-6:
            return
        self.canvas.push_history("修改连边属性")
        route_network.set_edge_passable_width(edge, normalized)
        self.editor_metric.setText(self._edge_metric_text(edge))
        self.on_graph_changed()

    def apply_editor_direction(self, direction: str) -> None:
        if self._properties_update_locked():
            return
        edge_id = self.canvas.selected_id
        if self.canvas.selected_type != "edge" or edge_id not in self.canvas.graph.edges:
            return
        edge = self.canvas.graph.edges[edge_id]
        change = route_network.edge_direction_change(edge, direction, toggle_forward=True)
        if change == "none":
            return
        self.canvas.push_history("切换单向方向" if change == "reverse" else "修改连边方向")
        route_network.apply_edge_direction(edge, direction, toggle_forward=True)
        if change == "reverse":
            self.editor_edge_start.setText(str(edge.startid))
            self.editor_edge_end.setText(str(edge.endid))
        self.editor_metric.setText(self._edge_metric_text(edge))
        self.on_graph_changed()

    def apply_editor_road_class(self, road_class: int) -> None:
        if self._properties_update_locked():
            return
        edge_id = self.canvas.selected_id
        if self.canvas.selected_type != "edge" or edge_id not in self.canvas.graph.edges:
            return
        edge = self.canvas.graph.edges[edge_id]
        normalized = route_network.normalized_road_class(road_class)
        if route_network.edge_road_class(edge) == normalized:
            return
        self.canvas.push_history("修改路网运动模式")
        route_network.set_edge_road_class(edge, normalized)
        self.editor_metric.setText(self._edge_metric_text(edge))
        self.on_graph_changed()

    def delete_selected(self) -> None:
        object_type = self.canvas.selected_type
        object_id = self.canvas.selected_id
        if object_type == "node" and object_id in self.canvas.graph.nodes:
            self.canvas.push_history("删除节点")
            self.canvas.graph.nodes.pop(object_id, None)
            for edge_id in [edge.id for edge in self.canvas.graph.edges.values() if edge.startid == object_id or edge.endid == object_id]:
                self.canvas.graph.edges.pop(edge_id, None)
        elif object_type == "edge" and object_id in self.canvas.graph.edges:
            self.canvas.push_history("删除连边")
            self.canvas.graph.edges.pop(object_id, None)
        else:
            return
        self.canvas._select("", None)
        self.on_graph_changed()

    def _set_direction_buttons(self, direction) -> None:
        self._updating_properties = True
        try:
            if route_network.normalized_direction(direction) == route_network.ROUTE_DIRECTION_BOTH:
                self.editor_direction_both.setChecked(True)
            else:
                self.editor_direction_forward.setChecked(True)
        finally:
            self._updating_properties = False

    def _edge_metric_text(self, edge) -> str:
        length = edge.length()
        road_class = route_network.road_class_label(route_network.edge_road_class(edge))
        return f"长度 {length:.2f} m；cost {edge.cost or length:.2f}；路宽 {route_network.edge_passable_width(edge):.2f} m；{road_class}"

    def _set_road_class_buttons(self, road_class: int) -> None:
        button = self.editor_road_class_buttons_by_value.get(route_network.road_class_mode_value(road_class))
        if button is not None:
            button.setChecked(True)

    def _current_editor_road_class(self, edge) -> int:
        try:
            group = getattr(self, "editor_road_class_group", None)
        except RuntimeError:
            group = None
        if group is None:
            return route_network.edge_road_class(edge)
        checked = group.checkedId()
        if checked < 0:
            return route_network.edge_road_class(edge)
        return route_network.normalized_road_class(checked)
