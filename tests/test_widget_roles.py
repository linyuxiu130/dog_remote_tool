from dog_remote_tool.ui.widget_roles import (
    repolish_widget,
    set_button_role,
    set_widget_role,
    set_widget_text,
    set_widget_text_style,
    set_widget_text_style_tooltip,
    set_widget_text_tooltip,
    set_widget_texts,
    widget_enabled,
    widget_object_name,
    widget_text,
    widget_stylesheet,
    widget_tooltip,
    widget_visible,
)


class _FakeStyle:
    def __init__(self):
        self.unpolished = 0
        self.polished = 0

    def unpolish(self, _widget):
        self.unpolished += 1

    def polish(self, _widget):
        self.polished += 1


class _FakeWidget:
    def __init__(self):
        self.object_name = ""
        self.text = ""
        self.tooltip = ""
        self.enabled = True
        self.style_sheet = ""
        self.style_obj = _FakeStyle()

    def setObjectName(self, name):
        self.object_name = name

    def setText(self, text):
        self.text = text

    def setStyleSheet(self, style):
        self.style_sheet = style

    def setToolTip(self, tooltip):
        self.tooltip = tooltip

    def style(self):
        return self.style_obj

    def objectName(self):
        return self.object_name

    def toolTip(self):
        return self.tooltip

    def styleSheet(self):
        return self.style_sheet

    def isEnabled(self):
        return self.enabled

    def isVisible(self):
        return True


class _NoStyleWidget:
    def __init__(self):
        self.object_name = ""

    def setObjectName(self, name):
        self.object_name = name


class _FakeTextOnlyWidget:
    def __init__(self):
        self._text = "按钮"
        self.object_name = "Primary"
        self.tooltip = "提示"
        self.styles = ["color:#607085;"]
        self.enabled = False
        self.visible = False


def test_widget_role_helpers_repolish_and_set_button_text():
    widget = _FakeWidget()

    assert repolish_widget(widget) is True
    assert widget.style_obj.unpolished == 1
    assert widget.style_obj.polished == 1
    assert set_widget_role(widget, "Primary") is True
    assert widget.object_name == "Primary"
    assert widget.style_obj.unpolished == 2
    assert widget.style_obj.polished == 2
    assert set_button_role(widget, "开始", "SoftPrimary") is True
    assert widget.text == "开始"
    assert widget.object_name == "SoftPrimary"


def test_widget_role_helpers_skip_duplicate_role_repolish():
    widget = _FakeWidget()

    assert set_widget_role(widget, "Primary") is True
    assert set_widget_role(widget, "Primary") is False
    assert widget.style_obj.unpolished == 1
    assert widget.style_obj.polished == 1


def test_widget_role_helpers_tolerate_missing_style_method():
    widget = _NoStyleWidget()

    assert repolish_widget(widget) is False
    assert set_widget_role(widget, "Muted") is True
    assert widget.object_name == "Muted"


def test_widget_read_helpers_support_qt_methods_and_fake_attributes():
    widget = _FakeWidget()
    widget.text = "标签"
    widget.object_name = "Ready"
    widget.tooltip = "说明"
    widget.style_sheet = "font-weight:700;"
    widget.enabled = True

    assert widget_text(widget) == "标签"
    assert widget_tooltip(widget) == "说明"
    assert widget_stylesheet(widget) == "font-weight:700;"
    assert widget_object_name(widget) == "Ready"
    assert widget_enabled(widget) is True
    assert widget_visible(widget) is True

    fallback = _FakeTextOnlyWidget()
    assert widget_text(fallback) == "按钮"
    assert widget_tooltip(fallback) == "提示"
    assert widget_stylesheet(fallback) == "color:#607085;"
    assert widget_object_name(fallback) == "Primary"
    assert widget_enabled(fallback, True) is False
    assert widget_visible(fallback, True) is False


def test_widget_text_helpers_return_change_status():
    first = _FakeWidget()
    second = _FakeWidget()
    first.text = "旧"
    second.text = "不变"

    assert set_widget_text(first, "新") is True
    assert first.text == "新"
    assert set_widget_text(first, "新") is False

    assert set_widget_texts(((first, "新"), (second, "不变"))) is False
    assert set_widget_texts(((first, "新2"), (second, "不变"))) is True
    assert first.text == "新2"
    assert second.text == "不变"


def test_widget_text_style_helper_returns_change_status():
    widget = _FakeWidget()
    widget.text = "旧"
    widget.style_sheet = "color:#8a5a00;"

    assert set_widget_text_style(widget, "新", "color:#607085;") is True
    assert widget.text == "新"
    assert widget.style_sheet == "color:#607085;"
    assert set_widget_text_style(widget, "新", "color:#607085;") is False


def test_widget_text_style_tooltip_helper_returns_change_status():
    widget = _FakeWidget()
    widget.text = "旧"
    widget.style_sheet = "color:#8a5a00;"
    widget.tooltip = "旧提示"

    assert set_widget_text_style_tooltip(widget, "新", "color:#607085;", "新提示") is True
    assert widget.text == "新"
    assert widget.style_sheet == "color:#607085;"
    assert widget.tooltip == "新提示"
    assert set_widget_text_style_tooltip(widget, "新", "color:#607085;", "新提示") is False


def test_widget_text_tooltip_helper_returns_change_status():
    widget = _FakeWidget()
    widget.text = "旧"
    widget.tooltip = "旧提示"

    assert set_widget_text_tooltip(widget, "新", "新提示") is True
    assert widget.text == "新"
    assert widget.tooltip == "新提示"
    assert set_widget_text_tooltip(widget, "新", "新提示") is False
