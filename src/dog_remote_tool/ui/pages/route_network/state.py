from __future__ import annotations

from pathlib import Path

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QPixmap
from PyQt5.QtWidgets import QFileDialog, QListWidgetItem, QMessageBox

from dog_remote_tool.modules.navigation import route_network
from dog_remote_tool.modules.navigation.route_network import RouteGraph, ValidationIssue
from dog_remote_tool.ui.route_editor_dialog import RouteEditorDialog
from dog_remote_tool.ui.pages.route_network.scale_status import RouteNetworkScaleStatusMixin
from dog_remote_tool.ui.pages.route_network.state_helpers import (
    default_local_geojson_path,
    path_preview_text,
    route_object_properties,
)


class RouteNetworkStateMixin(RouteNetworkScaleStatusMixin):
    def set_tool(self, mode: str) -> None:
        self.current_tool = mode
        for key, button in self.tool_buttons.items():
            button.setChecked(key == mode)
        self.canvas.set_mode(mode)
        self.update_tool_hint()

    def new_route_for_selected_history(self) -> bool:
        if not self.ensure_selected_history_preview("new"):
            return False
        self.start_new_history_route(open_editor=True)
        return True

    def start_new_history_route(self, open_editor: bool = False) -> None:
        self.new_graph()
        if open_editor:
            self.open_route_editor()

    def open_map(self) -> None:
        path, _filter = QFileDialog.getOpenFileName(self, "选择 map.yaml", str(Path.home()), "Map YAML (map.yaml *.yaml *.yml)")
        if not path:
            return
        self.load_map(path)

    def load_map(self, yaml_path: str) -> bool:
        try:
            metadata = route_network.read_map_yaml(yaml_path)
            pixmap = QPixmap(str(metadata.image_path))
        except Exception as exc:
            QMessageBox.warning(self, "底图加载失败", str(exc))
            return False
        if pixmap.isNull():
            QMessageBox.warning(self, "底图加载失败", f"无法打开图像：{metadata.image_path}")
            return False
        self.map_metadata = metadata
        self.map_path.setText(str(yaml_path))
        self.canvas.set_map(pixmap, metadata)
        overlay = self.create_current_inflation_overlay(metadata)
        if overlay is not None:
            self.canvas.set_inflation_overlay(overlay.pixmap, overlay.label)
        else:
            self.canvas.set_inflation_overlay(None, "")
        self.update_scale_info()
        self.set_status("底图已加载", "ready")
        return True

    def open_geojson(self) -> None:
        path, _filter = QFileDialog.getOpenFileName(self, "选择 map.geojson", str(Path.home()), "GeoJSON (*.geojson *.json)")
        if not path:
            return
        self.load_geojson(path)

    def load_geojson(self, path: str) -> bool:
        try:
            self.graph = route_network.load_geojson(path)
        except Exception as exc:
            QMessageBox.warning(self, "路网加载失败", str(exc))
            return False
        self.geojson_path.setText(path)
        self.canvas.set_graph(self.graph)
        self.validate_graph(show_message=False)
        self.update_scale_info()
        return True

    def new_graph(self) -> None:
        self.graph = RouteGraph()
        self.canvas.set_graph(self.graph)
        self.geojson_path.setText(str(self.default_local_geojson_path()))
        self.issue_list.clear()
        self.issue_summary.setText("空路网")
        self.canvas.set_issues([])
        self.update_scale_info()
        self.set_status("新建路网", "ready")

    def default_local_geojson_path(self) -> Path:
        return default_local_geojson_path(self.map_path.text(), Path.home())

    def save_routes_remotely_by_default(self) -> bool:
        return bool(self.selected_history_map_pgm() and self.remote_route_path.text().strip())

    def save_geojson(self, *, notify_saved: bool = True) -> bool:
        path = self.geojson_path.text().strip()
        if not path:
            path, _filter = QFileDialog.getSaveFileName(self, "保存 map.geojson", str(self.default_local_geojson_path()), "GeoJSON (*.geojson)")
            if not path:
                return False
        self.graph = self.canvas.graph
        route_network.save_geojson(self.graph, path)
        self.geojson_path.setText(path)
        if notify_saved:
            self.set_status("已保存", "success")
            self.notify_route_saved(path)
        else:
            self.set_status("准备上传", "warning")
        return True

    def notify_route_saved(self, path: str | None = None) -> bool:
        callback = getattr(self, "route_saved_callback", None)
        if callable(callback):
            callback(self.selected_history_map_pgm(), path or self.geojson_path.text().strip())
            return True
        return False

    def validate_graph(self, show_message: bool = True) -> bool:
        image_size = None
        if self.canvas.pixmap and not self.canvas.pixmap.isNull():
            image_size = (self.canvas.pixmap.width(), self.canvas.pixmap.height())
        self.graph = self.canvas.graph
        self.last_issues = route_network.validate_graph(self.graph, self.map_metadata, image_size)
        self.canvas.set_issues(self.last_issues)
        self.issue_list.clear()
        errors = sum(1 for issue in self.last_issues if issue.severity == "error")
        warnings = sum(1 for issue in self.last_issues if issue.severity == "warning")
        for issue in self.last_issues:
            item = QListWidgetItem(f"{'错误' if issue.severity == 'error' else '警告'} · {issue.message}")
            item.setData(Qt.UserRole, issue)
            self.issue_list.addItem(item)
        if not self.last_issues:
            self.issue_summary.setText("校验通过")
            self.set_status("校验通过", "success")
        else:
            self.issue_summary.setText(f"错误 {errors}，警告 {warnings}")
            self.set_status(f"错误 {errors} / 警告 {warnings}", "error" if errors else "warning")
            self.inspector_tabs.setCurrentWidget(self.issue_tab)
        self.update_scale_info()
        if show_message and errors:
            details = "\n".join(
                f"- {issue.message}" for issue in self.last_issues if issue.severity == "error"
            )
            QMessageBox.information(
                self,
                "校验未通过",
                f"存在 {errors} 个路网错误，需修复后才能上传远端。\n\n{details}",
            )
        return errors == 0

    def preview_path(self) -> None:
        try:
            start_id = int(self.start_node.text().strip())
            goal_id = int(self.goal_node.text().strip())
        except ValueError:
            QMessageBox.information(self, "节点 ID 无效", "请输入起点和终点节点 ID。")
            return
        result = route_network.shortest_path(self.canvas.graph, start_id, goal_id)
        self.canvas.set_path_edges(result.edge_ids)
        self.inspector_tabs.setCurrentIndex(1)
        text, state = path_preview_text(result)
        self.preview_result.setText(text)
        self.set_status("路径可达" if result.reachable else "路径不可达", state)

    def update_properties(self, object_type: str, object_id: int) -> None:
        properties = route_object_properties(self.canvas.graph, object_type, object_id)
        if properties is not None:
            self.object_label.setText(properties.object_type)
            self.object_id.setText(properties.object_id)
            self.object_start.setText(properties.start)
            self.object_end.setText(properties.end)
            self.object_direction_buttons.setEnabled(properties.direction_enabled)
            self.object_passable_width.blockSignals(True)
            try:
                self.object_passable_width.setEnabled(properties.passable_width is not None)
                self.object_passable_width.setValue(properties.passable_width or route_network.DEFAULT_ROUTE_PASSABLE_WIDTH)
            finally:
                self.object_passable_width.blockSignals(False)
            self.object_road_class_buttons.blockSignals(True)
            try:
                self.object_road_class_buttons.setEnabled(properties.road_class is not None)
                self._set_road_class_buttons(properties.road_class or route_network.DEFAULT_ROUTE_ROAD_CLASS)
            finally:
                self.object_road_class_buttons.blockSignals(False)
            if properties.direction is not None:
                self._set_direction_buttons(properties.direction)
            self.object_metric.setText(properties.metric)
            self.inspector_tabs.setCurrentIndex(0)
            return
        self.object_label.setText("未选择")
        self.object_id.clear()
        self.object_start.clear()
        self.object_end.clear()
        self.object_direction_buttons.setEnabled(False)
        self.object_passable_width.blockSignals(True)
        try:
            self.object_passable_width.setEnabled(False)
            self.object_passable_width.setValue(route_network.DEFAULT_ROUTE_PASSABLE_WIDTH)
        finally:
            self.object_passable_width.blockSignals(False)
        self.object_road_class_buttons.blockSignals(True)
        try:
            self.object_road_class_buttons.setEnabled(False)
            self._set_road_class_buttons(route_network.DEFAULT_ROUTE_ROAD_CLASS)
        finally:
            self.object_road_class_buttons.blockSignals(False)
        self.object_metric.setText("--")

    def apply_direction(self, direction: str) -> None:
        if self._updating_properties:
            return
        edge_id = self.canvas.selected_id
        if self.canvas.selected_type != "edge" or edge_id not in self.canvas.graph.edges:
            return
        edge = self.canvas.graph.edges[edge_id]
        change = route_network.edge_direction_change(edge, direction, toggle_forward=True)
        if change == "none":
            return
        if callable(getattr(self.canvas, "push_history", None)):
            self.canvas.push_history("切换单向方向" if change == "reverse" else "修改连边方向")
        route_network.apply_edge_direction(edge, direction, toggle_forward=True)
        if change == "reverse":
            try:
                object_start = self.object_start
                object_end = self.object_end
            except (AttributeError, RuntimeError):
                object_start = None
                object_end = None
            if callable(getattr(object_start, "setText", None)):
                object_start.setText(str(edge.startid))
            if callable(getattr(object_end, "setText", None)):
                object_end.setText(str(edge.endid))
        self.canvas.graph.dirty = True
        self.canvas.update()
        try:
            object_metric = self.object_metric
        except (AttributeError, RuntimeError):
            object_metric = None
        if callable(getattr(object_metric, "setText", None)):
            object_metric.setText(self._edge_metric_text(edge))

    def apply_passable_width(self, width: float) -> None:
        if self._updating_properties:
            return
        edge_id = self.canvas.selected_id
        if self.canvas.selected_type != "edge" or edge_id not in self.canvas.graph.edges:
            return
        edge = self.canvas.graph.edges[edge_id]
        current = route_network.edge_passable_width(edge)
        normalized = route_network.normalized_passable_width(width)
        if abs(current - normalized) <= 1e-6:
            return
        if callable(getattr(self.canvas, "push_history", None)):
            self.canvas.push_history("修改路网通行宽度")
        route_network.set_edge_passable_width(edge, normalized)
        self.canvas.graph.dirty = True
        self.canvas.update()
        self.object_metric.setText(self._edge_metric_text(edge))
        self.on_graph_changed()

    def apply_road_class(self, road_class: int | None = None) -> None:
        if self._updating_properties:
            return
        edge_id = self.canvas.selected_id
        if self.canvas.selected_type != "edge" or edge_id not in self.canvas.graph.edges:
            return
        edge = self.canvas.graph.edges[edge_id]
        selected = self.object_road_class_group.checkedId() if road_class is None else road_class
        normalized = route_network.normalized_road_class(selected)
        if route_network.edge_road_class(edge) == normalized:
            return
        if callable(getattr(self.canvas, "push_history", None)):
            self.canvas.push_history("修改路网运动模式")
        route_network.set_edge_road_class(edge, normalized)
        self.canvas.graph.dirty = True
        self.canvas.update()
        self.object_metric.setText(self._edge_metric_text(edge))
        self.on_graph_changed()

    def _edge_metric_text(self, edge) -> str:
        length = edge.length()
        road_class = route_network.road_class_label(route_network.edge_road_class(edge))
        return f"长度 {length:.2f} m；cost {edge.cost or length:.2f}；路宽 {route_network.edge_passable_width(edge):.2f} m；{road_class}"

    def _set_road_class_buttons(self, road_class: int) -> None:
        button = self.object_road_class_buttons_by_value.get(route_network.road_class_mode_value(road_class))
        if button is not None:
            button.setChecked(True)

    def _set_direction_buttons(self, direction) -> None:
        self._updating_properties = True
        try:
            if route_network.normalized_direction(direction) == route_network.ROUTE_DIRECTION_BOTH:
                self.object_direction_both.setChecked(True)
            else:
                self.object_direction_forward.setChecked(True)
        finally:
            self._updating_properties = False

    def focus_issue(self, item: QListWidgetItem) -> None:
        issue = item.data(Qt.UserRole)
        if isinstance(issue, ValidationIssue) and issue.object_id is not None:
            self.canvas.selected_type = issue.object_type
            self.canvas.selected_id = issue.object_id
            self.update_properties(issue.object_type, issue.object_id)
            self.canvas.update()

    def on_graph_changed(self) -> None:
        self.update_scale_info()
        self.set_status("未保存修改", "warning")

    def on_point_picked(self, x: float, y: float) -> None:
        self.cursor_label.setText(f"点击：x={x:.3f}, y={y:.3f}")
        if not self.canvas.editing_enabled:
            self.open_route_editor()

    def use_selected_node(self, target: str) -> None:
        node_id = self.canvas.selected_id
        if self.canvas.selected_type != "node" or node_id not in self.canvas.graph.nodes:
            QMessageBox.information(self, "未选择节点", "请先在画布上选择一个节点。")
            return
        if target == "start":
            self.start_node.setText(str(node_id))
            self.preview_result.setText(f"起点已设为节点 {node_id}")
        else:
            self.goal_node.setText(str(node_id))
            self.preview_result.setText(f"终点已设为节点 {node_id}")
        self.inspector_tabs.setCurrentIndex(1)

    def on_cursor_moved(self, x: float, y: float) -> None:
        self.cursor_label.setText(f"坐标：x={x:.3f}, y={y:.3f}")

    def open_route_editor(self) -> None:
        if self._opening_editor:
            return
        if not self.canvas.pixmap or self.canvas.pixmap.isNull() or not self.map_metadata:
            if self.selected_history_map_pgm():
                if not self.ensure_selected_history_preview("edit"):
                    return
            if not self.canvas.pixmap or self.canvas.pixmap.isNull() or not self.map_metadata:
                QMessageBox.information(self, "未加载底图", "请先打开 map.yaml，再进入路网编辑。")
                return
        self._opening_editor = True
        try:
            try:
                dialog = RouteEditorDialog(self)
            except Exception as exc:
                self.set_status("编辑器打开失败", "error")
                callback = getattr(self, "route_editor_status_callback", None)
                if callable(callback):
                    callback(f"编辑器打开失败：{exc}", "error")
                else:
                    QMessageBox.warning(self, "编辑器打开失败", str(exc))
                return
            self.active_editor_dialog = dialog
            dialog.showFullScreen()
            dialog.raise_()
            dialog.activateWindow()
            dialog.exec_()
            self.canvas.editing_enabled = False
            self.canvas.set_display_options(show_nodes=False, show_node_labels=False, show_direction_arrows=False)
            self.canvas.hover_text = "点击地图打开全屏编辑器"
            self.update_scale_info()
            self.update_tool_hint()
        finally:
            self.active_editor_dialog = None
            self._opening_editor = False

    def update_tool_hint(self) -> None:
        if not self.canvas.editing_enabled:
            self.tool_hint_label.setText("预览：点击地图进入全屏编辑；方向键/WASD 平移，+/- 缩放")
            return
        hints = {
            "select": "选取/移动：点击点或边查看属性；方向键/WASD 平移，+/- 缩放",
            "node": "添加节点：点击底图空白处创建节点；靠近已有点会自动选中已有点",
            "edge": "加点连线：左键加点/连线；方向键/WASD 平移，+/- 缩放",
            "delete": "删除对象：右键也可直接删除命中的点或边",
        }
        self.tool_hint_label.setText(hints.get(self.current_tool, "选择：点击对象查看属性"))
