from __future__ import annotations

import math

from PyQt5.QtCore import QPointF


class NavigationMapViewMixin:
    def _marker_scale(self) -> float:
        return max(1.0, min(2.4, math.sqrt(max(1.0, self.zoom_scale))))

    def _target_rect(self):
        if not self.source_pixmap or self.source_pixmap.isNull():
            return self.rect()
        scale = self._image_scale()
        center_px = self._view_center_px()
        center = self._view_widget_center()
        width = self.source_pixmap.width() * scale
        height = self.source_pixmap.height() * scale
        left = center.x() - center_px[0] * scale
        top = center.y() - center_px[1] * scale
        return self.rect().adjusted(
            int(left),
            int(top),
            -(self.width() - int(left + width)),
            -(self.height() - int(top + height)),
        )

    def _image_scale(self) -> float:
        if not self.source_pixmap or self.source_pixmap.isNull():
            return 1.0
        fit = min(self.width() / max(1, self.source_pixmap.width()), self.height() / max(1, self.source_pixmap.height()))
        return max(0.001, fit * self.zoom_scale)

    def _view_center_px(self) -> tuple[float, float]:
        if not self.source_pixmap or self.source_pixmap.isNull():
            return (0.0, 0.0)
        center = self.view_center_px or (self.source_pixmap.width() / 2.0, self.source_pixmap.height() / 2.0)
        return self._clamp_center(center)

    def _view_widget_center(self) -> QPointF:
        center = self.rect().center()
        offset_x = float(getattr(self, "view_widget_offset_ratio_x", 0.0) or 0.0) * float(self.width())
        return QPointF(float(center.x()) + offset_x, float(center.y()))

    def _clamp_center(self, center: tuple[float, float]) -> tuple[float, float]:
        if not self.source_pixmap or self.source_pixmap.isNull():
            return center
        return (
            min(max(center[0], 0.0), float(self.source_pixmap.width())),
            min(max(center[1], 0.0), float(self.source_pixmap.height())),
        )

    def _widget_to_image(self, point) -> tuple[float, float] | None:
        if not self.source_pixmap or self.source_pixmap.isNull():
            return None
        scale = self._image_scale()
        center_px = self._view_center_px()
        center = self._view_widget_center()
        px = center_px[0] + (point.x() - center.x()) / scale
        py = center_px[1] + (point.y() - center.y()) / scale
        if px < 0 or py < 0 or px > self.source_pixmap.width() or py > self.source_pixmap.height():
            return None
        return float(px), float(py)

    def _zoom_around(self, point, image_point: tuple[float, float]) -> None:
        scale = self._image_scale()
        center = self._view_widget_center()
        center_px = (
            image_point[0] - (point.x() - center.x()) / scale,
            image_point[1] - (point.y() - center.y()) / scale,
        )
        self.view_center_px = self._clamp_center(center_px)

    def _pan_from_widget_delta(
        self,
        anchor_center_px: tuple[float, float],
        delta_x: float,
        delta_y: float,
    ) -> None:
        scale = self._image_scale()
        center_px = (
            anchor_center_px[0] - delta_x / scale,
            anchor_center_px[1] - delta_y / scale,
        )
        self.view_center_px = self._clamp_center(center_px)

    def _nearest_point_index_at_widget(self, point, max_distance_px: float = 28.0) -> int:
        nearest_index = -1
        nearest_distance = float("inf")
        for index, (x, y, _yaw) in enumerate(getattr(self, "points", []) or []):
            widget_point = self._world_to_widget(x, y)
            if widget_point is None:
                continue
            distance = math.hypot(widget_point.x() - point.x(), widget_point.y() - point.y())
            if distance < nearest_distance:
                nearest_distance = distance
                nearest_index = index
        return nearest_index if nearest_distance <= max_distance_px else -1

    def _world_to_widget(self, x: float, y: float) -> QPointF | None:
        image_point = self._world_to_image(x, y)
        if image_point is None:
            return None
        px, py = image_point
        scale = self._image_scale()
        center_px = self._view_center_px()
        center = self._view_widget_center()
        return QPointF(center.x() + (px - center_px[0]) * scale, center.y() + (py - center_px[1]) * scale)

    def _occupancy_at_widget(self, point) -> str:
        image_point = self._widget_to_image(point)
        if image_point is None:
            return "outside"
        return self._occupancy_at_image(*image_point)

    def _occupancy_at_image(self, px: float, py: float) -> str:
        if self.safety_mask is not None:
            return self.safety_mask.status_at_pixel(px, py)
        if self.source_image is None or self.source_image.isNull():
            return "unknown"
        ix = int(round(px))
        iy = int(round(py))
        if ix < 0 or iy < 0 or ix >= self.source_image.width() or iy >= self.source_image.height():
            return "outside"
        sample_radius = 1
        for sy in range(max(0, iy - sample_radius), min(self.source_image.height(), iy + sample_radius + 1)):
            for sx in range(max(0, ix - sample_radius), min(self.source_image.width(), ix + sample_radius + 1)):
                color = self.source_image.pixelColor(sx, sy)
                value = (color.red() + color.green() + color.blue()) / 3.0
                if value < 245:
                    return "blocked" if value < 100 else "unknown"
        return "free"

    def _occupancy_reject_message(self, occupancy: str) -> str:
        if occupancy == "outside":
            return "目标点未添加：点击位置不在地图范围内"
        if occupancy == "blocked":
            return "目标点未添加：点击位置在障碍区"
        if occupancy == "inflated":
            return "目标点未添加：点击位置在障碍/未知膨胀区内"
        return "目标点未添加：点击位置在未知/不可通行区域"

    def safety_status_at_world(self, x: float, y: float) -> str:
        image_point = self._world_to_image(x, y)
        if image_point is None:
            return "outside"
        return self._occupancy_at_image(*image_point)

    def _world_to_image(self, x: float, y: float) -> tuple[float, float] | None:
        if not self.source_pixmap or self.source_pixmap.isNull() or self.resolution <= 0:
            return None
        px = (x - self.origin[0]) / self.resolution
        py = self.source_pixmap.height() - (y - self.origin[1]) / self.resolution
        if px < 0 or py < 0 or px > self.source_pixmap.width() or py > self.source_pixmap.height():
            return None
        return float(px), float(py)

    def _widget_to_world(self, point) -> tuple[float, float] | None:
        if not self.source_pixmap or self.source_pixmap.isNull() or self.resolution <= 0:
            return None
        image_point = self._widget_to_image(point)
        if image_point is None:
            return None
        px, py = image_point
        x = self.origin[0] + px * self.resolution
        y = self.origin[1] + (self.source_pixmap.height() - py) * self.resolution
        return float(x), float(y)
