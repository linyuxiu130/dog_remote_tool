import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5.QtGui import QColor, QPixmap
from PyQt5.QtWidgets import QApplication, QLabel

from dog_remote_tool.ui.thumbnail_helpers import load_thumbnail_pixmap, update_scaled_thumbnail


_QT_APP = None


def _app():
    global _QT_APP
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    _QT_APP = app
    return app


def test_thumbnail_helpers_load_scale_and_clear_missing_file(tmp_path):
    _app()
    image_path = tmp_path / "map.pgm"
    source = QPixmap(12, 8)
    source.fill(QColor("#336699"))
    assert source.save(str(image_path), "PNG")

    label = QLabel("预览待加载")
    label.resize(24, 16)
    pixmap = load_thumbnail_pixmap(label, image_path)
    assert pixmap is not None
    assert label.text() == ""
    assert update_scaled_thumbnail(label, pixmap) is True
    assert label.pixmap() is not None
    assert not label.pixmap().isNull()

    missing = load_thumbnail_pixmap(label, tmp_path / "missing.pgm")
    assert missing is None
    assert label.text() == "预览不可用"
    current = label.pixmap()
    assert current is None or current.isNull()


def test_update_scaled_thumbnail_ignores_empty_pixmap():
    _app()
    label = QLabel()
    assert update_scaled_thumbnail(label, None) is False
