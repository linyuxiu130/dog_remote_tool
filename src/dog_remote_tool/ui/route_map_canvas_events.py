from __future__ import annotations

from PyQt5.QtCore import QPointF, Qt


class RouteMapCanvasEventMixin:
    def mousePressEvent(self, event) -> None:
        self.setFocus()
        if event.button() == Qt.MiddleButton:
            self._begin_pan(event.pos(), event.button())
            event.accept()
            return
        if event.button() == Qt.LeftButton and self.space_pressed:
            self._begin_pan(event.pos(), event.button())
            event.accept()
            return
        if event.button() == Qt.RightButton:
            world = self._widget_to_world(event.pos())
            if world is None:
                return
            x, y = world
            if self.editing_enabled:
                self._delete_at(x, y)
                event.accept()
                return
            hit_type, hit_id = self._hit_test(x, y)
            self._select(hit_type, hit_id)
            event.accept()
            return
        if event.button() != Qt.LeftButton:
            return
        world = self._widget_to_world(event.pos())
        if world is None:
            return
        x, y = world
        self.point_picked.emit(x, y)
        if not self.editing_enabled:
            hit_type, hit_id = self._hit_test(x, y)
            self._select(hit_type, hit_id)
            return
        if self.mode == "node":
            self._add_node(x, y)
            return
        if self.mode == "edge":
            self._edge_click(x, y)
            return
        if self.mode == "delete":
            self._delete_at(x, y)
            return
        hit_type, hit_id = self._hit_test(x, y)
        if hit_type == "node" and hit_id is not None:
            self.dragging_node_id = hit_id
            self.drag_history_recorded = False
        self._select(hit_type, hit_id)

    def mouseMoveEvent(self, event) -> None:
        if self.panning and self.pan_last_pos is not None and self.pixmap and not self.pixmap.isNull():
            delta = QPointF(event.pos()) - self.pan_last_pos
            self.pan_last_pos = QPointF(event.pos())
            target = self._map_rect()
            if target.width() > 0 and target.height() > 0:
                center = self._view_center()
                center = QPointF(
                    center.x() - delta.x() * self.pixmap.width() / target.width(),
                    center.y() - delta.y() * self.pixmap.height() / target.height(),
                )
                self.view_center_px = center
                self._clamp_view_center()
                self.update()
            return
        world = self._widget_to_world(event.pos())
        if world is None:
            self.update()
            return
        x, y = world
        self.cursor_moved.emit(x, y)
        self._move_dragging_node_to(x, y)
        self.update()

    def mouseReleaseEvent(self, event) -> None:
        if self.panning and event.button() == self.pan_button:
            self._end_pan()
            event.accept()
            return
        self.dragging_node_id = None
        self.drag_history_recorded = False

    def wheelEvent(self, event) -> None:
        angle_delta = event.angleDelta()
        pixel_delta = event.pixelDelta() if callable(getattr(event, "pixelDelta", None)) else QPointF(0, 0)
        if event.modifiers() & Qt.ControlModifier:
            delta = angle_delta.y() or pixel_delta.y()
            if delta:
                self.zoom_at_widget_point(event.pos(), 1.18 if delta > 0 else 1 / 1.18)
                event.accept()
                return
        pixel_is_null = pixel_delta.isNull() if callable(getattr(pixel_delta, "isNull", None)) else not (pixel_delta.x() or pixel_delta.y())
        dx = pixel_delta.x() if not pixel_is_null else angle_delta.x() / 3
        dy = pixel_delta.y() if not pixel_is_null else angle_delta.y() / 3
        if dx or dy:
            if event.modifiers() & Qt.ShiftModifier and not dx:
                dx, dy = dy, 0
            self.pan_by_widget_delta(float(dx), float(dy))
            event.accept()
            return
        super().wheelEvent(event)

    def keyPressEvent(self, event) -> None:
        auto_repeat = bool(event.isAutoRepeat()) if callable(getattr(event, "isAutoRepeat", None)) else False
        if event.key() == Qt.Key_Space and not auto_repeat:
            self.space_pressed = True
            if not self.panning:
                self.setCursor(Qt.OpenHandCursor)
            event.accept()
            return
        key = event.key()
        pan_step = 120 if event.modifiers() & Qt.ShiftModifier else 56
        if key in (Qt.Key_Plus, Qt.Key_Equal):
            self.zoom_at_center(1.18)
            event.accept()
            return
        if key in (Qt.Key_Minus, Qt.Key_Underscore):
            self.zoom_at_center(1 / 1.18)
            event.accept()
            return
        if key in (Qt.Key_0, Qt.Key_Home):
            self.reset_view()
            event.accept()
            return
        if key in (Qt.Key_Left, Qt.Key_A):
            self.pan_by_widget_delta(pan_step, 0)
            event.accept()
            return
        if key in (Qt.Key_Right, Qt.Key_D):
            self.pan_by_widget_delta(-pan_step, 0)
            event.accept()
            return
        if key in (Qt.Key_Up, Qt.Key_W):
            self.pan_by_widget_delta(0, pan_step)
            event.accept()
            return
        if key in (Qt.Key_Down, Qt.Key_S):
            self.pan_by_widget_delta(0, -pan_step)
            event.accept()
            return
        super().keyPressEvent(event)

    def keyReleaseEvent(self, event) -> None:
        auto_repeat = bool(event.isAutoRepeat()) if callable(getattr(event, "isAutoRepeat", None)) else False
        if event.key() == Qt.Key_Space and not auto_repeat:
            self.space_pressed = False
            if not self.panning:
                self.unsetCursor()
            event.accept()
            return
        super().keyReleaseEvent(event)

    def enterEvent(self, event) -> None:
        self.setFocus()
        super().enterEvent(event)

    def _begin_pan(self, pos, button) -> None:
        self.panning = True
        self.pan_button = button
        self.pan_last_pos = QPointF(pos)
        self.setCursor(Qt.ClosedHandCursor)

    def _end_pan(self) -> None:
        self.panning = False
        self.pan_last_pos = None
        self.pan_button = None
        if self.space_pressed:
            self.setCursor(Qt.OpenHandCursor)
        else:
            self.unsetCursor()
