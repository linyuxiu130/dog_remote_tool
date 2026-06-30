from __future__ import annotations

from PyQt5.QtCore import QTimer

from dog_remote_tool.core.profiles import ProductProfile
from dog_remote_tool.ui.device_bar_connection import CONNECTION_PENDING_STYLE
from dog_remote_tool.ui.label_status import set_label_text_style
from dog_remote_tool.ui.product_selector import is_retired_l2_s100_host, looks_accidental_stored_profile_value
from dog_remote_tool.ui.widget_roles import set_widget_text_tooltip


class DeviceBarProfileMixin:
    def current_profile(self) -> ProductProfile:
        base = self.selector.profile()
        return ProductProfile(
            key=base.key,
            label=base.label,
            platform=base.platform,
            host=self.host.text().strip() or base.host,
            user=self.user.text().strip() or base.user,
            password=self.password.text() or base.password,
            home=base.home,
            bag_storage=base.bag_storage,
            ros_domain_id=base.ros_domain_id,
            rmw=base.rmw,
            jump_host=base.jump_host,
            jump_user=base.jump_user,
            jump_password=base.jump_password,
            capabilities=base.capabilities,
        )

    def switch_profile_key(self, key: str) -> bool:
        if key == self.selector.current_key():
            return False
        self.selector.set_key(key)
        if key != self.selector.current_key():
            return False
        self._load_profile(self.selector.profile())
        return True

    def set_disabled_platform_keys(self, platform_keys: set[str]) -> None:
        self.selector.set_disabled_platforms(platform_keys)

    def _load_profile(self, profile: ProductProfile) -> None:
        self.loading_profile = True
        self.battery_slot.stop_async()
        self.connection_slot.stop_async()
        self.host.setText(self._stored_value(profile.key, "host", profile.host))
        self.user.setText(self._stored_value(profile.key, "user", profile.user))
        self.password.setText(self._stored_value(profile.key, "password", profile.password))
        self.loading_profile = False
        set_label_text_style(self.status, "未验证", CONNECTION_PENDING_STYLE)
        set_widget_text_tooltip(self.battery, "电量 --", "")
        self.battery_last_percent = None
        self.battery_last_charging = False
        self.last_battery_probe = 0.0
        self.last_battery_probe_target = ""
        self._set_battery_style(None)
        current = self.current_profile()
        cached = self.battery_cache.get(self._battery_cache_key(current))
        if cached is not None:
            self._show_battery(cached)
        self.save_current_profile()
        self.profile_changed.emit(current)
        request_id = self.battery_slot.request_id
        QTimer.singleShot(900, lambda: self.refresh_battery(request_id))
        connection_id = self.connection_slot.request_id
        QTimer.singleShot(1400, lambda: self.test_connection(False, connection_id))

    def schedule_connection_test(self) -> None:
        if self.loading_profile:
            return
        self.save_current_profile()
        self._stop_connection_process()
        set_label_text_style(self.status, "未验证", CONNECTION_PENDING_STYLE)
        self.connection_edit_timer.start()

    def _stored_value(self, key: str, field: str, default: str) -> str:
        setting_key = f"device_bar/profiles/{key}/{field}"
        value = self.settings.value(setting_key, default, type=str) or default
        if is_retired_l2_s100_host(key, field, value, default) or looks_accidental_stored_profile_value(field, value, default):
            self.settings.setValue(setting_key, default)
            return default
        return value

    def save_current_profile(self) -> None:
        profile = self.current_profile()
        self.settings.setValue("device_bar/current_key", profile.key)
        self.settings.setValue(f"device_bar/profiles/{profile.key}/host", profile.host)
        self.settings.setValue(f"device_bar/profiles/{profile.key}/user", profile.user)
        self.settings.setValue(f"device_bar/profiles/{profile.key}/password", profile.password)
