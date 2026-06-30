from __future__ import annotations


def repolish_widget(widget) -> bool:
    style = widget.style() if callable(getattr(widget, "style", None)) else None
    if style is None:
        return False
    style.unpolish(widget)
    style.polish(widget)
    return True


def set_widget_role(widget, role: str) -> bool:
    if not callable(getattr(widget, "setObjectName", None)):
        return False
    if widget_object_name(widget) == role:
        return False
    widget.setObjectName(role)
    repolish_widget(widget)
    return True


def set_button_role(button, text: str, role: str) -> bool:
    text_changed = widget_text(button) != text
    if text_changed:
        button.setText(text)
    return set_widget_role(button, role) or text_changed


def set_widget_text(widget, text: str) -> bool:
    changed = widget_text(widget) != text
    widget.setText(text)
    return changed


def set_widget_texts(items) -> bool:
    changed = False
    for widget, text in items:
        changed = set_widget_text(widget, text) or changed
    return changed


def set_widget_text_style(widget, text: str, style: str) -> bool:
    changed = widget_text(widget) != text or widget_stylesheet(widget) != style
    widget.setText(text)
    widget.setStyleSheet(style)
    return changed


def set_widget_text_style_tooltip(widget, text: str, style: str, tooltip: str) -> bool:
    changed = (
        widget_text(widget) != text
        or widget_stylesheet(widget) != style
        or widget_tooltip(widget) != tooltip
    )
    widget.setText(text)
    widget.setStyleSheet(style)
    widget.setToolTip(tooltip)
    return changed


def set_widget_text_tooltip(widget, text: str, tooltip: str) -> bool:
    changed = widget_text(widget) != text or widget_tooltip(widget) != tooltip
    widget.setText(text)
    widget.setToolTip(tooltip)
    return changed


def widget_text(widget, default: str = "") -> str:
    text = getattr(widget, "text", None)
    if callable(text):
        return text()
    if text is not None:
        return text
    return getattr(widget, "_text", default)


def widget_tooltip(widget, default: str = "") -> str:
    tooltip = getattr(widget, "toolTip", None)
    if callable(tooltip):
        return tooltip()
    return getattr(widget, "tooltip", default)


def widget_stylesheet(widget, default: str = "") -> str:
    style_sheet = getattr(widget, "styleSheet", None)
    if callable(style_sheet):
        return style_sheet()
    styles = getattr(widget, "styles", None)
    if styles:
        return styles[-1]
    return getattr(widget, "style_sheet", default)


def widget_object_name(widget, default: str = "") -> str:
    object_name = getattr(widget, "objectName", None)
    if callable(object_name):
        return object_name()
    return getattr(widget, "object_name", default)


def widget_enabled(widget, default: bool = False) -> bool:
    enabled = getattr(widget, "isEnabled", None)
    if callable(enabled):
        return enabled()
    return getattr(widget, "enabled", default)


def widget_visible(widget, default: bool = False) -> bool:
    visible = getattr(widget, "isVisible", None)
    if callable(visible):
        return visible()
    return getattr(widget, "visible", default)
