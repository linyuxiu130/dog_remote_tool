from __future__ import annotations

from datetime import datetime
import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5.QtCore import QEvent, Qt
from PyQt5.QtGui import QColor, QPixmap
from PyQt5.QtWidgets import QApplication, QLabel

from dog_remote_tool.core.profiles import PRODUCTS
from dog_remote_tool.core.shell import quote
from dog_remote_tool.modules import mapping
from dog_remote_tool.modules.mapping import pgm_editor
from dog_remote_tool.ui.pages.mapping.pgm_editor_dialog import PgmEditorCanvas, PgmEditorDialog, _PaintLabel


def _write_pgm(path, width=7, height=7, fill=128):
    path.write_bytes(b"P5\n# comment\n%d %d\n255\n" % (width, height) + bytes([fill]) * width * height)


_QT_APP = None


def _app():
    global _QT_APP
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    _QT_APP = app
    return app


def test_load_pgm_preserves_header_and_pixels(tmp_path):
    image = tmp_path / "map.pgm"
    _write_pgm(image, width=3, height=2, fill=255)

    pgm = pgm_editor.load_pgm(image)

    assert pgm.width == 3
    assert pgm.height == 2
    assert pgm.maxval == 255
    assert pgm.header.startswith(b"P5\n# comment")
    assert pgm.to_bytes() == image.read_bytes()


def test_circle_brush_modes_write_obstacle_free_unknown_and_restore(tmp_path):
    image = tmp_path / "map.pgm"
    _write_pgm(image, width=7, height=7, fill=255)
    pgm = pgm_editor.load_pgm(image)
    original = bytes([255 if i == 24 else value for i, value in enumerate(pgm.pixels)])
    pixels = bytearray(original)

    changed = pgm_editor.erase_circle(pixels, original, 7, 7, 3, 3, 1, pgm_editor.BRUSH_OBSTACLE)
    assert changed > 0
    assert pixels[24] == 0

    pgm_editor.erase_circle(pixels, original, 7, 7, 3, 3, 1, pgm_editor.BRUSH_ERASE)
    assert pixels[24] == 255

    pgm_editor.erase_circle(pixels, original, 7, 7, 3, 3, 1, pgm_editor.BRUSH_UNKNOWN)
    assert pgm_editor.UNKNOWN_PIXEL_VALUE == 128
    assert pixels[24] == pgm_editor.UNKNOWN_PIXEL_VALUE

    pixels[24] = 0
    pgm_editor.erase_circle(pixels, original, 7, 7, 3, 3, 1, pgm_editor.BRUSH_RESTORE)
    assert pixels[24] == original[24]


def test_brush_modes_can_overwrite_unknown_to_obstacle_free_or_unknown(tmp_path):
    image = tmp_path / "map.pgm"
    image.write_bytes(
        b"P5\n3 3\n255\n"
        + bytes(
            [
                255,
                255,
                255,
                255,
                128,
                255,
                255,
                255,
                255,
            ]
        )
    )
    pgm = pgm_editor.load_pgm(image)
    pixels = bytearray(pgm.pixels)

    pgm_editor.erase_circle(pixels, pgm.pixels, 3, 3, 1, 1, 2, pgm_editor.BRUSH_OBSTACLE)
    assert pixels[4] == 0

    pixels[4] = 128
    pgm_editor.erase_circle(pixels, pgm.pixels, 3, 3, 1, 1, 2, pgm_editor.BRUSH_ERASE)
    assert pixels[4] == 255

    pgm_editor.erase_circle(pixels, pgm.pixels, 3, 3, 1, 1, 2, pgm_editor.BRUSH_UNKNOWN)
    assert pixels[4] == pgm_editor.UNKNOWN_PIXEL_VALUE

    pgm_editor.erase_circle(pixels, pgm.pixels, 3, 3, 1, 1, 2, pgm_editor.BRUSH_RESTORE)
    assert pixels[4] == 128


def test_stroke_interpolates_between_fast_mouse_points(tmp_path):
    image = tmp_path / "map.pgm"
    _write_pgm(image, width=20, height=5, fill=0)
    pgm = pgm_editor.load_pgm(image)
    pixels = bytearray(pgm.pixels)

    pgm_editor.erase_stroke(pixels, pgm.pixels, 20, 5, (1, 2), (18, 2), 2, pgm_editor.BRUSH_ERASE)

    assert all(pixels[2 * 20 + x] == 255 for x in range(1, 19))


def test_unknown_brush_preview_color_stays_visible_on_unknown_pixels():
    _app()
    label = _PaintLabel()
    label.brush_mode = pgm_editor.BRUSH_UNKNOWN

    color = label._brush_preview_color()

    assert color == QColor(245, 158, 11)
    assert color != QColor(
        pgm_editor.UNKNOWN_PIXEL_VALUE,
        pgm_editor.UNKNOWN_PIXEL_VALUE,
        pgm_editor.UNKNOWN_PIXEL_VALUE,
    )


