from __future__ import annotations

from PyQt5.QtCore import pyqtSignal
from PyQt5.QtWidgets import QHBoxLayout, QLabel, QPushButton, QWidget

from ..core.profiles import ProductProfile, get_product


def looks_accidental_stored_profile_value(field: str, value: str, default: str) -> bool:
    if not value or value == default:
        return False
    default_fields = {
        "host": {"192.168.234.1", "192.168.234.234", "192.168.168.100"},
        "user": {"robot", "firefly"},
        "password": {"1", "bot", "firefly"},
    }
    if default not in default_fields.get(field, set()):
        return False
    repeated_default = value.startswith(default * 2)
    suspicious_length = len(value) > max(16, len(default) * 3)
    non_ascii = any(ord(ch) > 127 for ch in value)
    return value.startswith(default) and (repeated_default or suspicious_length or non_ascii)


def is_retired_l2_s100_host(key: str, field: str, value: str, default: str) -> bool:
    return key == "xg2_s100" and field == "host" and default == "192.168.168.100" and value.startswith("192.168.144.")


class ProductSelector(QWidget):
    changed = pyqtSignal(object)

    FAMILIES = (
        ("xg_l1", "小狗L1"),
        ("xg_l2", "小狗L2"),
        ("zg_lidar", "中狗激光"),
        ("zg_surround", "中狗环视"),
    )
    PLATFORMS = (
        ("rk3588", "RK3588"),
        ("nx_s100", "NX/S100"),
    )
    COMBINATIONS = {
        ("xg_l1", "rk3588"): "xg3588",
        ("xg_l1", "nx_s100"): "xg1_nx",
        ("xg_l2", "rk3588"): "xg2_3588",
        ("xg_l2", "nx_s100"): "xg2_s100",
        ("zg_lidar", "rk3588"): "zg3588",
        ("zg_lidar", "nx_s100"): "zg_lidar_nx",
        ("zg_surround", "rk3588"): "zg_surround_3588",
        ("zg_surround", "nx_s100"): "zg_surround_s100",
    }
    KEY_TO_SELECTION = {key: selection for selection, key in COMBINATIONS.items()}

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        self.family_key = "xg_l1"
        self.platform_key = "rk3588"
        self._syncing = False
        self.family_buttons: dict[str, QPushButton] = {}
        self.platform_buttons: dict[str, QPushButton] = {}
        self.disabled_platform_keys: set[str] = set()

        family_label = QLabel("类型")
        family_label.setObjectName("FieldLabel")
        layout.addWidget(family_label)
        for key, label in self.FAMILIES:
            button = self._make_segment_button(label)
            button.clicked.connect(lambda _checked=False, family=key: self._select_family(family))
            self.family_buttons[key] = button
            layout.addWidget(button)

        platform_label = QLabel("平台")
        platform_label.setObjectName("FieldLabel")
        layout.addWidget(platform_label)
        for key, label in self.PLATFORMS:
            button = self._make_segment_button(label)
            button.clicked.connect(lambda _checked=False, platform=key: self._select_platform(platform))
            self.platform_buttons[key] = button
            layout.addWidget(button)

        layout.addStretch(1)
        self._refresh_buttons()

    def profile(self) -> ProductProfile:
        return get_product(self._current_key())

    def current_key(self) -> str:
        return self._current_key()

    def set_key(self, key: str) -> None:
        selection = self.KEY_TO_SELECTION.get(key)
        if not selection:
            return
        self.family_key, self.platform_key = selection
        self._refresh_buttons()

    def set_disabled_platforms(self, platform_keys: set[str]) -> None:
        self.disabled_platform_keys = set(platform_keys)
        self._refresh_buttons()

    def _make_segment_button(self, text: str) -> QPushButton:
        button = QPushButton(text)
        button.setObjectName("SegmentButton")
        button.setCheckable(True)
        button.setMinimumWidth(74)
        return button

    def _current_key(self) -> str:
        return self.COMBINATIONS[(self.family_key, self.platform_key)]

    def _available_platforms(self, family_key: str | None = None) -> list[str]:
        family = family_key or self.family_key
        return [platform for platform, _label in self.PLATFORMS if (family, platform) in self.COMBINATIONS]

    def _select_family(self, family_key: str) -> None:
        if self._syncing:
            return
        self.family_key = family_key
        if self.platform_key not in self._available_platforms(family_key):
            self.platform_key = self._available_platforms(family_key)[0]
        self._refresh_buttons()
        self._emit_changed()

    def _select_platform(self, platform_key: str) -> None:
        if self._syncing or platform_key in self.disabled_platform_keys or platform_key not in self._available_platforms():
            self._refresh_buttons()
            return
        self.platform_key = platform_key
        self._refresh_buttons()
        self._emit_changed()

    def _refresh_buttons(self) -> None:
        self._syncing = True
        try:
            available_platforms = set(self._available_platforms())
            for key, button in self.family_buttons.items():
                button.setChecked(key == self.family_key)
            for key, button in self.platform_buttons.items():
                button.setEnabled(key in available_platforms and key not in self.disabled_platform_keys)
                button.setChecked(key == self.platform_key)
        finally:
            self._syncing = False

    def _emit_changed(self) -> None:
        self.changed.emit(self.profile())
