from __future__ import annotations

from dog_remote_tool.modules.navigation import route_network


class RouteEditorToolsMixin:
    def manual_coordinate_values(self) -> tuple[float, float]:
        x_text = str(self.manual_route_x.text()).strip()
        y_text = str(self.manual_route_y.text()).strip()
        if not y_text:
            parts = [part for part in x_text.replace("，", ",").replace(",", " ").split() if part]
            if len(parts) >= 2:
                x_text, y_text = parts[0], parts[1]
        if not x_text or not y_text:
            raise ValueError("请输入 x 和 y 坐标")
        try:
            return float(x_text), float(y_text)
        except ValueError as exc:
            raise ValueError("坐标必须是数字，例如 2.806028840 -7.476321017") from exc

    def add_manual_coordinate_node(self) -> bool:
        try:
            x, y = self.manual_coordinate_values()
            self.canvas.push_history("按坐标添加节点")
            result = route_network.add_coordinate_route_node(
                self.canvas.graph,
                x,
                y,
                passable_width=getattr(self.canvas, "new_edge_passable_width", route_network.DEFAULT_ROUTE_PASSABLE_WIDTH),
            )
        except ValueError as exc:
            self.editor_status.setText(str(exc))
            return False
        self.canvas._select("node", result.node_id)
        self.on_graph_changed()
        self.editor_status.setText(
            f"已按坐标新增节点 {result.node_id}：x={x:.9f}, y={y:.9f}，"
            f"已自动连接最近节点 {result.connected_node_id}"
        )
        return True

    def auto_mark_crossing_points(self) -> bool:
        self.refresh_validation_highlights()
        if not any(issue.code == "crossing_edges" for issue in self.page.last_issues):
            self.editor_status.setText("没有需要补点的相交边")
            return False
        self.canvas.push_history("自动补交点")
        added_nodes, split_edges = route_network.split_crossing_edges(self.canvas.graph)
        if added_nodes == 0 and split_edges == 0:
            self.editor_status.setText("没有需要补点的相交边")
            self.refresh_validation_highlights()
            return False
        self.canvas._select("", None)
        self.on_graph_changed()
        self.editor_status.setText(f"已自动补交点：新增 {added_nodes} 点，生成 {split_edges} 段边")
        return True

    def auto_attach_isolated_nodes(self) -> bool:
        self.refresh_validation_highlights()
        if not any(issue.code == "isolated_node" for issue in self.page.last_issues):
            self.editor_status.setText("没有需要接入的孤立点")
            return False
        self.canvas.push_history("自动接孤立点")
        attached_nodes, created_edges = route_network.attach_isolated_nodes_to_edges(self.canvas.graph)
        if attached_nodes == 0 and created_edges == 0:
            self.editor_status.setText("没有可接入的孤立点")
            self.refresh_validation_highlights()
            return False
        self.canvas._select("", None)
        self.on_graph_changed()
        self.editor_status.setText(f"已自动接孤立点：接入 {attached_nodes} 点，新增 {created_edges} 条边")
        return True
