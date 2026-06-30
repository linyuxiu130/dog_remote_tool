from __future__ import annotations

from PyQt5.QtCore import QEvent, QPoint, Qt
from PyQt5.QtGui import QPixmap
from PyQt5.QtWidgets import QLabel, QScrollArea, QWidget


class ZoomableImageArea(QScrollArea):
    def __init__(self, pixmap: QPixmap, zoom_label: QLabel, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.source_pixmap = pixmap
        self.zoom_label = zoom_label
        self.scale = 1.0
        self.space_down = False
        self.dragging = False
        self.drag_start = QPoint()
        self.drag_h_value = 0
        self.drag_v_value = 0
        self.fit_label = False

        self.image_label = QLabel()
        self.image_label.setAlignment(Qt.AlignCenter)
        self.image_label.setFocusPolicy(Qt.NoFocus)
        self.image_label.installEventFilter(self)
        self.setObjectName("DialogScroll")
        self.setWidgetResizable(False)
        self.setAlignment(Qt.AlignCenter)
        self.setFocusPolicy(Qt.StrongFocus)
        self.viewport().installEventFilter(self)
        self.setWidget(self.image_label)

    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key_Space:
            self.space_down = True
            self._refresh_cursor()
            event.accept()
            return
        super().keyPressEvent(event)

    def keyReleaseEvent(self, event) -> None:
        if event.key() == Qt.Key_Space:
            self.space_down = False
            self.dragging = False
            self._refresh_cursor()
            event.accept()
            return
        super().keyReleaseEvent(event)

    def wheelEvent(self, event) -> None:
        if event.modifiers() & Qt.ControlModifier:
            self.zoom_by(1.18 if event.angleDelta().y() > 0 else 1 / 1.18, event.pos())
            event.accept()
            return
        super().wheelEvent(event)

    def fit_to_view(self) -> None:
        viewport = self.viewport().size()
        if viewport.width() <= 1 or viewport.height() <= 1:
            return
        scale_x = max(0.01, (viewport.width() - 10) / max(1, self.source_pixmap.width()))
        scale_y = max(0.01, (viewport.height() - 10) / max(1, self.source_pixmap.height()))
        fit_scale = min(scale_x, scale_y)
        if fit_scale > 1.0:
            fit_scale = min(fit_scale, 2.5)
        self.set_scale(fit_scale, center=True, fit_label=True)

    def zoom_by(self, factor: float, anchor: QPoint | None = None) -> None:
        self.set_scale(self.scale * factor, anchor=anchor)

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

        self.scale = max(0.01, min(12.0, scale))
        width = max(1, int(self.source_pixmap.width() * self.scale))
        height = max(1, int(self.source_pixmap.height() * self.scale))
        scaled = self.source_pixmap.scaled(width, height, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        self.image_label.setPixmap(scaled)
        self.image_label.resize(scaled.size())
        self.fit_label = fit_label
        prefix = "适配 " if fit_label else ""
        percent = max(1, int(round(self.scale * 100)))
        self.zoom_label.setText(f"{prefix}{percent}%")

        if center:
            self.horizontalScrollBar().setValue(max(0, (self.image_label.width() - self.viewport().width()) // 2))
            self.verticalScrollBar().setValue(max(0, (self.image_label.height() - self.viewport().height()) // 2))
            return

        self.horizontalScrollBar().setValue(int(image_x * self.image_label.width() - viewport_anchor.x()))
        self.verticalScrollBar().setValue(int(image_y * self.image_label.height() - viewport_anchor.y()))

    def eventFilter(self, obj, event) -> bool:
        if event.type() == QEvent.KeyPress and event.key() == Qt.Key_Space:
            self.space_down = True
            self._refresh_cursor()
            return True
        if event.type() == QEvent.KeyRelease and event.key() == Qt.Key_Space:
            self.space_down = False
            self.dragging = False
            self._refresh_cursor()
            return True
        if obj in (self.viewport(), self.image_label):
            if event.type() == QEvent.Wheel and event.modifiers() & Qt.ControlModifier:
                anchor = self.viewport().mapFromGlobal(event.globalPos())
                self.zoom_by(1.18 if event.angleDelta().y() > 0 else 1 / 1.18, anchor)
                event.accept()
                return True
            if event.type() == QEvent.MouseButtonPress and self.space_down and event.button() == Qt.LeftButton:
                self.dragging = True
                self.drag_start = self.viewport().mapFromGlobal(event.globalPos())
                self.drag_h_value = self.horizontalScrollBar().value()
                self.drag_v_value = self.verticalScrollBar().value()
                self._refresh_cursor()
                event.accept()
                return True
            if event.type() == QEvent.MouseMove and self.dragging:
                current = self.viewport().mapFromGlobal(event.globalPos())
                delta = current - self.drag_start
                self.horizontalScrollBar().setValue(self.drag_h_value - delta.x())
                self.verticalScrollBar().setValue(self.drag_v_value - delta.y())
                event.accept()
                return True
            if event.type() == QEvent.MouseButtonRelease and self.dragging:
                self.dragging = False
                self._refresh_cursor()
                event.accept()
                return True
        return super().eventFilter(obj, event)

    def _refresh_cursor(self) -> None:
        cursor = Qt.ClosedHandCursor if self.dragging else Qt.OpenHandCursor if self.space_down else Qt.ArrowCursor
        self.viewport().setCursor(cursor)
        self.image_label.setCursor(cursor)
