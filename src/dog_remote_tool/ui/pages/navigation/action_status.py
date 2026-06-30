from __future__ import annotations

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QLabel, QSizePolicy

from dog_remote_tool.ui.pages.navigation.action_status_text import NavigationActionStatusTextMixin
from dog_remote_tool.ui.pages.navigation.status_helpers import _status_style
from dog_remote_tool.ui.user_console import ConsoleStatusCard


class NavigationStatusCard(ConsoleStatusCard):
    STATE_TONES = {
        "active": "running",
        "ready": "success",
        "success": "success",
        "starting": "warning",
        "paused": "warning",
        "cancelled": "neutral",
        "blocked": "danger",
        "error": "danger",
        "unknown": "neutral",
    }

    def __init__(self, text: str) -> None:
        self._legacy_text = ""
        super().__init__("", "", "")
        self.setProperty("compact", True)
        layout = self.layout()
        if layout is not None:
            layout.setContentsMargins(12, 10, 12, 10)
            layout.setSpacing(4)
        self.badge.setMinimumHeight(24)
        self.setText(text)

    def setText(self, text: str) -> None:
        self._legacy_text = text
        lines = [line.strip() for line in str(text).splitlines()]
        eyebrow = lines[0] if lines else ""
        title = lines[1] if len(lines) > 1 else eyebrow or "--"
        detail = " ".join(line for line in lines[2:] if line) or self.detail.text()
        self.eyebrow.setText(eyebrow)
        self.set_status(title, detail, self.property("tone") or "neutral")

    def text(self) -> str:
        return self._legacy_text

    def set_navigation_state(self, state: str) -> None:
        self.set_status(self.title.text(), self.detail.text(), self.STATE_TONES.get(state, "neutral"))


