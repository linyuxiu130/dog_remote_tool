from __future__ import annotations

import os
import sys

from PyQt5.QtGui import QFont
from PyQt5.QtWidgets import QApplication

from .core.paths import app_root
from .ui.main_window import MainWindow
from .ui.theme import apply_theme


def main(argv: list[str] | None = None) -> int:
    argv = argv if argv is not None else sys.argv
    if len(argv) > 1 and argv[1] == "--robot-remote":
        from .modules.control.robot_remote.protocol import main as robot_remote_main

        return robot_remote_main(argv[2:])

    if os.environ.get("XDG_SESSION_TYPE") == "wayland" and not os.environ.get("QT_QPA_PLATFORM"):
        os.environ["QT_QPA_PLATFORM"] = "xcb"
        os.environ.pop("XDG_SESSION_TYPE", None)

    app = QApplication(argv)
    app.setApplicationName("Remote Debug Platform")
    app.setOrganizationName("ZSZH")
    app.setFont(QFont("Noto Sans CJK SC", 10))
    apply_theme(app)

    window = MainWindow(app_root())
    if "--smoke-test" in argv:
        print(
            f"{window.windowTitle()} pages={window.stack.count()} "
            f"size={window.width()}x{window.height()} "
            f"min={window.minimumWidth()}x{window.minimumHeight()} "
            f"font={app.font().family()}:{app.font().pointSize()}"
        )
        window._skip_page_shutdown_for_smoke = True
        window.close()
        window.deleteLater()
        app.processEvents()
        del window
        app.processEvents()
        sys.stdout.flush()
        sys.stderr.flush()
        os._exit(0)
        return 0
    window.showMaximized()
    return app.exec_()
