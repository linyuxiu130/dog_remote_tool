from __future__ import annotations

from importlib import import_module


def _remote_access_page_module():
    return import_module("dog_remote_tool.ui.pages.remote_access.page")


class RemoteAccessLifecycleMixin:
    def _profile_changed(self, _profile) -> bool:
        changed = self._stop_async_processes(include_connect=True)
        changed = self._refresh_wifi_controls() or changed
        if self.page_active:
            changed = self.refresh_public_ssid() or changed
            changed = self.refresh_public_status() or changed
            changed = self.refresh_wifi_status() or changed
        return changed

    def activate_page(self) -> bool:
        if self.page_active:
            return False
        self.page_active = True
        timer = _remote_access_page_module().QTimer
        timer.singleShot(300, self.refresh_public_status)
        timer.singleShot(450, self.refresh_wifi_status)
        timer.singleShot(600, self.refresh_public_ssid)
        return True

    def deactivate_page(self) -> bool:
        changed = self.page_active
        self.page_active = False
        stopped = self._stop_async_processes(include_connect=False)
        return changed or stopped

    def _stop_async_processes(self, *, include_connect: bool = False) -> bool:
        stopped = (
            self.public_status_slot.is_running()
            or self.public_ssid_slot.is_running()
            or self.wifi_status_slot.is_running()
            or self.wifi_scan_slot.is_running()
            or (include_connect and self.wifi_connect_slot.is_running())
        )
        self.public_status_slot.stop()
        self.public_ssid_slot.stop()
        self.wifi_status_slot.stop()
        self.wifi_scan_slot.stop()
        if include_connect:
            self.wifi_connect_slot.stop()
        return stopped

    def shutdown_processes(self) -> bool:
        changed = self.page_active or not self.public_status_shutdown
        self.page_active = False
        self.public_status_shutdown = True
        stopped = self._stop_async_processes(include_connect=True)
        return changed or stopped
