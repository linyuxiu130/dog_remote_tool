from __future__ import annotations

import math

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QColor, QImage, QPainter, QPixmap
from PyQt5.QtWidgets import QLabel

from dog_remote_tool.modules.navigation import route_network
from dog_remote_tool.ui.route_inflation_overlay import InflationOverlay, SafetyMask
from dog_remote_tool.ui.pages.navigation.map_drawing import NavigationMapDrawingMixin
from dog_remote_tool.ui.pages.navigation.map_history_card import NavigationMapHistoryCard as _NavigationMapHistoryCard
from dog_remote_tool.ui.pages.navigation.map_view import NavigationMapViewMixin


NavigationMapHistoryCard = _NavigationMapHistoryCard


class NavigationMapLabel(NavigationMapDrawingMixin, NavigationMapViewMixin, QLabel):
    point_clicked = pyqtSignal(float, float)
    point_rejected = pyqtSignal(str)
    point_delete_requested = pyqtSignal(int)
    direction_dragged = pyqtSignal(float)
    preview_requested = pyqtSignal()

    def __init__(self) -> None:
        super().__init__("选择历史图后加载预览")
        self.source_pixmap: QPixmap | None = None
        self.source_image: QImage | None = None
        self.safety_overlay: QPixmap | None = None
        self.safety_mask: SafetyMask | None = None
        self.safety_overlay_label = ""
        self.resolution = 0.0
        self.origin = (0.0, 0.0, 0.0)
        self.points: list[tuple[float, float, float]] = []
        self.charging_docks: list[tuple[int, float, float, float]] = []
        self.route_graph: route_network.RouteGraph | None = None
        self.route_target_node_ids: list[int] = []
        self.robot_pose: tuple[float, float, float] | None = None
        self.global_route: list[tuple[float, float, float]] = []
        self.realtime_plan: list[tuple[float, float, float]] = []
        self.obstacle_points: list[tuple[float, float]] = []
        self.drag_anchor: tuple[float, float] | None = None
        self.pan_anchor_pos = None
        self.pan_anchor_center_px: tuple[float, float] | None = None
        self.zoom_scale = 1.0
        self.view_center_px: tuple[float, float] | None = None
        self.view_widget_offset_ratio_x = 0.0
        self.setMinimumHeight(320)
        self.setAlignment(Qt.AlignCenter)
        self.setCursor(Qt.PointingHandCursor)
        self.setToolTip("左键添加目标并拖动设方向；滚轮缩放；中键或 Shift+左键拖动平移；右键删除目标点")
        self.setStyleSheet("background:#ffffff;border:1px solid #e3eaf3;border-radius:8px;color:#64748b;")

    def set_map(self, pixmap: QPixmap, resolution: float, origin: tuple[float, float, float]) -> None:
        self.source_pixmap = pixmap
        self.source_image = pixmap.toImage() if pixmap and not pixmap.isNull() else None
        self.resolution = resolution
        self.origin = origin
        self.zoom_scale = 1.0
        self.view_center_px = (pixmap.width() / 2.0, pixmap.height() / 2.0)
        self.view_widget_offset_ratio_x = 0.0
        self.setText("")
        self.update()

    def set_safety_overlay(self, overlay: InflationOverlay | None) -> None:
        self.safety_overlay = overlay.pixmap if overlay is not None else None
        self.safety_mask = overlay.safety_mask if overlay is not None else None
        self.safety_overlay_label = overlay.label if overlay is not None else ""
        self.update()

    def copy_safety_overlay_from(self, other: "NavigationMapLabel") -> None:
        self.safety_overlay = other.safety_overlay
        self.safety_mask = other.safety_mask
        self.safety_overlay_label = other.safety_overlay_label
        self.update()

    def clear_map(self, text: str = "选择历史图后加载预览") -> None:
        self.source_pixmap = None
        self.source_image = None
        self.safety_overlay = None
        self.safety_mask = None
        self.safety_overlay_label = ""
        self.resolution = 0.0
        self.origin = (0.0, 0.0, 0.0)
        self.view_center_px = None
        self.setPixmap(QPixmap())
        self.setText(text)
        self.update()

    def set_points(self, points: list[tuple[float, float, float]]) -> None:
        self.points = points
        self.update()

    def set_charging_docks(self, docks: list[tuple[int, float, float, float]]) -> None:
        self.charging_docks = list(docks)
        self.update()

    def set_route_graph(self, graph: route_network.RouteGraph | None) -> None:
        self.route_graph = graph
        self.update()

    def set_route_target_node_ids(self, node_ids: list[int]) -> None:
        self.route_target_node_ids = list(node_ids)
        self.update()

    def set_robot_pose(self, pose: tuple[float, float, float] | None) -> None:
        self.robot_pose = pose
        self.update()

    def set_global_route(self, points: list[tuple[float, float, float]]) -> None:
        self.global_route = points
        self.update()

    def set_realtime_plan(self, points: list[tuple[float, float, float]]) -> None:
        self.realtime_plan = points
        self.update()

    def set_obstacle_points(self, points: list[tuple[float, float]]) -> None:
        self.obstacle_points = list(points)
        self.update()

    def paintEvent(self, event) -> None:
        if not self.source_pixmap or self.source_pixmap.isNull():
            super().paintEvent(event)
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        target = self._target_rect()
        painter.drawPixmap(target, self.source_pixmap)
        if self.safety_overlay and not self.safety_overlay.isNull():
            painter.drawPixmap(target, self.safety_overlay)
        if len(self.global_route) >= 2:
            self._draw_polyline(painter, self.global_route, QColor("#2563eb"), 3)
        self._draw_route_graph(painter)
        self._draw_charging_docks(painter)
        self._draw_obstacle_points(painter)
        if self.points:
            marker_scale = self._marker_scale()
            for index, (x, y, _yaw) in enumerate(self.points, start=1):
                point = self._world_to_widget(x, y)
                if point is None:
                    continue
                self._draw_target_marker(painter, point, _yaw, index, marker_scale)
        if self.robot_pose:
            x, y, yaw = self.robot_pose
            point = self._world_to_widget(x, y)
            if point is not None:
                self._draw_robot_pose(painter, point, yaw)

    def _draw_obstacle_points(self, painter: QPainter) -> None:
        if not self.obstacle_points:
            return
        scale = self._marker_scale()
        radius = max(2.0, 2.4 * scale)
        painter.save()
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(239, 68, 68, 165))
        for x, y in self.obstacle_points:
            point = self._world_to_widget(x, y)
            if point is None:
                continue
            painter.drawEllipse(point, radius, radius)
        painter.restore()

    def wheelEvent(self, event) -> None:
        if not self.source_pixmap or self.source_pixmap.isNull():
            super().wheelEvent(event)
            return
        cursor_px = self._widget_to_image(event.pos())
        if cursor_px is None:
            cursor_px = self.view_center_px
        if cursor_px is None:
            event.accept()
            return
        steps = event.angleDelta().y() / 120.0
        if abs(steps) < 1e-6:
            event.accept()
            return
        old_scale = self.zoom_scale
        self.zoom_scale = max(1.0, min(8.0, self.zoom_scale * (1.18 ** steps)))
        if abs(self.zoom_scale - old_scale) > 1e-6:
            self._zoom_around(event.pos(), cursor_px)
            self.update()
        event.accept()

    def mousePressEvent(self, event) -> None:
        if not self.source_pixmap or self.source_pixmap.isNull() or self.resolution <= 0:
            return
        if event.button() == Qt.RightButton:
            index = self._nearest_point_index_at_widget(event.pos())
            if index >= 0:
                self.point_delete_requested.emit(index)
            event.accept()
            return
        if event.button() == Qt.MiddleButton or (
            event.button() == Qt.LeftButton and event.modifiers() & Qt.ShiftModifier
        ):
            self.drag_anchor = None
            self.pan_anchor_pos = event.pos()
            self.pan_anchor_center_px = self._view_center_px()
            self.setCursor(Qt.ClosedHandCursor)
            event.accept()
            return
        world = self._widget_to_world(event.pos())
        if world is None:
            return
        occupancy = self._occupancy_at_widget(event.pos())
        if occupancy != "free":
            self.drag_anchor = None
            self.point_rejected.emit(self._occupancy_reject_message(occupancy))
            event.accept()
            return
        self.drag_anchor = world
        self.point_clicked.emit(float(world[0]), float(world[1]))
        event.accept()

    def mouseMoveEvent(self, event) -> None:
        if self.pan_anchor_pos is not None and self.pan_anchor_center_px is not None:
            self._pan_from_widget_delta(
                self.pan_anchor_center_px,
                float(event.pos().x() - self.pan_anchor_pos.x()),
                float(event.pos().y() - self.pan_anchor_pos.y()),
            )
            self.update()
            event.accept()
            return
        if self.drag_anchor is None:
            return
        world = self._widget_to_world(event.pos())
        if world is None:
            return
        dx = world[0] - self.drag_anchor[0]
        dy = world[1] - self.drag_anchor[1]
        if abs(dx) < 1e-6 and abs(dy) < 1e-6:
            return
        self.direction_dragged.emit(float(math.atan2(dy, dx)))
        event.accept()

    def mouseReleaseEvent(self, event) -> None:
        if self.pan_anchor_pos is not None:
            self.pan_anchor_pos = None
            self.pan_anchor_center_px = None
            self.setCursor(Qt.PointingHandCursor)
            event.accept()
            return
        if self.drag_anchor is None:
            return
        world = self._widget_to_world(event.pos())
        if world is not None:
            dx = world[0] - self.drag_anchor[0]
            dy = world[1] - self.drag_anchor[1]
            if abs(dx) > 1e-6 or abs(dy) > 1e-6:
                self.direction_dragged.emit(float(math.atan2(dy, dx)))
        self.drag_anchor = None
        event.accept()
