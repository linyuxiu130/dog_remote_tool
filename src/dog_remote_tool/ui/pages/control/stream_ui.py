from __future__ import annotations

import json

from PyQt5.QtCore import QProcess
from PyQt5.QtWidgets import QLabel, QPushButton

from dog_remote_tool.ui.label_status import apply_label_status
from dog_remote_tool.ui.widget_roles import set_button_role as apply_button_role


def stream_exit_text(code: int, prefix: str = "") -> str:
    if code == 0:
        return f"{prefix}未连接"
    return f"{prefix}已断开({code})"


def stream_exit_state(code: int) -> str:
    return "warn" if code == 0 else "bad"


def set_button_role(button: QPushButton, text: str, role: str) -> None:
    apply_button_role(button, text, role)


def set_label_status(label: QLabel, state: str) -> None:
    apply_label_status(label, state)


def write_json_line(process: QProcess | None, payload: dict) -> bool:
    if not process or process.state() == QProcess.NotRunning:
        return False
    process.write((json.dumps(payload, separators=(",", ":")) + "\n").encode("utf-8"))
    return True
