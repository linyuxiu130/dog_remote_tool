from __future__ import annotations

from PyQt5.QtWidgets import QApplication

from .dialogs import install_dialog_polish
from .theme_styles import APP_STYLESHEET


def apply_theme(app: QApplication) -> None:
    app.setStyle("Fusion")
    app.setStyleSheet(APP_STYLESHEET)
    install_dialog_polish(app)