class NavigationActionStatusMixin(NavigationActionStatusTextMixin):
    def _status_card(self, text: str) -> NavigationStatusCard:
        label = NavigationStatusCard(text)
        label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self._set_card_style(label, "cancelled")
        return label

    def _set_card_style(self, label: QLabel, state: str) -> None:
        if hasattr(label, "set_navigation_state"):
            label.set_navigation_state(state)
            return
        bg, fg, border = _status_style(state)
        label.setStyleSheet(
            f"background:{bg};color:{fg};border:1px solid {border};border-radius:8px;padding:10px 12px;font-weight:700;"
        )

    def navigation_supported(self) -> bool:
        return "navigation" in self.profile().capabilities

    def remote_navigation_running(self, values: dict[str, str]) -> bool:
        status = values.get("STATUS", "")
        app_nav_status = values.get("APP_NAV_STATUS", "").strip()
        return status in {"active", "starting", "paused"} or app_nav_status in {"Running", "Active", "Naving"}

    def remote_navigation_paused(self, values: dict[str, str]) -> bool:
        status = values.get("STATUS", "")
        return status == "paused"

    def navigation_action_ready_reason(self, values: dict[str, str]) -> tuple[bool, str]:
        if not getattr(self, "page_active", False):
            return False, "导航页面未激活"
        if not NavigationActionStatusMixin.navigation_supported(self):
            return False, "当前设备不支持导航"
        map_pcd = self.map_pcd_path.text().strip() if hasattr(self, "map_pcd_path") else ""
        if not map_pcd:
            return False, "请先选择历史图"
        if NavigationActionStatusMixin.remote_navigation_running(self, values):
            return False, "远端已有导航任务运行，先停止或等待结束"
        if NavigationActionStatusMixin.arc_charging_detected(self, values):
            return False, "当前已检测到充电中，请先出桩"
        slot = getattr(self, "map_prepare_slot", None)
        if slot is not None and slot.is_running():
            return False, "正在初始化所选地图"
        if getattr(self, "prepared_map_pcd_path", "") != map_pcd:
            return False, "等待所选地图初始化完成"
        if not values:
            return False, "等待导航状态刷新"
        status_map_pcd = values.get("MAP_PCD", "").strip()
        if status_map_pcd != map_pcd:
            return False, "等待当前地图状态刷新"
        if values.get("MAP_OK") != "1":
            return False, "导航地图未确认可用"
        if values.get("LOCALIZATION_READY") != "1":
            return False, "等待连续定位正常"
        if values.get("NAV_PROCESS") != "1" or values.get("START_NAV_SUBSCRIBERS", "0") == "0":
            return False, "导航栈未就绪"
        if values.get("STATUS") in {"blocked", "error", "unknown"}:
            return False, values.get("TEXT", "导航状态未就绪")
        return True, "导航状态已就绪"

    def arc_charging_detected(self, values: dict[str, str] | None = None) -> bool:
        values = values or {}
        if bool(getattr(getattr(self, "device_bar", None), "battery_last_charging", False)):
            return True
        dock_state = values.get("ARC_DOCK_STATE", "")
        dock_text = values.get("ARC_DOCK_TEXT", "")
        app_dock = values.get("ARC_APP_DOCK_STATUS", "")
        app_alg = values.get("ARC_APP_ALG_STATUS", "")
        return dock_state == "2" or dock_text == "充电中" or app_dock == "Charging" or app_alg == "Charging"

    def mapped_dock_ready_reason(self, values: dict[str, str]) -> tuple[bool, str]:
        if NavigationActionStatusMixin.arc_charging_detected(self, values):
            return False, "当前已检测到充电中，请使用出桩"
        if not getattr(self, "page_active", False):
            return False, "导航页面未激活"
        if not NavigationActionStatusMixin.navigation_supported(self):
            return False, "当前设备不支持 ARC/导航"
        if not self.selected_map_pgm():
            return False, "请先选择历史图"
        if not getattr(self, "charging_docks", []):
            return False, "当前地图未标记充电桩"
        if NavigationActionStatusMixin.remote_navigation_running(self, values):
            return True, "远端导航运行中，可终止当前导航并切换到有图进桩"
        ready, reason = NavigationActionStatusMixin.navigation_action_ready_reason(self, values)
        if not ready:
            return False, reason
        return True, "当前地图已标记充电桩，定位正常"

    def unmapped_dock_ready_reason(self, values: dict[str, str]) -> tuple[bool, str]:
        if NavigationActionStatusMixin.arc_charging_detected(self, values):
            return False, "当前已检测到充电中，请使用出桩"
        if not getattr(self, "page_active", False):
            return False, "导航页面未激活"
        if not NavigationActionStatusMixin.navigation_supported(self):
            return False, "当前设备不支持 ARC/导航"
        if NavigationActionStatusMixin.remote_navigation_running(self, values):
            return False, "远端已有导航任务运行，先停止或等待结束"
        return True, "请确认机器狗位于充电桩二维码正前方"

    def arc_undock_ready_reason(self, values: dict[str, str]) -> tuple[bool, str]:
        if not getattr(self, "page_active", False):
            return False, "导航页面未激活"
        if not NavigationActionStatusMixin.navigation_supported(self):
            return False, "当前设备不支持 ARC/导航"
        if not NavigationActionStatusMixin.arc_charging_detected(self, values):
            return False, "当前未检测到充电状态"
        if NavigationActionStatusMixin.remote_navigation_running(self, values):
            return False, "远端已有导航任务运行，先停止或等待结束"
        return True, "当前检测到充电中"

    def mapped_recharge_action_state(self, values: dict[str, str]) -> tuple[str, str, bool, str]:
        undock_ready, undock_reason = NavigationActionStatusMixin.arc_undock_ready_reason(self, values)
        if NavigationActionStatusMixin.arc_charging_detected(self, values):
            return "undock", "出桩", undock_ready, undock_reason
        mapped_ready, mapped_reason = NavigationActionStatusMixin.mapped_dock_ready_reason(self, values)
        return "dock", "有图进桩", mapped_ready, mapped_reason

    def arc_calibration_ready_reason(self, values: dict[str, str]) -> tuple[bool, str]:
        if not getattr(self, "page_active", False):
            return False, "导航页面未激活"
        if not NavigationActionStatusMixin.navigation_supported(self):
            return False, "当前设备不支持 ARC/导航"
        if NavigationActionStatusMixin.remote_navigation_running(self, values):
            return False, "远端已有导航任务运行，先停止或等待结束"
        return True, "可以发送充电桩标定请求"

    def arc_mark_ready_reason(self, values: dict[str, str]) -> tuple[bool, str]:
        if not getattr(self, "page_active", False):
            return False, "导航页面未激活"
        if not NavigationActionStatusMixin.navigation_supported(self):
            return False, "当前设备不支持 ARC/导航"
        if NavigationActionStatusMixin.remote_navigation_running(self, values):
            return False, "远端已有导航任务运行，先停止或等待结束"
        map_pcd = self.map_pcd_path.text().strip()
        if not map_pcd:
            return False, "请先选择要写入的地图"
        slot = getattr(self, "map_prepare_slot", None)
        if slot is not None and slot.is_running():
            return False, "正在初始化所选地图"
        if getattr(self, "prepared_map_pcd_path", "") != map_pcd:
            return False, "请先初始化当前地图，避免写入错误地图"
        if not values:
            return False, "等待导航状态刷新"
        status_map_pcd = values.get("MAP_PCD", "").strip()
        if status_map_pcd and status_map_pcd != map_pcd:
            return False, "等待当前地图状态刷新"
        if values.get("MAP_OK") != "1":
            return False, "导航地图未确认可用"
        if values.get("LOCALIZATION_READY") not in {"1", "true", "True"}:
            return False, "等待定位状态就绪后再标记"
        return True, "请确认机器狗正对充电桩，二维码/桩体稳定可见后再标记"
