from __future__ import annotations

import math

from PyQt5.QtCore import QSignalBlocker, Qt
from PyQt5.QtWidgets import QFrame, QHBoxLayout, QLabel, QTableWidgetItem, QWidget


class NavigationWorkspacePointsMixin:
    def refresh_point_list(self) -> None:
        points = self.page.visible_navigation_points()
        current = self.selected_point_index()
        columns = self.point_table_columns
        table_rows = math.ceil(len(points) / columns)
        with QSignalBlocker(self.point_table):
            self.point_table.setRowCount(0)
            self.point_table.setColumnCount(columns)
            self.point_table.setRowCount(table_rows)
            for index, (x, y, yaw) in enumerate(points):
                row = index // columns
                column = index % columns
                if getattr(self.page, "route_target_mode", False):
                    text = f"路网节点 ({x:.1f},{y:.1f}) {math.degrees(yaw):.0f}°"
                else:
                    text = f"({x:.1f},{y:.1f},{math.degrees(yaw):.0f}°)"
                item = QTableWidgetItem("")
                item.setFlags(item.flags() & ~Qt.ItemIsEditable)
                item.setToolTip(f"{index + 1} {text}")
                item.setData(Qt.UserRole, text)
                self.point_table.setItem(row, column, item)
                self.point_table.setCellWidget(row, column, self._waypoint_cell(index + 1, text, False))
            for column in range(columns):
                self.point_table.setColumnWidth(column, max(176, self.point_table.viewport().width() // columns - 2))
            for row in range(table_rows):
                self.point_table.setRowHeight(row, 32)
            if points:
                selected = min(max(current, 0), len(points) - 1)
                self.point_table.setCurrentCell(selected // columns, selected % columns)
        self.update_point_selection_styles()
        self.delete_selected_point.setEnabled(bool(points) and self.selected_point_index() >= 0)

    def _waypoint_cell(self, index: int, text: str, selected: bool) -> QWidget:
        cell = QFrame()
        cell.setObjectName("WaypointCell")
        cell.setProperty("selected", "true" if selected else "false")
        cell.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        layout = QHBoxLayout(cell)
        layout.setContentsMargins(4, 0, 4, 0)
        layout.setSpacing(3)
        index_label = QLabel(str(index))
        index_label.setObjectName("WaypointIndex")
        index_label.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        index_label.setFixedWidth(14)
        index_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        value_label = QLabel(text)
        value_label.setObjectName("WaypointValue")
        value_label.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        value_label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        layout.addWidget(index_label)
        layout.addWidget(value_label, 1)
        return cell

    def on_point_table_selection_changed(self, row: int, column: int) -> None:
        self.delete_selected_point.setEnabled(row >= 0 and column >= 0 and bool(self.page.visible_navigation_points()))
        self.update_point_selection_styles()

    def update_point_selection_styles(self) -> None:
        selected = self.selected_point_index()
        columns = self.point_table_columns
        points = self.page.visible_navigation_points()
        for index, (_x, _y, _yaw) in enumerate(points):
            widget = self.point_table.cellWidget(index // columns, index % columns)
            if widget is None:
                continue
            widget.setProperty("selected", "true" if index == selected else "false")
            widget.style().unpolish(widget)
            widget.style().polish(widget)

    def selected_point_index(self) -> int:
        row = self.point_table.currentRow()
        column = self.point_table.currentColumn()
        if row < 0 or column < 0:
            return -1
        index = row * self.point_table_columns + column
        return index if index < len(self.page.visible_navigation_points()) else -1
