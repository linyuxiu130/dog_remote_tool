from __future__ import annotations

from pathlib import Path

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QDialog, QDialogButtonBox, QInputDialog, QLabel, QListWidget, QListWidgetItem, QVBoxLayout, QWidget

from dog_remote_tool.modules.navigation import route_history, route_network
from dog_remote_tool.ui.pages.navigation import point_text
from dog_remote_tool.ui.pages.navigation import point_text
from dog_remote_tool.ui.pages.navigation import route_target_geometry


class NavigationRouteHistoryMixin:
    def save_current_route_history(self, name: str | None = None) -> bool:
        remote_pgm = self.selected_map_pgm()
        node_ids = list(getattr(self, "route_target_node_ids", []) or [])
        if not remote_pgm:
            self.nav_status_note.setText("请先选择历史图，再保存路网路线")
            self.refresh_workspace_from_page()
            return False
        if not getattr(self, "route_target_mode", False) or not node_ids:
            self.nav_status_note.setText("请先进入路网导航并选择路网目标节点")
            self.refresh_workspace_from_page()
            return False
        if name is None:
            default_name = route_history.default_route_history_name()
            name, ok = QInputDialog.getText(self, "保存路网路线", "路线名称", text=default_name)
            if not ok:
                return False
        try:
            path = route_history.save_route_history(
                name=name or "",
                remote_pgm=remote_pgm,
                route_geojson_path=str(getattr(self, "route_graph_local_path", "") or self.selected_route_geojson_path()),
                node_ids=node_ids,
                waypoints_text=self.waypoints_text.toPlainText(),
            )
        except (OSError, ValueError) as exc:
            self.nav_status_note.setText(f"保存路网路线失败：{exc}")
            self.refresh_workspace_from_page()
            return False
        self.added_waypoint_undo_stack = []
        self.nav_status_note.setText(f"已保存路网路线：{path.name}")
        log = getattr(self, "_log_route_event", None)
        if callable(log):
            log(f"[路网] 已保存本地路线：{path}")
        self.refresh_workspace_from_page()
        return True

    def load_route_history(self, path: Path) -> bool:
        ensure_route_mode = getattr(self, "ensure_route_target_mode", None)
        if callable(ensure_route_mode):
            if not ensure_route_mode():
                return False
        elif not getattr(self, "route_target_mode", False):
            self.nav_status_note.setText("请先进入路网导航模式")
            self.refresh_workspace_from_page()
            return False
        graph = getattr(self, "route_graph", None)
        if graph is None:
            self.nav_status_note.setText("当前路网未加载，无法加载历史路线")
            self.refresh_workspace_from_page()
            return False
        try:
            data = route_history.read_route_history(path)
        except (OSError, ValueError) as exc:
            self.nav_status_note.setText(f"加载路网路线失败：{exc}")
            self.refresh_workspace_from_page()
            return False
        remote_pgm = self.selected_map_pgm()
        if data["remote_pgm"] != remote_pgm:
            self.nav_status_note.setText("该路线不属于当前历史图，已拒绝加载")
            self.refresh_workspace_from_page()
            return False
        missing = [node_id for node_id in data["node_ids"] if node_id not in graph.nodes]
        if missing:
            self.nav_status_note.setText(f"当前路网缺少历史路线节点：{', '.join(map(str, missing[:6]))}")
            self.refresh_workspace_from_page()
            return False
        self.route_target_node_ids = list(data["node_ids"])
        self.waypoints_text.setPlainText(
            NavigationRouteHistoryMixin._route_history_waypoints_text(self, graph, self.route_target_node_ids)
        )
        self.goal_point_selected = True
        self.added_waypoint_undo_stack = []
        points = point_text.visible_navigation_points(
            self.waypoints_text.toPlainText(),
            True,
            (float(self.goal_x.value()), float(self.goal_y.value()), float(self.goal_yaw.value())),
        )
        if points:
            set_goal = getattr(self, "set_goal_fields_from_point", None)
            if callable(set_goal):
                set_goal(*points[-1])
            else:
                x, y, yaw = points[-1]
                self.goal_x.setValue(x)
                self.goal_y.setValue(y)
                self.goal_yaw.setValue(yaw)
        update_points = getattr(self, "update_nav_map_points", None)
        if callable(update_points):
            update_points(selected_row=len(points) - 1 if points else None)
        else:
            self.nav_map.set_points(points)
            if callable(getattr(self.nav_map, "set_route_target_node_ids", None)):
                self.nav_map.set_route_target_node_ids(self.route_target_node_ids)
        self.nav_status_note.setText(f"已加载路网路线：{data['name']}，{len(points)} 个节点")
        log = getattr(self, "_log_route_event", None)
        if callable(log):
            log(f"[路网] 已加载本地路线：{path}")
        self.refresh_workspace_from_page()
        update_buttons = getattr(self, "update_navigation_action_buttons", None)
        if callable(update_buttons):
            update_buttons(getattr(self, "last_status_values", {}))
        return True

    def choose_route_history(self) -> bool:
        remote_pgm = self.selected_map_pgm()
        if not remote_pgm:
            self.nav_status_note.setText("请先选择历史图，再加载路网路线")
            self.refresh_workspace_from_page()
            return False
        entries = route_history.list_route_histories(remote_pgm)
        if not entries:
            self.nav_status_note.setText("当前历史图暂无本地路网路线")
            self.refresh_workspace_from_page()
            return False
        selected = NavigationRouteHistoryMixin._choose_route_history_entry(self, entries)
        if selected is None:
            return False
        return self.load_route_history(selected.path)

    def _choose_route_history_entry(self, entries: list[route_history.RouteHistoryEntry]):
        dialog = QDialog(self)
        dialog.setWindowTitle("加载路网路线")
        dialog.setMinimumWidth(460)
        dialog.resize(500, 360)
        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(22, 18, 22, 18)
        layout.setSpacing(12)
        title = QLabel("选择本地路线")
        title.setStyleSheet("font-weight: 800; color: #123d63;")
        layout.addWidget(title)

        route_list = QListWidget(dialog)
        route_list.setAlternatingRowColors(True)
        route_list.setMinimumHeight(180)
        route_list.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        route_list.setStyleSheet(
            "QListWidget{border:1px solid #d7e3f2;border-radius:7px;background:#ffffff;}"
            "QListWidget::item{padding:0;border-bottom:1px solid #edf2f7;}"
            "QListWidget::item:selected{background:#e7f1ff;color:#123d63;}"
        )
        for entry in entries:
            item = QListWidgetItem(entry.label())
            item.setData(Qt.UserRole, entry)
            route_list.addItem(item)
            item_widget = NavigationRouteHistoryMixin._route_history_entry_widget(entry)
            item.setSizeHint(item_widget.sizeHint())
            route_list.setItemWidget(item, item_widget)
        route_list.setCurrentRow(0)
        layout.addWidget(route_list)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel, dialog)
        ok_button = buttons.button(QDialogButtonBox.Ok)
        cancel_button = buttons.button(QDialogButtonBox.Cancel)
        if ok_button is not None:
            ok_button.setText("加载")
        if cancel_button is not None:
            cancel_button.setText("取消")
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        route_list.itemDoubleClicked.connect(lambda _item: dialog.accept())
        layout.addWidget(buttons)

        if dialog.exec_() != QDialog.Accepted:
            return None
        item = route_list.currentItem()
        if item is None:
            return None
        return item.data(Qt.UserRole)

    @staticmethod
    def _route_history_entry_widget(entry: route_history.RouteHistoryEntry) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(2)
        title = QLabel(entry.title_label())
        title.setStyleSheet("font-size: 12pt; font-weight: 800; color: #123d63;")
        title.setTextInteractionFlags(Qt.NoTextInteraction)
        meta = QLabel(entry.meta_label())
        meta.setStyleSheet("font-size: 10pt; color: #66788f;")
        meta.setTextInteractionFlags(Qt.NoTextInteraction)
        layout.addWidget(title)
        layout.addWidget(meta)
        return widget

    def _route_history_waypoints_text(self, graph: route_network.RouteGraph, node_ids: list[int]) -> str:
        lines = []
        for index, node_id in enumerate(node_ids):
            node = graph.nodes[node_id]
            if index + 1 < len(node_ids):
                yaw = route_target_geometry.route_path_start_yaw(graph, node_id, node_ids[index + 1])
            elif index > 0:
                yaw = route_target_geometry.route_path_yaw(graph, node_ids[index - 1], node_id)
            else:
                yaw = route_target_geometry.route_node_outgoing_yaw(graph, node_id)
            if yaw is None:
                yaw = self.current_direction_yaw() if callable(getattr(self, "current_direction_yaw", None)) else 0.0
            lines.append(point_text.format_waypoint_line(node.x, node.y, yaw))
        return "\n".join(lines)
