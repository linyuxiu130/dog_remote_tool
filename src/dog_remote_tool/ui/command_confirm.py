from __future__ import annotations

from PyQt5.QtWidgets import QMessageBox, QWidget

from dog_remote_tool.core.shell import CommandSpec


def command_display_command(spec: CommandSpec) -> str:
    return spec.display_command or f"执行：{spec.title}"


def confirm_dangerous_action(
    parent: QWidget | None,
    title: str,
    detail: str,
    *,
    confirm_text: str = "确认继续？",
) -> bool:
    message = f"{detail.strip()}\n\n{confirm_text}".strip()
    answer = QMessageBox.question(
        parent,
        title,
        message,
        QMessageBox.Yes | QMessageBox.Cancel,
        QMessageBox.Cancel,
    )
    return answer == QMessageBox.Yes


def confirm_command_spec(parent: QWidget, spec: CommandSpec) -> bool:
    if not spec.dangerous:
        return True
    message = f"即将执行：{spec.title}\n该操作可能影响远端设备。"
    if spec.description:
        message = f"{message}\n\n{spec.description}"
    return confirm_dangerous_action(
        parent,
        "确认危险操作",
        message,
        confirm_text="请确认现场安全后继续。",
    )