def test_pgm_editor_canvas_keyboard_pan_zoom_and_reset_without_mouse():
    app = _app()
    zoom_label = QLabel("100%")
    pixmap = QPixmap(600, 400)
    pixmap.fill(QColor("white"))
    canvas = PgmEditorCanvas(pixmap, zoom_label)
    canvas.resize(220, 160)
    canvas.show()
    canvas.set_scale(2.0, center=True)
    app.processEvents()

    class KeyEvent:
        def __init__(self, key, *, auto_repeat=False):
            self._key = key
            self._auto_repeat = auto_repeat
            self.accepted = False

        def type(self):
            return QEvent.KeyPress

        def key(self):
            return self._key

        def modifiers(self):
            return Qt.NoModifier

        def isAutoRepeat(self):
            return self._auto_repeat

        def accept(self):
            self.accepted = True

    canvas.horizontalScrollBar().setValue(0)
    first = KeyEvent(Qt.Key_D)
    repeat = KeyEvent(Qt.Key_D, auto_repeat=True)
    canvas.eventFilter(canvas, first)
    middle = canvas.horizontalScrollBar().value()
    canvas.eventFilter(canvas, repeat)
    after = canvas.horizontalScrollBar().value()

    assert first.accepted
    assert repeat.accepted
    assert middle > 0
    assert after > middle

    zoom_before = canvas.scale
    zoom_event = KeyEvent(Qt.Key_Plus)
    canvas.eventFilter(canvas, zoom_event)
    assert zoom_event.accepted
    assert canvas.scale > zoom_before

    reset_event = KeyEvent(Qt.Key_0)
    canvas.eventFilter(canvas, reset_event)
    assert reset_event.accepted
    assert canvas.scale < zoom_before


def test_pgm_editor_dialog_groups_drag_stroke_into_single_undo(tmp_path):
    _app()
    image = tmp_path / "map.pgm"
    _write_pgm(image, width=20, height=6, fill=255)
    dialog = PgmEditorDialog(image, lambda _payload: True)
    dialog.set_brush_mode(pgm_editor.BRUSH_OBSTACLE)
    dialog.brush_radius = 1

    dialog.begin_stroke()
    dialog.apply_stroke((1, 3), (6, 3))
    dialog.apply_stroke((6, 3), (12, 3))
    dialog.finish_stroke()

    changed = bytes(dialog.pixels)
    assert len(dialog.undo_stack) == 1
    assert changed != dialog.original_pixels

    dialog.undo()
    assert bytes(dialog.pixels) == dialog.original_pixels
    assert dialog.redo_stack == [changed]


@pytest.mark.parametrize(
    "payload,error",
    [
        (b"P2\n1 1\n255\n0", "P5"),
        (b"P5\n1 1\n100\n0", "maxval=255"),
        (b"P5\n2 2\n255\n123", "像素长度"),
    ],
)
def test_load_pgm_rejects_unsupported_or_incomplete_files(tmp_path, payload, error):
    image = tmp_path / "map.pgm"
    image.write_bytes(payload)

    with pytest.raises(ValueError, match=error):
        pgm_editor.load_pgm(image)


def test_local_backup_path_uses_backups_directory(tmp_path):
    path = pgm_editor.local_backup_path(tmp_path / "map.pgm", datetime(2026, 6, 15, 12, 30, 45))

    assert path == tmp_path / "backups" / "map_original_20260615_123045.pgm"


def test_upload_edited_map_pgm_command_backs_up_and_installs_remote_file(tmp_path):
    local_pgm = tmp_path / "map.pgm"
    local_pgm.write_bytes(b"P5\n1 1\n255\n\xff")
    profile = PRODUCTS["xg2_s100"]
    remote_pgm = "/opt/data/.robot/map/history_map/a/map.pgm"

    spec = mapping.upload_edited_map_pgm_command(profile, str(local_pgm), remote_pgm)

    assert spec.title == "保存编辑地图"
    assert spec.dangerous is True
    assert spec.concurrency == "parallel"
    assert f"host:{profile.host}:map:{remote_pgm}" in spec.locks
    assert f"test -s {quote(str(local_pgm))}" in spec.command
    assert "dog_remote_tool_map_edit_upload/map.pgm" in spec.command
    assert "case \"$TARGET\" in */map.pgm)" in spec.command
    assert "TARGET_YAML=" in spec.command
    assert "BACKUP=\"$TARGET.bak.$(date +%Y%m%d_%H%M%S)\"" in spec.command
    assert "sudo_run cp -a -- \"$TARGET\" \"$BACKUP\"" in spec.command
    assert "sudo_run install -m 0644 \"$TMP\" \"$TARGET\"" in spec.command
