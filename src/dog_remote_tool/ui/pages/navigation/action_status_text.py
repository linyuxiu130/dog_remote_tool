from __future__ import annotations

class NavigationActionStatusTextMixin:
    def _arc_charging_status_detected(self, values: dict[str, str]) -> bool:
        if bool(getattr(getattr(self, "device_bar", None), "battery_last_charging", False)):
            return True
        return (
            values.get("ARC_DOCK_STATE", "") == "2"
            or values.get("ARC_DOCK_TEXT", "") == "充电中"
            or values.get("ARC_APP_DOCK_STATUS", "") == "Charging"
            or values.get("ARC_APP_ALG_STATUS", "") == "Charging"
        )

    def current_navigation_status_text(self, values: dict[str, str], fallback: str = "") -> str:
        if NavigationActionStatusTextMixin._arc_charging_status_detected(self, values):
            return "✓ 充电中\nARC 已进入充电状态"
        app_nav_status = values.get("APP_NAV_STATUS", "").strip()
        if app_nav_status:
            icon = NavigationActionStatusTextMixin.navigation_status_icon(self, values, values.get("STATUS", ""))
            return f"{icon} {app_nav_status}"
        status = values.get("STATUS", "")
        icon = NavigationActionStatusTextMixin.navigation_status_icon(self, values, status)
        headline = NavigationActionStatusTextMixin.navigation_status_headline(self, values, fallback)
        return f"{icon} {fallback or '等待导航状态更新'}"

    def navigation_status_headline(self, values: dict[str, str], fallback: str = "") -> str:
        status = values.get("STATUS", "")
        text = values.get("TEXT", "") or fallback
        if text:
            return text
        return "等待状态刷新"

    def navigation_status_icon(self, values: dict[str, str], status: str = "") -> str:
        if NavigationActionStatusTextMixin._arc_charging_status_detected(self, values):
            return "✓"
        app_nav_status = values.get("APP_NAV_STATUS", "").strip()
        if app_nav_status in {"Succeeded"}:
            return "✓"
        if app_nav_status in {"Error", "NavError", "LocError", "Failed"}:
            return "!"
        if app_nav_status in {"Running", "Active", "Naving"}:
            return "▶"
        if app_nav_status in {"Stopped", "StandBy"}:
            return "●"
        status = status or values.get("STATUS", "")
        if status in {"error", "blocked", "unknown"}:
            return "!"
        if status == "success":
            return "✓"
        if status == "cancelled":
            return "■"
        if status in {"starting", "paused"}:
            return "●"
        if status == "active":
            return "▶"
        if status == "ready":
            return "●"
        return "?"

    def _compact_number(self, value: str) -> str:
        try:
            number = float(value)
        except ValueError:
            return value
        if number.is_integer():
            return str(int(number))
        return f"{number:.2f}".rstrip("0").rstrip(".")

    def navigation_current_card_state(self, values: dict[str, str], status: str = "") -> str:
        if NavigationActionStatusTextMixin._arc_charging_status_detected(self, values):
            return "success"
        app_nav_status = values.get("APP_NAV_STATUS", "").strip()
        if app_nav_status in {"Running", "Active", "Naving"}:
            return "active"
        if app_nav_status in {"Succeeded"}:
            return "success"
        if app_nav_status in {"Error", "NavError", "LocError", "Failed"}:
            return "error"
        return status or values.get("STATUS", "unknown")
