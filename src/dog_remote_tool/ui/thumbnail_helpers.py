from __future__ import annotations

from pathlib import Path

from PyQt5.QtCore import QSize, Qt
from PyQt5.QtGui import QPixmap
from PyQt5.QtWidgets import QLabel


def load_thumbnail_pixmap(label: QLabel, image_path: Path, unavailable_text: str = "预览不可用") -> QPixmap | None:
    pixmap = QPixmap(str(image_path))
    if pixmap.isNull():
        label.setPixmap(QPixmap())
        label.setText(unavailable_text)
        return None
    label.setText("")
    return pixmap


def update_scaled_thumbnail(label: QLabel, pixmap: QPixmap | None, fallback_size: QSize | None = None) -> bool:
    if pixmap is None:
        return False
    target = label.size()
    if target.width() <= 0 or target.height() <= 0:
        if fallback_size is None:
            return False
        target = fallback_size
    label.setPixmap(pixmap.scaled(target, Qt.KeepAspectRatio, Qt.FastTransformation))
    return True
