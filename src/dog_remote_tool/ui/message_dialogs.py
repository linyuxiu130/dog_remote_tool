from __future__ import annotations

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QDialog, QFrame, QHBoxLayout, QLabel, QMessageBox, QPushButton, QVBoxLayout, QWidget


BUTTON_LABELS = {
    QMessageBox.Ok: "确定",
    QMessageBox.Yes: "确定",
    QMessageBox.No: "取消",
    QMessageBox.Cancel: "取消",
    QMessageBox.Close: "关闭",
}
BUTTON_ORDER = (QMessageBox.No, QMessageBox.Cancel, QMessageBox.Close, QMessageBox.Ok, QMessageBox.Yes)
DANGER_TITLES = ("删除", "失败", "错误", "异常", "警告", "拒绝", "无法", "风险")


class StyledMessageDialog(QDialog):
    def __init__(
        self,
        icon: QMessageBox.Icon,
        parent: QWidget | None,
        title: str,
        text: str,
        buttons: QMessageBox.StandardButtons,
        default_button: QMessageBox.StandardButton = QMessageBox.NoButton,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("StyledMessageDialog")
        self.setWindowTitle(title)
        self.setModal(True)
        self.setMinimumWidth(460)
        self.result_button = default_button if default_button != QMessageBox.NoButton else QMessageBox.NoButton
        self._default_button = default_button
        self._message_buttons: list[QMessageBox.StandardButton] = []

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        surface = QFrame()
        surface.setObjectName("MessageDialogSurface")
        layout = QVBoxLayout(surface)
        layout.setContentsMargins(24, 18, 24, 16)
        layout.setSpacing(10)
        root.addWidget(surface)

        title_label = QLabel(title)
        title_label.setObjectName("DialogTitle")
        title_label.setWordWrap(True)
        title_label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        layout.addWidget(title_label)

        body = QLabel(self._display_text(title, text, icon))
        body.setObjectName("MessageDialogText")
        body.setWordWrap(True)
        body.setTextInteractionFlags(Qt.TextSelectableByMouse)
        body.setMinimumWidth(408)
        body.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        layout.addWidget(body)

        footer = QFrame()
        footer.setObjectName("MessageDialogFooter")
        footer_layout = QHBoxLayout(footer)
        footer_layout.setContentsMargins(0, 8, 0, 0)
        footer_layout.setSpacing(8)
        footer_layout.addStretch(1)

        specs = self._button_specs(buttons)
        if not specs:
            specs = [QMessageBox.Ok]
        if self.result_button == QMessageBox.NoButton:
            self.result_button = specs[-1]

        is_danger = any(word in title for word in DANGER_TITLES)
        for standard_button in specs:
            button = QPushButton(BUTTON_LABELS.get(standard_button, "确定"))
            button.setMinimumWidth(92)
            if standard_button in (QMessageBox.Ok, QMessageBox.Yes):
                button.setObjectName("Danger" if is_danger and standard_button == QMessageBox.Yes else "Primary")
            if standard_button == self._default_button or (
                self._default_button == QMessageBox.NoButton and standard_button == specs[-1]
            ):
                button.setDefault(True)
                button.setAutoDefault(True)
            button.clicked.connect(lambda _checked=False, value=standard_button: self._finish(value))
            footer_layout.addWidget(button)
        layout.addWidget(footer)

    @staticmethod
    def _display_text(title: str, text: str, icon: QMessageBox.Icon) -> str:
        stripped_title = title.strip()
        stripped_text = text.strip()
        if icon == QMessageBox.Question and stripped_title and stripped_text.startswith(stripped_title):
            rest = stripped_text[len(stripped_title):].strip()
            rest = rest.rstrip("?？").strip()
            if rest:
                return f"确定要{stripped_title} {rest} 吗？"
        return stripped_text

    def reject(self) -> None:
        for candidate in (QMessageBox.Cancel, QMessageBox.No, QMessageBox.Close):
            if candidate in self._button_specs_value:
                self.result_button = candidate
                break
        super().reject()

    @property
    def _button_specs_value(self) -> list[QMessageBox.StandardButton]:
        return self._message_buttons or [QMessageBox.Ok]

    def _button_specs(self, buttons: QMessageBox.StandardButtons) -> list[QMessageBox.StandardButton]:
        specs = [button for button in BUTTON_ORDER if int(buttons) & int(button)]
        self._message_buttons = specs
        return specs

    def _finish(self, button: QMessageBox.StandardButton) -> None:
        self.result_button = button
        self.accept()


def polish_message_buttons(box: QMessageBox) -> None:
    primary_buttons = {QMessageBox.Ok, QMessageBox.Yes}
    is_danger = any(text in box.windowTitle() for text in DANGER_TITLES)
    for standard_button, label in BUTTON_LABELS.items():
        button = box.button(standard_button)
        if button is None:
            continue
        button.setText(label)
        button.setMinimumWidth(88)
        if standard_button in primary_buttons:
            button.setObjectName("Danger" if is_danger and standard_button == QMessageBox.Yes else "Primary")
