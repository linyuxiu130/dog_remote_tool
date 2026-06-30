from dog_remote_tool.ui.label_status import (
    LABEL_STATUS_OBJECT_NAMES,
    apply_label_status,
    label_stylesheet,
    label_text,
    label_status_object_name,
    set_label_text_style,
)


class _FakeTextStyleLabel:
    def __init__(self, text=""):
        self.text = text
        self.styles = []

    def setText(self, text):
        self.text = text

    def setStyleSheet(self, style):
        self.styles.append(style)


class _FakeStyle:
    def __init__(self):
        self.unpolished = 0
        self.polished = 0

    def unpolish(self, _widget):
        self.unpolished += 1

    def polish(self, _widget):
        self.polished += 1


class _FakeRoleLabel:
    def __init__(self):
        self.object_name = ""
        self.style_obj = _FakeStyle()

    def setObjectName(self, name):
        self.object_name = name

    def style(self):
        return self.style_obj


def test_label_status_object_name_maps_known_states_and_falls_back_to_warn():
    assert LABEL_STATUS_OBJECT_NAMES == {
        "ok": "BagStatusOk",
        "warn": "BagStatusWarn",
        "bad": "BagStatusBad",
    }
    assert label_status_object_name("ok") == "BagStatusOk"
    assert label_status_object_name("bad") == "BagStatusBad"
    assert label_status_object_name("missing") == "BagStatusWarn"


def test_apply_label_status_sets_role_and_repolishes():
    label = _FakeRoleLabel()

    apply_label_status(label, "ok")

    assert label.object_name == "BagStatusOk"
    assert label.style_obj.unpolished == 1
    assert label.style_obj.polished == 1


def test_set_label_text_style_returns_change_result_for_fake_labels():
    label = _FakeTextStyleLabel("旧状态")

    assert label_text(label) == "旧状态"
    assert label_stylesheet(label) == ""
    assert set_label_text_style(label, "公网状态：检测中", "color:#607085;") is True
    assert label_text(label) == "公网状态：检测中"
    assert label_stylesheet(label) == "color:#607085;"
    assert set_label_text_style(label, "公网状态：检测中", "color:#607085;") is False
