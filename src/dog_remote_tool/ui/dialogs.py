from __future__ import annotations

from PyQt5.QtCore import QObject, QEvent, Qt
from PyQt5.QtWidgets import (
    QApplication,
    QFileDialog,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMessageBox,
    QWidget,
)

from dog_remote_tool.ui.message_dialogs import StyledMessageDialog, polish_message_buttons


class DialogPolishFilter(QObject):
    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        if event.type() in (QEvent.Show, QEvent.Polish) and isinstance(watched, QWidget):
            polish_dialog(watched)
        return super().eventFilter(watched, event)


def install_dialog_polish(app: QApplication) -> None:
    if app.property("_dog_remote_dialog_polish_installed"):
        return
    app.setProperty("_dog_remote_dialog_polish_installed", True)
    app.installEventFilter(DialogPolishFilter(app))
    _patch_message_boxes()
    _patch_input_dialogs()
    _patch_file_dialogs()


def polish_dialog(widget: QWidget) -> None:
    if not isinstance(widget, (StyledMessageDialog, QMessageBox, QInputDialog, QFileDialog)):
        return
    if widget.property("_dog_remote_dialog_polished"):
        return
    widget.setProperty("_dog_remote_dialog_polished", True)

    if isinstance(widget, StyledMessageDialog):
        widget.resize(max(widget.width(), 460), max(widget.height(), 136))
        return

    widget.setMinimumWidth(max(widget.minimumWidth(), 520))

    if isinstance(widget, QMessageBox):
        widget.setTextInteractionFlags(Qt.TextSelectableByMouse)
        for label in widget.findChildren(QLabel):
            label.setWordWrap(True)
            label.setMinimumWidth(max(label.minimumWidth(), 480))
        polish_message_buttons(widget)
        widget.resize(max(widget.width(), 540), max(widget.height(), 170))
        return

    if isinstance(widget, QInputDialog):
        widget.setMinimumWidth(max(widget.minimumWidth(), 520))
        widget.resize(max(widget.width(), 540), max(widget.height(), 150))
        return

    if isinstance(widget, QFileDialog):
        widget.setOption(QFileDialog.DontUseNativeDialog, True)
        widget.resize(max(widget.width(), 900), max(widget.height(), 560))


def _styled_message_box(
    icon: QMessageBox.Icon,
    parent: QWidget | None,
    title: str,
    text: str,
    buttons: QMessageBox.StandardButtons,
    default_button: QMessageBox.StandardButton = QMessageBox.NoButton,
) -> QMessageBox.StandardButton:
    dialog = StyledMessageDialog(icon, parent, title, text, buttons, default_button)
    polish_dialog(dialog)
    dialog.exec_()
    return dialog.result_button


def _patch_message_boxes() -> None:
    if getattr(QMessageBox, "_dog_remote_static_patched", False):
        return
    QMessageBox._dog_remote_static_patched = True

    def information(parent, title, text, buttons=QMessageBox.Ok, defaultButton=QMessageBox.NoButton):
        return _styled_message_box(QMessageBox.Information, parent, title, text, buttons, defaultButton)

    def warning(parent, title, text, buttons=QMessageBox.Ok, defaultButton=QMessageBox.NoButton):
        return _styled_message_box(QMessageBox.Warning, parent, title, text, buttons, defaultButton)

    def critical(parent, title, text, buttons=QMessageBox.Ok, defaultButton=QMessageBox.NoButton):
        return _styled_message_box(QMessageBox.Critical, parent, title, text, buttons, defaultButton)

    def question(parent, title, text, buttons=QMessageBox.Yes | QMessageBox.No, defaultButton=QMessageBox.NoButton):
        return _styled_message_box(QMessageBox.Question, parent, title, text, buttons, defaultButton)

    QMessageBox.information = staticmethod(information)
    QMessageBox.warning = staticmethod(warning)
    QMessageBox.critical = staticmethod(critical)
    QMessageBox.question = staticmethod(question)


def _patch_input_dialogs() -> None:
    if getattr(QInputDialog, "_dog_remote_static_patched", False):
        return
    QInputDialog._dog_remote_static_patched = True

    def get_text(
        parent,
        title,
        label,
        mode=QLineEdit.Normal,
        text="",
        flags=Qt.WindowFlags(),
        inputMethodHints=Qt.ImhNone,
    ):
        dialog = QInputDialog(parent, flags)
        dialog.setWindowTitle(title)
        dialog.setInputMode(QInputDialog.TextInput)
        dialog.setLabelText(label)
        dialog.setTextEchoMode(mode)
        dialog.setTextValue(text)
        dialog.setInputMethodHints(inputMethodHints)
        dialog.setOkButtonText("确定")
        dialog.setCancelButtonText("取消")
        polish_dialog(dialog)
        accepted = dialog.exec_() == QInputDialog.Accepted
        return dialog.textValue(), accepted

    QInputDialog.getText = staticmethod(get_text)


def _patch_file_dialogs() -> None:
    if getattr(QFileDialog, "_dog_remote_static_patched", False):
        return
    QFileDialog._dog_remote_static_patched = True
    original_get_open_file_name = QFileDialog.getOpenFileName
    original_get_open_file_names = QFileDialog.getOpenFileNames
    original_get_existing_directory = QFileDialog.getExistingDirectory

    def get_open_file_name(
        parent=None,
        caption="",
        directory="",
        filter="",
        initialFilter="",
        options=QFileDialog.Options(),
    ):
        options |= QFileDialog.DontUseNativeDialog
        return original_get_open_file_name(parent, caption, directory, filter, initialFilter, options)

    def get_open_file_names(
        parent=None,
        caption="",
        directory="",
        filter="",
        initialFilter="",
        options=QFileDialog.Options(),
    ):
        options |= QFileDialog.DontUseNativeDialog
        return original_get_open_file_names(parent, caption, directory, filter, initialFilter, options)

    def get_existing_directory(parent=None, caption="", directory="", options=QFileDialog.ShowDirsOnly):
        options |= QFileDialog.DontUseNativeDialog
        return original_get_existing_directory(parent, caption, directory, options)

    QFileDialog.getOpenFileName = staticmethod(get_open_file_name)
    QFileDialog.getOpenFileNames = staticmethod(get_open_file_names)
    QFileDialog.getExistingDirectory = staticmethod(get_existing_directory)
