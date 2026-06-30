from __future__ import annotations

from PyQt5.QtWidgets import QLabel

from dog_remote_tool.ui.widget_roles import repolish_widget, set_widget_role, set_widget_text_style, widget_stylesheet, widget_text

LABEL_STATUS_OBJECT_NAMES = {
    "ok": "BagStatusOk",
    "warn": "BagStatusWarn",
    "bad": "BagStatusBad",
}


def label_status_object_name(state: str) -> str:
    return LABEL_STATUS_OBJECT_NAMES.get(state, LABEL_STATUS_OBJECT_NAMES["warn"])


def repolish_label(label: QLabel) -> None:
    repolish_widget(label)


def apply_label_status(label: QLabel, state: str) -> None:
    set_widget_role(label, label_status_object_name(state))


def label_text(label) -> str:
    return widget_text(label)


def label_stylesheet(label) -> str:
    return widget_stylesheet(label)


def set_label_text_style(label, text: str, style: str) -> bool:
    return set_widget_text_style(label, text, style)
