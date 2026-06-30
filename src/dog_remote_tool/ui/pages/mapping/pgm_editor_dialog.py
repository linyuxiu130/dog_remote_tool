from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from PyQt5.QtCore import QEvent, QPoint, QTimer, Qt, pyqtSignal
from PyQt5.QtGui import QColor, QImage, QKeySequence, QPainter, QPen, QPixmap
from PyQt5.QtWidgets import (
    QButtonGroup,
    QDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QShortcut,
    QSlider,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from dog_remote_tool.modules.mapping import pgm_editor


MODE_LABELS = {
    pgm_editor.BRUSH_OBSTACLE: "画障碍",
    pgm_editor.BRUSH_ERASE: "画可通行",
    pgm_editor.BRUSH_UNKNOWN: "画未知区域",
    pgm_editor.BRUSH_RESTORE: "恢复原图",
}


class _PaintLabel(QLabel):
    def __init__(self) -> None:
        super().__init__()
        self.brush_pos: QPoint | None = None
        self.brush_radius = 8
        self.brush_scale = 1.0
        self.brush_mode = pgm_editor.BRUSH_ERASE
        self.setAlignment(Qt.AlignCenter)
        self.setMouseTracking(True)

    def paintEvent(self, event) -> None:
        super().paintEvent(event)
        if self.brush_pos is None:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        pen = QPen(self._brush_preview_color())
        pen.setWidth(2)
        painter.setPen(pen)
        radius = max(2, int(round(self.brush_radius * self.brush_scale)))
        painter.drawEllipse(self.brush_pos, radius, radius)

    def _brush_preview_color(self):
        color = {
            pgm_editor.BRUSH_OBSTACLE: Qt.red,
            pgm_editor.BRUSH_ERASE: Qt.blue,
            pgm_editor.BRUSH_UNKNOWN: QColor(245, 158, 11),
            pgm_editor.BRUSH_RESTORE: Qt.darkGreen,
        }.get(self.brush_mode, Qt.blue)
        return color


class PgmEditorCanvas(QScrollArea):
    stroke_started = pyqtSignal()
    stroke_finished = pyqtSignal()
    stroke_requested = pyqtSignal(tuple, tuple)
    brush_wheel_requested = pyqtSignal(int)

    def __init__(self, pixmap: QPixmap, zoom_label: QLabel, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.source_pixmap = pixmap
        self.zoom_label = zoom_label
        self.scale = 1.0
        self.space_down = False
        self.dragging = False
        self.painting = False
        self.drag_start = QPoint()
        self.drag_h_value = 0
        self.drag_v_value = 0
        self.last_image_point: tuple[float, float] | None = None
        self.image_label = _PaintLabel()
        self.image_label.installEventFilter(self)
        self.viewport().installEventFilter(self)
        self.setObjectName("DialogScroll")
        self.setWidgetResizable(False)
        self.setAlignment(Qt.AlignCenter)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setWidget(self.image_label)

    def set_brush(self, radius: int, mode: str) -> None:
        self.image_label.brush_radius = radius
        self.image_label.brush_mode = mode
        self.image_label.update()

    def set_source_pixmap(self, pixmap: QPixmap) -> None:
        self.source_pixmap = pixmap
        self._render_scaled()

    def fit_to_view(self) -> None:
        viewport = self.viewport().size()
        if viewport.width() <= 1 or viewport.height() <= 1:
            return
        scale_x = max(0.01, (viewport.width() - 10) / max(1, self.source_pixmap.width()))
        scale_y = max(0.01, (viewport.height() - 10) / max(1, self.source_pixmap.height()))
        self.set_scale(min(scale_x, scale_y), center=True, fit_label=True)

    def zoom_by(self, factor: float, anchor: QPoint | None = None) -> None:
        self.set_scale(self.scale * factor, anchor=anchor)

    def zoom_at_center(self, factor: float) -> None:
        self.zoom_by(factor)

    def reset_view(self) -> None:
        self.fit_to_view()

    def pan_by_widget_delta(self, dx: float, dy: float) -> None:
        self.horizontalScrollBar().setValue(self.horizontalScrollBar().value() + int(round(dx)))
        self.verticalScrollBar().setValue(self.verticalScrollBar().value() + int(round(dy)))

    def set_scale(
        self,
        scale: float,
        *,
        anchor: QPoint | None = None,
        center: bool = False,
        fit_label: bool = False,
    ) -> None:
        old_width = max(1, self.image_label.width())
        old_height = max(1, self.image_label.height())
        viewport_anchor = anchor or QPoint(self.viewport().width() // 2, self.viewport().height() // 2)
        image_x = (self.horizontalScrollBar().value() + viewport_anchor.x()) / old_width
        image_y = (self.verticalScrollBar().value() + viewport_anchor.y()) / old_height
        self.scale = max(0.05, min(16.0, scale))
        self._render_scaled(fit_label=fit_label)
        if center:
            self.horizontalScrollBar().setValue(max(0, (self.image_label.width() - self.viewport().width()) // 2))
            self.verticalScrollBar().setValue(max(0, (self.image_label.height() - self.viewport().height()) // 2))
            return
        self.horizontalScrollBar().setValue(int(image_x * self.image_label.width() - viewport_anchor.x()))
        self.verticalScrollBar().setValue(int(image_y * self.image_label.height() - viewport_anchor.y()))

    def _render_scaled(self, *, fit_label: bool = False) -> None:
        width = max(1, int(self.source_pixmap.width() * self.scale))
        height = max(1, int(self.source_pixmap.height() * self.scale))
        scaled = self.source_pixmap.scaled(width, height, Qt.KeepAspectRatio, Qt.FastTransformation)
        self.image_label.setPixmap(scaled)
        self.image_label.resize(scaled.size())
        self.image_label.brush_scale = self.scale
        prefix = "适配 " if fit_label else ""
        self.zoom_label.setText(f"{prefix}{max(1, int(round(self.scale * 100)))}%")

    def _event_label_pos(self, obj, event) -> QPoint:
        if obj is self.image_label:
            return event.pos()
        return self.image_label.mapFromGlobal(event.globalPos())

    def _label_to_image(self, point: QPoint) -> tuple[float, float] | None:
        if self.scale <= 0 or not self.image_label.rect().contains(point):
            return None
        x = point.x() / self.scale
        y = point.y() / self.scale
        if x < 0 or y < 0 or x >= self.source_pixmap.width() or y >= self.source_pixmap.height():
            return None
        return x, y

    def _refresh_cursor(self) -> None:
        if self.painting:
            cursor = Qt.CrossCursor
        elif self.dragging:
            cursor = Qt.ClosedHandCursor
        elif self.space_down:
            cursor = Qt.OpenHandCursor
        else:
            cursor = Qt.CrossCursor
        self.viewport().setCursor(cursor)
        self.image_label.setCursor(cursor)

    def _clear_brush_preview(self) -> None:
        if self.image_label.brush_pos is None:
            return
        self.image_label.brush_pos = None
        self.image_label.update()

    def eventFilter(self, obj, event) -> bool:
        auto_repeat = bool(event.isAutoRepeat()) if callable(getattr(event, "isAutoRepeat", None)) else False
        if event.type() == QEvent.KeyPress and event.key() == Qt.Key_Space and not auto_repeat:
            self.space_down = True
            self._clear_brush_preview()
            self._refresh_cursor()
            return True
        if event.type() == QEvent.KeyRelease and event.key() == Qt.Key_Space and not auto_repeat:
            self.space_down = False
            self.dragging = False
            self._refresh_cursor()
            return True
        if event.type() == QEvent.KeyPress:
            key = event.key()
            pan_step = 120 if event.modifiers() & Qt.ShiftModifier else 56
            if key in (Qt.Key_Plus, Qt.Key_Equal):
                self.zoom_at_center(1.18)
                event.accept()
                return True
            if key in (Qt.Key_Minus, Qt.Key_Underscore):
                self.zoom_at_center(1 / 1.18)
                event.accept()
                return True
            if key in (Qt.Key_0, Qt.Key_Home):
                self.reset_view()
                event.accept()
                return True
            if key in (Qt.Key_Left, Qt.Key_A):
                self.pan_by_widget_delta(-pan_step, 0)
                event.accept()
                return True
            if key in (Qt.Key_Right, Qt.Key_D):
                self.pan_by_widget_delta(pan_step, 0)
                event.accept()
                return True
            if key in (Qt.Key_Up, Qt.Key_W):
                self.pan_by_widget_delta(0, -pan_step)
                event.accept()
                return True
            if key in (Qt.Key_Down, Qt.Key_S):
                self.pan_by_widget_delta(0, pan_step)
                event.accept()
                return True
        if obj not in (self.viewport(), self.image_label):
            return super().eventFilter(obj, event)
        if event.type() == QEvent.Wheel:
            if event.modifiers() & Qt.ControlModifier:
                anchor = self.viewport().mapFromGlobal(event.globalPos())
                self.zoom_by(1.18 if event.angleDelta().y() > 0 else 1 / 1.18, anchor)
            elif event.modifiers() & Qt.ShiftModifier:
                pixel_delta = event.pixelDelta() if callable(getattr(event, "pixelDelta", None)) else QPoint()
                pixel_is_null = pixel_delta.isNull() if callable(getattr(pixel_delta, "isNull", None)) else True
                dx = pixel_delta.x() if not pixel_is_null else event.angleDelta().x() / 3
                dy = pixel_delta.y() if not pixel_is_null else event.angleDelta().y() / 3
                if not dx:
                    dx, dy = dy, 0
                self.pan_by_widget_delta(float(dx), float(-dy))
            else:
                self.brush_wheel_requested.emit(1 if event.angleDelta().y() > 0 else -1)
            event.accept()
            return True
        if event.type() == QEvent.MouseMove:
            if self.dragging:
                current = self.viewport().mapFromGlobal(event.globalPos())
                delta = current - self.drag_start
                self.horizontalScrollBar().setValue(self.drag_h_value - delta.x())
                self.verticalScrollBar().setValue(self.drag_v_value - delta.y())
                event.accept()
                return True
            label_pos = self._event_label_pos(obj, event)
            if self.space_down:
                self._clear_brush_preview()
                event.accept()
                return True
            next_brush_pos = label_pos if self.image_label.rect().contains(label_pos) else None
            if self.image_label.brush_pos != next_brush_pos:
                self.image_label.brush_pos = next_brush_pos
                self.image_label.update()
            if self.painting:
                point = self._label_to_image(label_pos)
                if point is not None and self.last_image_point is not None:
                    self.stroke_requested.emit(self.last_image_point, point)
                    self.last_image_point = point
                event.accept()
                return True
        if event.type() == QEvent.Leave:
            self.image_label.brush_pos = None
            self.image_label.update()
            return False
        if event.type() == QEvent.MouseButtonPress and event.button() == Qt.LeftButton:
            if self.space_down:
                self.dragging = True
                self.drag_start = self.viewport().mapFromGlobal(event.globalPos())
                self.drag_h_value = self.horizontalScrollBar().value()
                self.drag_v_value = self.verticalScrollBar().value()
                self._refresh_cursor()
                event.accept()
                return True
            point = self._label_to_image(self._event_label_pos(obj, event))
            if point is not None:
                self.painting = True
                self.last_image_point = point
                self.stroke_started.emit()
                self.stroke_requested.emit(point, point)
                self._refresh_cursor()
                event.accept()
                return True
        if event.type() == QEvent.MouseButtonRelease and event.button() == Qt.LeftButton:
            was_painting = self.painting
            self.painting = False
            self.dragging = False
            self.last_image_point = None
            self._refresh_cursor()
            if was_painting:
                self.stroke_finished.emit()
            event.accept()
            return True
        return super().eventFilter(obj, event)


class PgmEditorDialog(QDialog):
    def __init__(self, map_path: str | Path, save_callback: Callable[[bytes], bool], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.map_path = Path(map_path)
        self.save_callback = save_callback
        self.pgm = pgm_editor.load_pgm(self.map_path)
        self.original_pixels = self.pgm.pixels
        self.pixels = bytearray(self.pgm.pixels)
        self.current_stroke_snapshot: bytes | None = None
        self.undo_stack: list[bytes] = []
        self.redo_stack: list[bytes] = []
        self.brush_mode = pgm_editor.BRUSH_ERASE
        self.brush_radius = 8
        self.dirty = False
        self.setObjectName("ToolDialog")
        self.setWindowTitle("编辑 map.pgm")
        self.resize(1180, 780)
        self._build_ui()
        self._refresh_canvas()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 14)
        layout.setSpacing(10)
        header = QHBoxLayout()
        path_label = QLabel(str(self.map_path))
        path_label.setObjectName("Muted")
        path_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        path_label.setWordWrap(True)
        self.zoom_label = QLabel("100%")
        self.zoom_label.setObjectName("Muted")
        self.zoom_label.setMinimumWidth(62)
        self.zoom_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        header.addWidget(path_label, 1)
        header.addWidget(self.zoom_label)
        layout.addLayout(header)

        toolbar = QHBoxLayout()
        self.mode_group = QButtonGroup(self)
        self.mode_group.setExclusive(True)
        for mode, label in MODE_LABELS.items():
            button = QPushButton(label)
            button.setCheckable(True)
            button.setMinimumHeight(32)
            button.setToolTip(f"当前画笔模式：{label}")
            self.mode_group.addButton(button)
            self.mode_group.setId(button, len(self.mode_group.buttons()))
            button.clicked.connect(lambda _checked=False, selected=mode: self.set_brush_mode(selected))
            toolbar.addWidget(button)
            if mode == self.brush_mode:
                button.setChecked(True)
        toolbar.addSpacing(12)
        toolbar.addWidget(QLabel("画笔大小"))
        self.decrease_brush_button = QPushButton("-")
        self.decrease_brush_button.setFixedWidth(34)
        self.decrease_brush_button.setToolTip("减小画笔大小（[）")
        self.decrease_brush_button.clicked.connect(lambda: self.adjust_brush_radius(-1))
        self.radius_slider = QSlider(Qt.Horizontal)
        self.radius_slider.setRange(2, 80)
        self.radius_slider.setValue(self.brush_radius)
        self.radius_slider.setMinimumWidth(180)
        self.radius_spin = QSpinBox()
        self.radius_spin.setRange(2, 80)
        self.radius_spin.setValue(self.brush_radius)
        self.radius_spin.setSuffix(" px")
        self.radius_spin.setToolTip("画笔半径，鼠标滚轮或 [ / ] 也可调整")
        self.increase_brush_button = QPushButton("+")
        self.increase_brush_button.setFixedWidth(34)
        self.increase_brush_button.setToolTip("增大画笔大小（]）")
        self.increase_brush_button.clicked.connect(lambda: self.adjust_brush_radius(1))
        self.radius_slider.valueChanged.connect(self.set_brush_radius)
        self.radius_spin.valueChanged.connect(self.set_brush_radius)
        toolbar.addWidget(self.decrease_brush_button)
        toolbar.addWidget(self.radius_slider, 1)
        toolbar.addWidget(self.radius_spin)
        toolbar.addWidget(self.increase_brush_button)
        layout.addLayout(toolbar)

        self.canvas = PgmEditorCanvas(self._pixmap_from_pixels(), self.zoom_label, self)
        self.canvas.stroke_started.connect(self.begin_stroke)
        self.canvas.stroke_finished.connect(self.finish_stroke)
        self.canvas.stroke_requested.connect(self.apply_stroke)
        self.canvas.brush_wheel_requested.connect(self.adjust_brush_radius)
        self.canvas.set_brush(self.brush_radius, self.brush_mode)
        layout.addWidget(self.canvas, 1)
        self.installEventFilter(self.canvas)
        QTimer.singleShot(0, self.canvas.fit_to_view)
        QTimer.singleShot(0, self.canvas.setFocus)

        footer = QHBoxLayout()
        self.status = QLabel(
            "左键拖动绘制；方向键/WASD 平移，+/- 缩放，0/Home 复位；滚轮或 [ / ] 调画笔。"
        )
        self.status.setObjectName("Muted")
        self.undo_button = QPushButton("撤销")
        self.redo_button = QPushButton("重做")
        self.reset_button = QPushButton("重置")
        self.save_button = QPushButton("保存到远端")
        self.save_button.setObjectName("Primary")
        close_button = QPushButton("关闭")
        self.undo_button.clicked.connect(self.undo)
        self.redo_button.clicked.connect(self.redo)
        self.reset_button.clicked.connect(self.reset_to_original)
        self.save_button.clicked.connect(self.save_to_remote)
        close_button.clicked.connect(self.close)
        footer.addWidget(self.status, 1)
        for button in (self.undo_button, self.redo_button, self.reset_button, self.save_button, close_button):
            button.setMinimumHeight(34)
            footer.addWidget(button)
        layout.addLayout(footer)
        QShortcut(QKeySequence("Ctrl+Z"), self).activated.connect(self.undo)
        QShortcut(QKeySequence("Ctrl+Y"), self).activated.connect(self.redo)
        QShortcut(QKeySequence("["), self).activated.connect(lambda: self.adjust_brush_radius(-1))
        QShortcut(QKeySequence("]"), self).activated.connect(lambda: self.adjust_brush_radius(1))
        QShortcut(QKeySequence("Esc"), self).activated.connect(self.close)
        self._update_action_buttons()

    def _pixmap_from_pixels(self) -> QPixmap:
        image = QImage(bytes(self.pixels), self.pgm.width, self.pgm.height, self.pgm.width, QImage.Format_Grayscale8).copy()
        return QPixmap.fromImage(image)

    def _refresh_canvas(self) -> None:
        self.canvas.set_source_pixmap(self._pixmap_from_pixels())
        self.canvas.set_brush(self.brush_radius, self.brush_mode)

    def set_brush_mode(self, mode: str) -> None:
        self.brush_mode = mode
        self.canvas.set_brush(self.brush_radius, self.brush_mode)
        self.status.setText(f"当前模式：{MODE_LABELS.get(mode, mode)}")

    def set_brush_radius(self, value: int) -> None:
        value = max(2, min(80, int(value)))
        if self.brush_radius == value:
            return
        self.brush_radius = value
        if self.radius_slider.value() != value:
            self.radius_slider.setValue(value)
        if self.radius_spin.value() != value:
            self.radius_spin.setValue(value)
        self.canvas.set_brush(self.brush_radius, self.brush_mode)
        self.status.setText(f"画笔大小：{value} px")

    def adjust_brush_radius(self, delta: int) -> None:
        self.set_brush_radius(self.brush_radius + delta)

    def _push_undo_snapshot(self, snapshot: bytes) -> None:
        if self.undo_stack and self.undo_stack[-1] == snapshot:
            return
        self.undo_stack.append(snapshot)
        if len(self.undo_stack) > 40:
            self.undo_stack.pop(0)
        self.redo_stack.clear()

    def _push_undo(self) -> None:
        self._push_undo_snapshot(bytes(self.pixels))

    def begin_stroke(self) -> None:
        if self.current_stroke_snapshot is None:
            self.current_stroke_snapshot = bytes(self.pixels)

    def finish_stroke(self) -> None:
        snapshot = self.current_stroke_snapshot
        self.current_stroke_snapshot = None
        if snapshot is not None and bytes(self.pixels) != snapshot:
            self._push_undo_snapshot(snapshot)
        self.dirty = bytes(self.pixels) != self.original_pixels
        self._update_action_buttons()

    def apply_stroke(self, start: tuple[float, float], end: tuple[float, float]) -> None:
        before = bytes(self.pixels)
        changed = pgm_editor.erase_stroke(
            self.pixels,
            self.original_pixels,
            self.pgm.width,
            self.pgm.height,
            start,
            end,
            self.brush_radius,
            self.brush_mode,
        )
        if not changed:
            return
        if self.current_stroke_snapshot is None:
            self._push_undo_snapshot(before)
        self.dirty = bytes(self.pixels) != self.original_pixels
        self._refresh_canvas()
        self._update_action_buttons()

    def undo(self) -> None:
        if not self.undo_stack:
            return
        self.redo_stack.append(bytes(self.pixels))
        self.pixels = bytearray(self.undo_stack.pop())
        self.dirty = bytes(self.pixels) != self.original_pixels
        self._refresh_canvas()
        self._update_action_buttons()

    def redo(self) -> None:
        if not self.redo_stack:
            return
        self.undo_stack.append(bytes(self.pixels))
        self.pixels = bytearray(self.redo_stack.pop())
        self.dirty = bytes(self.pixels) != self.original_pixels
        self._refresh_canvas()
        self._update_action_buttons()

    def reset_to_original(self) -> None:
        if bytes(self.pixels) == self.original_pixels:
            return
        self._push_undo()
        self.pixels = bytearray(self.original_pixels)
        self.dirty = False
        self._refresh_canvas()
        self._update_action_buttons()

    def _update_action_buttons(self) -> None:
        self.undo_button.setEnabled(bool(self.undo_stack))
        self.redo_button.setEnabled(bool(self.redo_stack))
        self.reset_button.setEnabled(bytes(self.pixels) != self.original_pixels)
        self.save_button.setEnabled(bytes(self.pixels) != self.original_pixels)

    def current_pgm_bytes(self) -> bytes:
        return self.pgm.header + bytes(self.pixels)

    def save_to_remote(self) -> None:
        if bytes(self.pixels) == self.original_pixels:
            QMessageBox.information(self, "没有改动", "当前地图没有需要保存的修改。")
            return
        if self.save_callback(self.current_pgm_bytes()):
            self.accept()
