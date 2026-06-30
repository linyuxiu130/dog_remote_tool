from __future__ import annotations

from PyQt5.QtCore import QTimer, Qt
from PyQt5.QtGui import QKeySequence, QPixmap
from PyQt5.QtWidgets import QApplication, QDialog, QHBoxLayout, QLabel, QMessageBox, QShortcut, QVBoxLayout, QWidget

from dog_remote_tool.ui.image_zoom import ZoomableImageArea


def show_zoomable_pixmap(
    parent: QWidget,
    title: str,
    pixmap: QPixmap | None,
    image_path: str,
    *,
    fullscreen: bool = False,
) -> bool:
    if not pixmap or pixmap.isNull():
        QMessageBox.information(parent, "预览不可用", "当前图片还没有加载完成。")
        return False

    dialog = QDialog(parent)
    dialog.setObjectName("ToolDialog")
    dialog.setWindowTitle(title)
    layout = QVBoxLayout(dialog)
    layout.setContentsMargins(14, 12, 14, 14)
    layout.setSpacing(10)

    header = QHBoxLayout()
    path_label = QLabel(image_path or title)
    path_label.setObjectName("Muted")
    path_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
    path_label.setWordWrap(True)
    zoom_label = QLabel("100%")
    zoom_label.setObjectName("Muted")
    zoom_label.setMinimumWidth(56)
    zoom_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
    header.addWidget(path_label, 1)
    header.addWidget(zoom_label)
    layout.addLayout(header)

    image_area = ZoomableImageArea(pixmap, zoom_label, dialog)
    layout.addWidget(image_area, 1)
    dialog.installEventFilter(image_area)

    QShortcut(QKeySequence("Ctrl+P"), dialog).activated.connect(lambda: image_area.zoom_by(1.25))
    QShortcut(QKeySequence("Ctrl+O"), dialog).activated.connect(lambda: image_area.zoom_by(0.8))
    QShortcut(QKeySequence("Esc"), dialog).activated.connect(dialog.close)

    if fullscreen:
        dialog.showFullScreen()
    elif screen := QApplication.primaryScreen():
        available = screen.availableGeometry()
        width = min(int(available.width() * 0.9), max(900, pixmap.width() + 40))
        height = min(int(available.height() * 0.9), max(650, pixmap.height() + 90))
        dialog.resize(width, height)
    else:
        dialog.resize(1100, 760)
    QTimer.singleShot(0, image_area.fit_to_view)
    QTimer.singleShot(80, image_area.fit_to_view)
    QTimer.singleShot(200, image_area.fit_to_view)
    QTimer.singleShot(0, image_area.setFocus)
    dialog.exec_()
    return True
