from __future__ import annotations

from dog_remote_tool.modules import mapping
from dog_remote_tool.modules import navigation
from dog_remote_tool.ui.pages.navigation.page_refs import navigation_page_class, navigation_page_module


class NavigationArcActionsMixin:
    def make_start_arc_calibration(self) -> bool:
        page = navigation_page_class()
        ready, reason = page.arc_calibration_ready_reason(self, self.last_status_values or {})
        if not ready:
            navigation_page_module().QMessageBox.information(self, "暂不能标定充电桩", reason)
            return False
        started = self.run_robot_task_spec(navigation.start_arc_calibration_command(self.profile()), "充电桩标定中")
        if started:
            page.log_navigation_event(self, "[ARC] 已开始充电桩标定")
        return started

    def make_mark_charging_dock(self) -> bool:
        page = navigation_page_class()
        ready, reason = page.arc_mark_ready_reason(self, self.last_status_values or {})
        if not ready:
            navigation_page_module().QMessageBox.information(self, "暂不能标记充电桩", reason)
            return False
        map_pcd = self.map_pcd_path.text().strip()
        slam_version = (self.last_status_values or {}).get("SLAM_VERSION", "")
        started = self.run_navigation_spec(
            navigation.mark_charging_dock_command(self.profile(), map_pcd, slam_version=slam_version),
            "标记充电桩中",
        )
        if started:
            page.log_navigation_event(self, "[ARC] 已开始标记充电桩")
        return started

    def make_mapped_dock_action(self) -> bool:
        page = navigation_page_class()
        ready, reason = page.mapped_dock_ready_reason(self, self.last_status_values or {})
        if not ready:
            navigation_page_module().QMessageBox.information(self, "暂不能有图进桩", reason)
            return False
        map_pcd = self.map_pcd_path.text().strip()
        started = self.run_navigation_spec(navigation.start_arc_with_map_command(self.profile(), map_pcd), "有图进桩中")
        if started:
            page.log_navigation_event(self, "[ARC] 已开始有图进桩")
        return started

    def make_unmapped_dock_action(self) -> bool:
        page = navigation_page_class()
        ready, reason = page.unmapped_dock_ready_reason(self, self.last_status_values or {})
        if not ready:
            navigation_page_module().QMessageBox.information(self, "暂不能无图进桩", reason)
            return False
        started = self.run_navigation_spec(mapping.arc_start_action_command(self.profile(), "dock"), "无图进桩中")
        if started:
            page.log_navigation_event(self, "[ARC] 已开始无图进桩")
        return started

    def make_arc_undock_action(self) -> bool:
        page = navigation_page_class()
        ready, reason = page.arc_undock_ready_reason(self, self.last_status_values or {})
        if not ready:
            navigation_page_module().QMessageBox.information(self, "暂不能出桩", reason)
            return False
        started = self.run_navigation_spec(mapping.arc_start_action_command(self.profile(), "undock"), "出桩中")
        if started:
            page.log_navigation_event(self, "[ARC] 已开始出桩")
        return started

    def make_mapped_recharge_action(self) -> bool:
        page = navigation_page_class()
        action, label, ready, reason = page.mapped_recharge_action_state(self, self.last_status_values or {})
        if not ready or not action:
            navigation_page_module().QMessageBox.information(self, f"暂不能{label}", reason)
            return False
        if action == "undock":
            return page.make_arc_undock_action(self)
        return page.make_mapped_dock_action(self)
