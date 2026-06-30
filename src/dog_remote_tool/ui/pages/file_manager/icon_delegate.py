from __future__ import annotations

from PyQt5.QtCore import QRect, QSize, Qt
from PyQt5.QtGui import QColor, QFontMetrics, QPainter, QPen
from PyQt5.QtWidgets import QStyle, QStyledItemDelegate, QStyleOptionViewItem


STATE_SELECTED = QStyle.State_Selected
STATE_MOUSE_OVER = QStyle.State_MouseOver


class FileIconDelegate(QStyledItemDelegate):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.cell_width = 210
        self.base_cell_height = 230
        self.cell_height = self.base_cell_height
        self.icon_size = 88
        self.text_width = 164
        self.max_lines = 3
        self.icon_top = 14
        self.text_gap = 12
        self.cell_bottom = 10

    def sizeHint(self, _option, _index) -> QSize:
        return QSize(self.cell_width, self.cell_height)

    def height_for_lines(self, line_count: int, metrics: QFontMetrics) -> int:
        text_height = max(1, line_count) * metrics.lineSpacing() + 8
        return max(self.base_cell_height, self.icon_top + self.icon_size + self.text_gap + text_height + self.cell_bottom)

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index) -> None:
        painter.save()
        try:
            painter.setClipRect(option.rect.adjusted(2, 2, -2, -2))
            selected = bool(option.state & STATE_SELECTED)
            if option.state & STATE_MOUSE_OVER and not selected:
                painter.setPen(Qt.NoPen)
                painter.setBrush(QColor("#f1f5f9"))
                rect = option.rect.adjusted(12, 10, -12, -10)
                painter.drawRoundedRect(rect, 8, 8)

            icon = index.data(Qt.DecorationRole)
            icon_rect = QRect(
                option.rect.center().x() - self.icon_size // 2,
                option.rect.top() + self.icon_top,
                self.icon_size,
                self.icon_size,
            )
            if icon:
                icon.paint(painter, icon_rect, Qt.AlignCenter)

            text = index.data(Qt.DisplayRole) or ""
            text_rect = QRect(
                option.rect.center().x() - self.text_width // 2,
                icon_rect.bottom() + self.text_gap,
                self.text_width,
                option.rect.bottom() - icon_rect.bottom() - self.cell_bottom,
            )
            metrics = QFontMetrics(option.font)
            line_height = metrics.lineSpacing()
            line_capacity = max(1, (text_rect.height() - 8) // line_height)
            if selected:
                lines = self._wrapped_lines(str(text), metrics, None)[:line_capacity]
            else:
                lines = self._wrapped_lines(str(text), metrics, min(self.max_lines, line_capacity))
            if selected and lines:
                text_width = max(metrics.horizontalAdvance(line) for line in lines)
                pill_width = max(72, min(self.text_width, text_width + 18))
                pill_rect = QRect(
                    option.rect.center().x() - pill_width // 2,
                    text_rect.top() - 4,
                    pill_width,
                    len(lines) * line_height + 8,
                )
                painter.setPen(Qt.NoPen)
                painter.setBrush(QColor("#e95420"))
                painter.drawRoundedRect(pill_rect, 7, 7)
                painter.setPen(QPen(QColor("#ffffff")))
            else:
                painter.setPen(QPen(QColor("#10233f")))

            y = text_rect.top()
            for line in lines:
                painter.drawText(QRect(text_rect.left(), y, text_rect.width(), line_height), Qt.AlignHCenter, line)
                y += line_height
        finally:
            painter.restore()

    def _wrapped_lines(self, text: str, metrics: QFontMetrics, max_lines: int | None) -> list[str]:
        if not text:
            return []
        tokens = self._tokens(text)
        lines: list[str] = []
        current = ""
        for token in tokens:
            candidate = token if not current else current + token
            if metrics.horizontalAdvance(candidate) <= self.text_width:
                current = candidate
                continue
            if current:
                lines.append(current)
            current = token
            while metrics.horizontalAdvance(current) > self.text_width:
                cut = self._fit_prefix(current, metrics)
                lines.append(cut)
                current = current[len(cut):]
        if current:
            lines.append(current)
        if max_lines is None:
            return lines
        line_limit = max_lines
        if len(lines) <= line_limit:
            return lines
        shown = lines[:line_limit]
        shown[-1] = metrics.elidedText(shown[-1] + "".join(lines[line_limit:]), Qt.ElideRight, self.text_width)
        return shown

    def _fit_prefix(self, text: str, metrics: QFontMetrics) -> str:
        for index in range(1, len(text) + 1):
            if metrics.horizontalAdvance(text[:index]) > self.text_width:
                return text[: max(1, index - 1)]
        return text

    def _tokens(self, text: str) -> list[str]:
        tokens: list[str] = []
        current = ""
        for char in text:
            current += char
            if char in {"_", "-", "."}:
                tokens.append(current)
                current = ""
        if current:
            tokens.append(current)
        return tokens
