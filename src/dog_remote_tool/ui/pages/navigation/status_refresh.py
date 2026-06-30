from __future__ import annotations

import time
from pathlib import Path

from PyQt5.QtCore import QProcess, Qt

from dog_remote_tool.core.shell import CommandSpec
from dog_remote_tool.modules import mapping
from dog_remote_tool.modules import navigation
from dog_remote_tool.ui.navigation_helpers import parse_map_list_entries
from dog_remote_tool.ui.pages.navigation.status_helpers import (
    _navigation_command_wait_text,
)

_ARC_CHARGING_STATUS_KEYS = ("ARC_DOCK_STATE", "ARC_DOCK_TEXT", "ARC_APP_DOCK_STATUS", "ARC_APP_ALG_STATUS")


def _navigation_page_class():
    from dog_remote_tool.ui.pages.navigation.page import NavigationPage

    return NavigationPage


def _navigation_page_module():
    from dog_remote_tool.ui.pages.navigation import page as navigation_page

    return navigation_page


class NavigationStatusRefreshMixin:
    def refresh_navigation_status(self) -> bool:
        if not self.page_active:
            return False
        if not self.navigation_supported():
            self.last_status_values = {}
            self.last_status_state = "blocked"
            self.set_cards_from_values({"STATUS": "blocked", "TEXT": "当前设备不支持导航"})
            return False
        if self.status_slot.is_running():
            return False
        map_pcd, _x, _y, _yaw, _speed, _tol = self.navigation_values()
        profile = self.profile()
        process, request_id = self.status_slot.start_spec(
            CommandSpec(
                "刷新导航状态",
                navigation.fast_probe_status_command(profile, map_pcd),
                concurrency="parallel",
                locks=("navigation-status",),
            )
        )
        if process is None:
            return False
        process.readyReadStandardOutput.connect(lambda: self.read_status_output(process, request_id))
        process.finished.connect(lambda exit_code, _status: self.status_finished(process, exit_code, request_id))
        process.start()
        return True

    def read_status_output(self, process: QProcess, request_id: int) -> bool:
        return self.status_slot.read_available_output(process, request_id)

    def status_finished(self, process: QProcess, exit_code: int, request_id: int) -> bool:
        page = _navigation_page_class()
        navigation_page = _navigation_page_module()
        output = self.status_slot.finish(process, request_id)
        if output is None:
            return False
        state, text, detail, values = navigation.summarize_status(output, exit_code)
        self.last_status_at = time.monotonic()
        values = dict(values)
        values = NavigationStatusRefreshMixin._merge_missing_arc_charging_status(self, values)
        current_map_pcd = self.map_pcd_path.text().strip() if hasattr(self, "map_pcd_path") else ""
        status_map_pcd = values.get("MAP_PCD", "").strip()
        if current_map_pcd and status_map_pcd and status_map_pcd != current_map_pcd:
            if self.page_active:
                navigation_page.QTimer.singleShot(0, self.refresh_navigation_status)
            return True
        self.last_status_values = values
        self.last_status_state = state
        values.setdefault("STATUS", state)
        values.setdefault("TEXT", text)
        self.set_cards_from_values(values, detail)
        page.retry_map_preparation_after_ready_status(self, values)
        if page.navigation_streams_ready(self):
            navigation_page.QTimer.singleShot(0, self.start_pose_stream)
        if page.navigation_stream_subscription_active(self) and page.navigation_streams_ready(self):
            navigation_page.QTimer.singleShot(0, self.start_plan_stream)
        if self.pending_navigation_action:
            ready, reason = page.navigation_action_ready_reason(self, values)
            if ready:
                navigation_page.QTimer.singleShot(0, lambda: page.continue_pending_navigation_action(self))
            else:
                self.nav_status_note.setText(f"导航任务已排队：{reason}")
        return True

    def _merge_missing_arc_charging_status(self, values: dict[str, str]) -> dict[str, str]:
        page = _navigation_page_class()
        if page.arc_charging_detected(self, values):
            return values
        previous_values = getattr(self, "last_status_values", {}) or {}
        if not page.arc_charging_detected(self, previous_values):
            return values
        has_conclusive_arc_status = (
            bool(values.get("ARC_DOCK_STATE", "").strip())
            or bool(values.get("ARC_APP_DOCK_STATUS", "").strip())
            or bool(values.get("ARC_APP_ALG_STATUS", "").strip())
            or values.get("ARC_DOCK_TEXT", "") not in {"", "无数据", "未知"}
        )
        if has_conclusive_arc_status:
            return values
        merged = dict(values)
        for key in _ARC_CHARGING_STATUS_KEYS:
            if key in previous_values:
                merged[key] = previous_values[key]
        return merged

    def set_cards_from_values(self, values: dict[str, str], detail: str = "") -> None:
        page = _navigation_page_class()
        status = values.get("STATUS", "unknown")
        app_nav_status = values.get("APP_NAV_STATUS", "").strip()
        app_terminal = app_nav_status in {"Succeeded", "Error", "NavError", "LocError", "Failed"}
        ready_completion = status == "ready" and page.ready_status_confirms_navigation_finished(self, values)
        if (
            status == "ready"
            and getattr(self, "navigation_command_operation", "")
            and not app_terminal
            and not ready_completion
        ):
            self.navigation_command_idle_confirmations = 0
            values = page.pending_navigation_command_display_values(self, values)
            detail = _navigation_command_wait_text(getattr(self, "navigation_command_operation", ""))
        elif app_terminal and getattr(self, "navigation_command_operation", ""):
            self.navigation_command_idle_confirmations = 0
            if app_nav_status == "Succeeded":
                values = dict(values)
                values["STATUS"] = "success"
                values["TEXT"] = "导航已到达"
                detail = detail or "导航状态已返回成功。"
            self.navigation_command_task_id = None
            self.navigation_command_operation = ""
        elif status == "ready":
            self.navigation_command_idle_confirmations = getattr(self, "navigation_command_idle_confirmations", 0) + 1
        else:
            self.navigation_command_idle_confirmations = 0
        status = values.get("STATUS", status)
        text = values.get("TEXT", "未知")
        map_ok = values.get("MAP_OK")
        loc_ready = values.get("LOCALIZATION_READY")
        loc_code = values.get("LOCALIZATION_CODE", "")
        detection_publishers = values.get("DETECTION2D_PUBLISHERS", "0")
        detection_ready = values.get("DETECTION2D_READY")
        nav_process = values.get("NAV_PROCESS")
        subs = values.get("START_NAV_SUBSCRIBERS", "0")
        license_ok = values.get("LICENSE_OK")
        calibration_ok = values.get("CALIBRATION_OK")

        map_text = "可用" if map_ok == "1" else "缺失" if map_ok == "0" else "读取中"
        self.map_state.setText("地图\n" + map_text)
        self._set_card_style(self.map_state, "ready" if map_ok == "1" else "blocked" if map_ok == "0" else "starting")
        loc_label = navigation.localization_state_display_text(
            loc_code,
            values.get("LOCALIZATION_DESC", ""),
            values.get("LOCALIZATION_CODE_FIELD", "status"),
        )
        self.localization_state.setText(f"定位\n{loc_label if loc_code else '读取中'}")
        self._set_card_style(
            self.localization_state,
            "ready" if loc_ready == "1" else "blocked" if loc_ready == "0" else "starting",
        )
        file_status_reported = license_ok is not None or calibration_ok is not None
        file_ready = not file_status_reported or (
            (license_ok is None or license_ok == "1") and (calibration_ok is None or calibration_ok == "1")
        )
        if file_status_reported and not file_ready:
            perception_text = f"授权{'Y' if license_ok == '1' else 'N'} 标定{'Y' if calibration_ok == '1' else 'N'}"
        elif detection_ready == "1":
            perception_text = "感知有数据"
        elif detection_publishers != "0":
            perception_text = "感知无数据"
        else:
            perception_text = "未检查"
        self.perception_state.setText("文件/感知\n" + perception_text)
        self._set_card_style(self.perception_state, "ready" if file_ready else "blocked")
        nav_ready = nav_process == "1" and subs != "0"
        nav_checked = nav_process is not None
        self.navigation_state.setText("导航栈\n" + ("可用" if nav_ready else "未启动" if nav_checked else "读取中"))
        self._set_card_style(self.navigation_state, "ready" if nav_ready else "blocked" if nav_checked else "starting")
        app_nav_status = values.get("APP_NAV_STATUS", "").strip()
        task_text = {
            "active": "导航中",
            "success": "已完成",
            "error": "异常",
            "ready": "可发送目标",
            "cancelled": "已取消",
        }.get(status, text or "等待状态")
        self.task_state.setText(f"任务\n{task_text}")
        display_state = page.navigation_current_card_state(self, values, status)
        self._set_card_style(self.task_state, display_state)
        if hasattr(self, "nav_current_state"):
            current_text = page.current_navigation_status_text(self, values, text)
            self.nav_current_state.setText(f"当前状态\n{current_text}")
            self.nav_current_state.setToolTip(current_text)
            self._set_card_style(self.nav_current_state, display_state)
        self.flow_detail.setText(f"流程摘要\n{detail or text}")
        self.flow_detail.setToolTip(detail or text)
        if hasattr(self, "nav_code_detail"):
            self.nav_code_detail.setText(text or task_text)
            self.nav_code_detail.setToolTip(detail or text or task_text)
        note = text if text else task_text
        if status == "active":
            note = f"导航中：{page.navigation_status_headline(self, values, note)}"
        elif status in {"blocked", "error", "unknown"}:
            note = f"需处理：{note}"
        self.nav_status_note.setText(note)
        self.nav_status_note.setToolTip(detail or text)
        if status == "active":
            page.resume_navigation_visualization_from_status(self, values)
        page.update_navigation_action_buttons(self, values)
        self.finish_navigation_visualization_if_terminal(status)
        self.refresh_workspace_from_page()

    def refresh_map_list(self) -> bool:
        if not self.page_active or not self.navigation_supported():
            return False
        if self.map_list_slot.is_running():
            return False
        profile = self.profile()
        save_map_path = self.save_map_path.text().strip() or mapping.default_save_map_path(profile)
        process, request_id = self.map_list_slot.start_spec(
            CommandSpec(
                "读取导航地图列表",
                mapping.list_map_pgm_command(profile, save_map_path),
                concurrency="parallel",
                locks=("navigation-map-list",),
            )
        )
        if process is None:
            return False
        process.readyReadStandardOutput.connect(lambda: self.read_map_list_output(process, request_id))
        process.finished.connect(lambda exit_code, _status: self.map_list_finished(process, exit_code, request_id))
        process.start()
        return True

    def read_map_list_output(self, process: QProcess, request_id: int) -> bool:
        return self.map_list_slot.read_available_output(process, request_id)

    def map_list_finished(self, process: QProcess, exit_code: int, request_id: int) -> bool:
        page = _navigation_page_class()
        navigation_page = _navigation_page_module()
        output = self.map_list_slot.finish(process, request_id)
        if output is None:
            return False
        if exit_code != 0:
            self.refresh_navigation_status()
            return True
        entries = parse_map_list_entries(output)
        current = self.selected_map_pgm()
        previous_signature = self.map_entries_signature
        previous_selected = current
        self.map_entries_signature = tuple(entries)
        self.map_details = {remote_path: detail for _label, remote_path, detail in entries}
        signature_changed = self.map_entries_signature != previous_signature
        update_cards = getattr(self, "update_map_cards", None)
        clear_cards = getattr(self, "clear_map_cards", None)
        selected_changed = False
        with navigation_page.QSignalBlocker(self.map_selector):
            self.map_selector.clear()
            for label, remote_path, detail in entries:
                self.map_selector.addItem(label, remote_path)
                self.map_selector.setItemData(self.map_selector.count() - 1, detail, Qt.ToolTipRole)
            if current:
                index = self.map_selector.findData(current)
                if index >= 0:
                    self.map_selector.setCurrentIndex(index)
        if entries and (not current or self.map_selector.findData(current) < 0):
            with navigation_page.QSignalBlocker(self.map_selector):
                self.map_selector.setCurrentIndex(0)
            self.map_pcd_path.setText(str(Path(entries[0][1]).with_name("map.pcd")))
            selected_changed = self.selected_map_pgm() != previous_selected
            current = self.selected_map_pgm()
        if selected_changed:
            page.reset_selected_map_runtime_state(self)
        page.sync_selected_route_geojson_path(self)
        self.update_selected_map_detail()
        cards_missing = not getattr(self, "map_cards", {})
        if entries and callable(update_cards) and (cards_missing or signature_changed):
            update_cards(entries)
        elif entries:
            update_selection = getattr(self, "update_map_card_selection", None)
            if callable(update_selection):
                update_selection()
        elif not entries and callable(clear_cards):
            clear_cards()
        selected_map = self.selected_map_pgm()
        selected_changed_now = selected_map != previous_selected
        refresh_preview_once = bool(getattr(self, "refresh_selected_map_preview_once", False))
        if selected_changed_now or signature_changed or (refresh_preview_once and selected_map):
            self.refresh_selected_map_preview_once = False
            self.fetch_navigation_map_preview(force=refresh_preview_once and not selected_changed_now and not signature_changed)
        self.refresh_navigation_status()
        return True
