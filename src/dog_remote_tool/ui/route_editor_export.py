from __future__ import annotations

from pathlib import Path

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QPainter
from PyQt5.QtPrintSupport import QPrinter
from PyQt5.QtWidgets import QFileDialog


class RouteEditorExportMixin:
    def export_canvas_image(self) -> None:
        path, _filter = QFileDialog.getSaveFileName(
            self,
            "导出路网画布",
            str(Path.home() / "route_network.png"),
            "PNG 图片 (*.png);;JPEG 图片 (*.jpg *.jpeg);;PDF 文件 (*.pdf)",
        )
        if not path:
            return
        target = Path(path)
        pixmap = self.canvas.grab()
        if target.suffix.lower() == ".pdf":
            printer = QPrinter(QPrinter.HighResolution)
            printer.setOutputFormat(QPrinter.PdfFormat)
            printer.setOutputFileName(str(target))
            painter = QPainter(printer)
            page_rect = printer.pageRect()
            scaled = pixmap.scaled(page_rect.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation)
            x = page_rect.x() + (page_rect.width() - scaled.width()) / 2
            y = page_rect.y() + (page_rect.height() - scaled.height()) / 2
            painter.drawPixmap(int(x), int(y), scaled)
            painter.end()
        else:
            if target.suffix.lower() not in {".png", ".jpg", ".jpeg"}:
                target = target.with_suffix(".png")
            pixmap.save(str(target))
        self.editor_status.setText(f"已导出：{target.name}")
