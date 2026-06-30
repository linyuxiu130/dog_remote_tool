from __future__ import annotations

from pathlib import Path

from PyQt5.QtCore import QProcess

from dog_remote_tool.core.parsers import parse_key_values
from dog_remote_tool.modules import navigation
from dog_remote_tool.ui.pages.navigation.status_helpers import (
    _compact_failure_lines,
    _status_confirms_selected_map_navigation_ready,
)


def _navigation_page_class():
    from dog_remote_tool.ui.pages.navigation.page import NavigationPage

    return NavigationPage


def _navigation_page_module():
    from dog_remote_tool.ui.pages.navigation import page as navigation_page

    return navigation_page


class NavigationMapPreparationMixin:
    def on_map_selection_changed(self) -> None:
        page = _navigation_page_class()
        previous_map_pcd = self.map_pcd_path.text().strip() if hasattr(self, "map_pcd_path") else ""
        remote_pgm = self.selected_map_pgm()
        if remote_pgm:
            self.map_pcd_path.setText(str(Path(remote_pgm).with_name("map.pcd")))
        page.sync_selected_route_geojson_path(self)
        page.clear_selected_map_preview_if_stale(self, remote_pgm)
        map_pcd = self.map_pcd_path.text().strip()
        if page.should_stop_navigation_before_map_switch(self, previous_map_pcd, map_pcd):
            page.stop_navigation_for_map_switch(self)
        if map_pcd != self.prepared_map_pcd_path:
            page.reset_selected_map_runtime_state(self)
        self.update_selected_map_detail()
        self.fetch_navigation_map_preview()
        if remote_pgm and callable(getattr(self, "refresh_route_file_state", None)):
            self.refresh_route_file_state(remote_pgm)
        if self.page_active:
            started_prepare = page.start_selected_map_preparation(self)
            if not started_prepare:
                self.refresh_navigation_status()

    def should_stop_navigation_before_map_switch(self, previous_map_pcd: str, map_pcd: str) -> bool:
        if not previous_map_pcd or not map_pcd or previous_map_pcd == map_pcd:
            return False
        values = getattr(self, "last_status_values", {}) or {}
        status_map_pcd = values.get("MAP_PCD", "").strip()
        if status_map_pcd and status_map_pcd != previous_map_pcd:
            return False
        page = _navigation_page_class()
        return bool(getattr(self, "navigation_tracking_enabled", False) or page.remote_navigation_running(self, values))

    def start_selected_map_preparation(self, *, force: bool = False) -> bool:
        page = _navigation_page_class()
        if not self.page_active or not self.navigation_supported():
            return False
        map_pcd = self.map_pcd_path.text().strip()
        if not map_pcd:
            return False
        if not force and self.prepared_map_pcd_path == map_pcd:
            return False
        if not force and page.mark_selected_map_ready_from_cached_status(self, map_pcd):
            return False
        if self.map_prepare_slot.is_running():
            if self.preparing_map_pcd_path == map_pcd:
                return False
            self.map_prepare_slot.stop()
            self.nav_status_note.setText("已切换地图，正在初始化新地图")
        self.prepared_map_pcd_path = ""
        self.preparing_map_pcd_path = map_pcd
        self.map_prepare_error = ""
        if force:
            self.map_prepare_auto_retry_pcd = map_pcd
        self.map_state.setText("地图\n初始化中")
        self.localization_state.setText("定位\n加载地图")
        self.task_state.setText("任务\n准备地图")
        self._set_card_style(self.map_state, "starting")
        self._set_card_style(self.localization_state, "starting")
        self._set_card_style(self.task_state, "starting")
        self.nav_status_note.setText("正在为所选地图加载定位并初始化导航")
        process, request_id = self.map_prepare_slot.start_spec(navigation.prepare_map_command(self.profile(), map_pcd))
        if process is None:
            return False
        page.update_navigation_action_buttons(self, self.last_status_values)
        self.refresh_workspace_from_page()
        process.readyReadStandardOutput.connect(lambda: self.read_map_preparation_output(process, request_id))
        process.finished.connect(lambda exit_code, _status: self.map_preparation_finished(process, exit_code, request_id))
        process.start()
        return True

    def route_navigation_ready_reason(self) -> tuple[bool, str]:
        page = _navigation_page_class()
        remote_pgm = self.selected_map_pgm()
        if not remote_pgm:
            route_path = self.route_geojson_path.text().strip() if hasattr(self, "route_geojson_path") else ""
            return bool(route_path), "请先选择历史图或填写路网 GeoJSON"
        state = self.route_file_states.get(remote_pgm)
        if state is True:
            return True, "远端路网文件已就绪"
        local_route = page.local_route_geojson_path(self, remote_pgm)
        if local_route is not None and local_route.exists():
            return False, "本地路网已保存，请点击“上传路网”同步到机器人，或在编辑器中点击“上传远端”"
        if state is False:
            return False, "机器人当前地图目录没有 map.geojson，请先编辑路网并上传远端"
        return False, "等待路网检查完成，或先编辑路网并上传远端"

    def read_map_preparation_output(self, process: QProcess, request_id: int) -> bool:
        return self.map_prepare_slot.read_available_output(process, request_id)

    def map_preparation_finished(self, process: QProcess, exit_code: int, request_id: int) -> bool:
        page = _navigation_page_class()
        navigation_page = _navigation_page_module()
        output = self.map_prepare_slot.finish(process, request_id)
        if output is None:
            return False
        prep_values = parse_key_values(output)
        prepared_path = self.preparing_map_pcd_path
        self.preparing_map_pcd_path = ""
        current_path = self.map_pcd_path.text().strip()
        if prepared_path and current_path and prepared_path != current_path:
            if self.page_active:
                page.start_selected_map_preparation(self, force=True)
            return True
        if exit_code != 0 and (
            (
                prep_values.get("MAP_PREP_NAV_READY") == "1"
                and prep_values.get("MAP_PREP_LOCALIZATION_READY") == "1"
            )
            or _status_confirms_selected_map_navigation_ready(getattr(self, "last_status_values", {}) or {}, current_path)
        ):
            exit_code = 0
        tail = _compact_failure_lines(output)
        if exit_code == 0:
            self.prepared_map_pcd_path = current_path
            self.map_prepare_error = ""
            self.map_prepare_auto_retry_pcd = ""
            self.map_state.setText("地图\n已初始化")
            self.localization_state.setText("定位\n连续定位正常")
            self.navigation_state.setText("导航栈\n已初始化")
            self.task_state.setText("任务\n导航就绪")
            self._set_card_style(self.map_state, "ready")
            self._set_card_style(self.localization_state, "ready")
            self._set_card_style(self.navigation_state, "ready")
            self._set_card_style(self.task_state, "ready")
            self.nav_status_note.setText("所选地图已初始化，定位已确认，可发送导航任务")
            self.flow_detail.setText("流程摘要\n地图已初始化，定位已确认，后台继续刷新完整导航状态")
            page.log_navigation_event(self, "[地图] 当前地图已就绪")
            if self.page_active:
                navigation_page.QTimer.singleShot(300, self.refresh_navigation_status)
                navigation_page.QTimer.singleShot(900, self.start_pose_stream)
                navigation_page.QTimer.singleShot(900, self.start_plan_stream)
            if self.pending_navigation_action:
                self.nav_status_note.setText("地图初始化和定位已确认，正在自动下发导航任务")
                page.log_navigation_event(self, "[任务] 地图已就绪，继续导航任务")
            pending_values = dict(getattr(self, "last_status_values", {}))
            pending_values.update(
                {
                    "STATUS": "ready",
                    "TEXT": "导航就绪",
                    "MAP_PCD": current_path,
                    "MAP_OK": "1",
                    "LOAD_MAP_SERVICE": "1",
                    "LOCALIZATION_READY": prep_values.get("MAP_PREP_LOCALIZATION_READY", "1"),
                    "LOCALIZATION_CODE": pending_values.get("LOCALIZATION_CODE", "3"),
                    "MAP_PREP_NAV_READY": prep_values.get("MAP_PREP_NAV_READY", "1"),
                    "NAV_PROCESS": pending_values.get("NAV_PROCESS", "1"),
                    "START_NAV_SUBSCRIBERS": pending_values.get("START_NAV_SUBSCRIBERS", "1"),
                }
            )
            self.last_status_values = pending_values
            self.last_status_state = "ready"
            if hasattr(self, "nav_current_state"):
                current_text = page.current_navigation_status_text(self, pending_values, "导航就绪")
                self.nav_current_state.setText(f"当前状态\n{current_text}")
                self._set_card_style(self.nav_current_state, "ready")
            if self.pending_navigation_action:
                navigation_page.QTimer.singleShot(0, lambda: page.continue_pending_navigation_action(self))
        else:
            if not tail:
                self.map_prepare_error = ""
                self.nav_status_note.setText("地图初始化状态未回读，正在刷新远端状态")
                self.flow_detail.setText("流程摘要\n地图初始化命令未返回详细错误，正在刷新远端状态")
                page.log_navigation_event(self, "[地图] 初始化状态未回读，正在刷新远端状态")
                if self.page_active:
                    navigation_page.QTimer.singleShot(0, self.refresh_navigation_status)
                page.update_navigation_action_buttons(self, self.last_status_values)
                self.refresh_workspace_from_page()
                return True
            self.prepared_map_pcd_path = ""
            self.pending_navigation_action = ""
            self.map_prepare_error = tail or "地图准备失败"
            self.map_state.setText("地图\n初始化失败")
            self.localization_state.setText("定位\n地图未加载")
            self.task_state.setText("任务\n地图初始化失败")
            self._set_card_style(self.map_state, "blocked")
            self._set_card_style(self.localization_state, "blocked")
            self._set_card_style(self.task_state, "blocked")
            self.nav_status_note.setText("地图初始化失败，请查看日志或重新选择地图")
            self.flow_detail.setText("流程摘要\n" + self.map_prepare_error)
            page.log_navigation_event(self, "[地图] 初始化失败：" + self.map_prepare_error)
        page.update_navigation_action_buttons(self, self.last_status_values)
        self.refresh_workspace_from_page()
        return True

    def mark_selected_map_ready_from_cached_status(self, map_pcd: str) -> bool:
        page = _navigation_page_class()
        values = getattr(self, "last_status_values", {}) or {}
        if not _status_confirms_selected_map_navigation_ready(values, map_pcd):
            return False
        self.preparing_map_pcd_path = ""
        self.prepared_map_pcd_path = map_pcd
        self.map_prepare_error = ""
        self.map_prepare_auto_retry_pcd = ""
        self.map_state.setText("地图\n已初始化")
        self.localization_state.setText("定位\n连续定位正常")
        self.navigation_state.setText("导航栈\n已初始化")
        self.task_state.setText("任务\n导航就绪")
        self._set_card_style(self.map_state, "ready")
        self._set_card_style(self.localization_state, "ready")
        self._set_card_style(self.navigation_state, "ready")
        self._set_card_style(self.task_state, "ready")
        self.nav_status_note.setText("远端已确认当前地图和定位就绪，可发送导航任务")
        self.flow_detail.setText("流程摘要\n远端状态已确认当前地图、定位和导航栈就绪。")
        page.update_navigation_action_buttons(self, values)
        self.refresh_workspace_from_page()
        return True

    def retry_map_preparation_after_ready_status(self, values: dict[str, str]) -> bool:
        page = _navigation_page_class()
        navigation_page = _navigation_page_module()
        map_pcd = self.map_pcd_path.text().strip() if hasattr(self, "map_pcd_path") else ""
        if not map_pcd or getattr(self, "prepared_map_pcd_path", "") == map_pcd:
            return False
        if _status_confirms_selected_map_navigation_ready(values, map_pcd):
            slot = getattr(self, "map_prepare_slot", None)
            preparing_map = getattr(self, "preparing_map_pcd_path", "")
            if slot is not None and slot.is_running() and preparing_map and preparing_map != map_pcd:
                return False
            if slot is not None and slot.is_running():
                slot.stop()
            self.preparing_map_pcd_path = ""
            self.prepared_map_pcd_path = map_pcd
            self.map_prepare_error = ""
            self.map_prepare_auto_retry_pcd = ""
            self.map_state.setText("地图\n已初始化")
            self.localization_state.setText("定位\n连续定位正常")
            self.navigation_state.setText("导航栈\n已初始化")
            self.task_state.setText("任务\n导航就绪")
            self._set_card_style(self.map_state, "ready")
            self._set_card_style(self.localization_state, "ready")
            self._set_card_style(self.navigation_state, "ready")
            self._set_card_style(self.task_state, "ready")
            self.nav_status_note.setText("远端已确认当前地图和定位就绪，可发送导航任务")
            self.flow_detail.setText("流程摘要\n远端状态已确认当前地图、定位和导航栈就绪。")
            page.update_navigation_action_buttons(self, values)
            self.refresh_workspace_from_page()
            if self.page_active:
                navigation_page.QTimer.singleShot(0, self.start_pose_stream)
                if page.navigation_stream_subscription_active(self):
                    navigation_page.QTimer.singleShot(0, self.start_plan_stream)
            return True
        if not getattr(self, "map_prepare_error", ""):
            return False
        if getattr(self, "map_prepare_auto_retry_pcd", "") == map_pcd:
            return False
        slot = getattr(self, "map_prepare_slot", None)
        if slot is not None and slot.is_running():
            return False
        if values.get("MAP_PCD", "").strip() != map_pcd:
            return False
        if values.get("MAP_OK") != "1" or values.get("LOCALIZATION_READY") != "1":
            return False
        if values.get("NAV_PROCESS") != "1" or values.get("START_NAV_SUBSCRIBERS", "0") == "0":
            return False
        self.map_prepare_auto_retry_pcd = map_pcd
        self.nav_status_note.setText("定位状态已恢复，正在重新初始化所选地图")
        page.log_navigation_event(self, "[地图] 定位已恢复，自动重新初始化所选地图")
        return page.start_selected_map_preparation(self, force=True)

    def queue_pending_navigation_action(self, action: str) -> bool:
        page = _navigation_page_class()
        map_pcd = self.map_pcd_path.text().strip() if hasattr(self, "map_pcd_path") else ""
        if not self.page_active or not map_pcd:
            return False
        labels = {
            "goal": "单点导航",
            "multipoint": "多点导航",
            "route": "路网导航",
        }
        label = labels.get(action)
        if label is None:
            return False
        self.pending_navigation_action = action
        self.nav_status_note.setText(f"{label}已排队，地图和定位就绪后自动下发")
        page.log_navigation_event(self, f"[任务] {label}已排队，等待地图和定位就绪")
        return True

    def continue_pending_navigation_action(self) -> bool:
        page = _navigation_page_class()
        action = self.pending_navigation_action
        if not action:
            return False
        self.pending_navigation_action = ""
        if action == "goal":
            return page.make_start_goal(self)
        if action == "multipoint":
            return page.make_start_multipoint(self)
        if action == "route":
            return page.make_start_route_goal(self)
        return False

    def ensure_selected_map_prepared_for_goal(self) -> bool:
        page = _navigation_page_class()
        navigation_page = _navigation_page_module()
        slot = getattr(self, "map_prepare_slot", None)
        if slot is None:
            return True
        map_pcd = self.map_pcd_path.text().strip()
        if not map_pcd:
            navigation_page.QMessageBox.information(self, "未选择地图", "请先选择一个历史图。")
            return False
        if self.prepared_map_pcd_path == map_pcd:
            return True
        if slot.is_running():
            self.nav_status_note.setText("地图正在自动定位初始化，完成后再发送导航任务")
            self.refresh_workspace_from_page()
            return False
        page.start_selected_map_preparation(self, force=True)
        self.nav_status_note.setText("已开始自动定位当前地图，完成后再发送导航任务")
        self.refresh_workspace_from_page()
        return False
