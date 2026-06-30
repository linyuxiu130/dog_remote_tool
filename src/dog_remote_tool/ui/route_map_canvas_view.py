from __future__ import annotations

from PyQt5.QtCore import QPointF, QRectF, Qt


class RouteMapCanvasViewMixin:
    def reset_view(self) -> None:
        self.view_zoom = 1.0
        self.view_center_px = None
        self.panning = False
        self.pan_last_pos = None
        self.pan_button = None
        self.update()

    def zoom_at_widget_point(self, point, factor: float) -> None:
        if not self.pixmap or self.pixmap.isNull():
            return
        old_pixel = self._widget_to_pixel(point) or self._view_center()
        old_zoom = self.view_zoom
        self.view_zoom = max(self.min_zoom, min(self.max_zoom, self.view_zoom * factor))
        if abs(self.view_zoom - old_zoom) < 1e-6:
            return
        base = self._base_map_rect()
        if base.width() <= 0 or base.height() <= 0:
            return
        scale_x = base.width() * self.view_zoom / self.pixmap.width()
        scale_y = base.height() * self.view_zoom / self.pixmap.height()
        new_center = QPointF(
            old_pixel.x() - (point.x() - self.width() / 2) / scale_x,
            old_pixel.y() - (point.y() - self.height() / 2) / scale_y,
        )
        self.view_center_px = new_center
        self._clamp_view_center()
        self.update()

    def zoom_at_center(self, factor: float) -> None:
        self.zoom_at_widget_point(QPointF(self.width() / 2, self.height() / 2), factor)

    def pan_by_widget_delta(self, dx: float, dy: float) -> None:
        if not self.pixmap or self.pixmap.isNull():
            return
        target = self._map_rect()
        if target.width() <= 0 or target.height() <= 0:
            return
        center = self._view_center()
        self.view_center_px = QPointF(
            center.x() - dx * self.pixmap.width() / target.width(),
            center.y() - dy * self.pixmap.height() / target.height(),
        )
        self._clamp_view_center()
        self.update()

    def _screen_radius_to_world(self, pixels: int) -> float:
        if not self.pixmap or self.pixmap.isNull() or not self.map_metadata or self.map_metadata.resolution <= 0:
            return self.snap_distance
        target = self._map_rect()
        if target.width() <= 0 or target.height() <= 0:
            return self.snap_distance
        meters_per_widget_px_x = self.map_metadata.resolution * self.pixmap.width() / target.width()
        meters_per_widget_px_y = self.map_metadata.resolution * self.pixmap.height() / target.height()
        return max(self.snap_distance, max(meters_per_widget_px_x, meters_per_widget_px_y) * pixels)

    def _base_map_rect(self) -> QRectF:
        if not self.pixmap or self.pixmap.isNull():
            return QRectF(self.rect().adjusted(12, 12, -12, -12))
        scaled = self.pixmap.size()
        scaled.scale(self.size(), Qt.KeepAspectRatio)
        left = (self.width() - scaled.width()) / 2
        top = (self.height() - scaled.height()) / 2
        return QRectF(left, top, scaled.width(), scaled.height())

    def _map_rect(self) -> QRectF:
        if not self.pixmap or self.pixmap.isNull():
            return self._base_map_rect()
        base = self._base_map_rect()
        center = self._view_center()
        scale_x = base.width() * self.view_zoom / self.pixmap.width()
        scale_y = base.height() * self.view_zoom / self.pixmap.height()
        return QRectF(
            self.width() / 2 - center.x() * scale_x,
            self.height() / 2 - center.y() * scale_y,
            self.pixmap.width() * scale_x,
            self.pixmap.height() * scale_y,
        )

    def _view_center(self) -> QPointF:
        if not self.pixmap or self.pixmap.isNull():
            return QPointF(self.width() / 2, self.height() / 2)
        if self.view_center_px is None:
            return QPointF(self.pixmap.width() / 2, self.pixmap.height() / 2)
        return self.view_center_px

    def _clamp_view_center(self) -> None:
        if not self.pixmap or self.pixmap.isNull():
            self.view_center_px = None
            return
        if self.view_zoom <= self.min_zoom + 1e-6:
            self.view_zoom = self.min_zoom
            self.view_center_px = None
            return
        visible_w = self.pixmap.width() / self.view_zoom
        visible_h = self.pixmap.height() / self.view_zoom
        half_w = visible_w / 2
        half_h = visible_h / 2
        center = self._view_center()
        self.view_center_px = QPointF(
            max(half_w, min(self.pixmap.width() - half_w, center.x())),
            max(half_h, min(self.pixmap.height() - half_h, center.y())),
        )

    def _world_to_widget(self, x: float, y: float) -> QPointF | None:
        if not self.pixmap or not self.map_metadata or self.map_metadata.resolution <= 0:
            return None
        px, py = self.map_metadata.world_to_pixel(x, y, self.pixmap.height())
        target = self._map_rect()
        return QPointF(target.left() + px * target.width() / self.pixmap.width(), target.top() + py * target.height() / self.pixmap.height())

    def _widget_to_world(self, point) -> tuple[float, float] | None:
        pixel = self._widget_to_pixel(point)
        if pixel is None or not self.pixmap or not self.map_metadata or self.map_metadata.resolution <= 0:
            return None
        return self.map_metadata.pixel_to_world(pixel.x(), pixel.y(), self.pixmap.height())

    def _widget_to_pixel(self, point) -> QPointF | None:
        if not self.pixmap or not self.map_metadata or self.map_metadata.resolution <= 0:
            return None
        target = self._map_rect()
        if not target.contains(point):
            return None
        px = (point.x() - target.left()) * self.pixmap.width() / target.width()
        py = (point.y() - target.top()) * self.pixmap.height() / target.height()
        return QPointF(px, py)
