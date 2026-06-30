from __future__ import annotations

import re
import time

from PyQt5.QtCore import QProcess
from PyQt5.QtWidgets import QPushButton

from dog_remote_tool.core.shell import CommandSpec
from dog_remote_tool.modules import mapping
from dog_remote_tool.ui.map_helpers import summarize_mapping_status
from dog_remote_tool.ui.user_console import (
    OPERATION_TONES,
    compact_map_name,
    status_tone_for_mapping_state,
)
from dog_remote_tool.ui.widget_roles import set_widget_role


def _mapping_page_class():
    from dog_remote_tool.ui.pages.mapping.page import MappingPage

    return MappingPage


def _mapping_page_module():
    from dog_remote_tool.ui.pages.mapping import page as mapping_page

    return mapping_page


class MappingStatusMixin:
    def _detail_field(self, detail: str, prefix: str) -> str:
        for line in detail.splitlines():
            if line.startswith(prefix):
                return line.removeprefix(prefix).strip()
        return ""

    def _mapping_next_step(self, state: str, detail: str) -> str:
        tone = status_tone_for_mapping_state(state)
        if state in {"unknown", "error"}:
            first = ""
            if detail:
                first = self._detail_field(detail, "远端状态：") or detail.splitlines()[0]
            return first or tone.next_step
        return tone.next_step

    def _update_mapping_result_metrics(self, state: str, text: str, detail: str, latest_map: str = "") -> None:
        map_count = self._detail_field(detail, "历史地图：")
        latest = latest_map or self._detail_field(detail, "最新地图：")
        disk = self._detail_field(detail, "剩余空间：")
        save_text = {
            "ready": "可开始建图",
            "mapping": "建图进行中",
            "starting": "启动中",
            "saving": "保存中",
            "success": "地图已保存",
            "stopped": "未开始",
            "error": "需要处理",
            "unknown": "状态未知",
        }.get(state, text or "--")
        if hasattr(self, "map_save_metric"):
            self.map_save_metric.set_value(save_text)
        if hasattr(self, "map_count_metric"):
            self.map_count_metric.set_value(map_count or "--")
        if hasattr(self, "latest_map_metric"):
            display_latest = compact_map_name(latest) if "/" in latest else latest
            self.latest_map_metric.set_value(display_latest or "--", latest if "/" in latest else "")
        if hasattr(self, "disk_metric"):
            self.disk_metric.set_value(disk or "--")

    def _update_mapping_alert(self, state: str, text: str, detail: str) -> None:
        alert = getattr(self, "mapping_alert", None)
        if alert is None:
            return
        if state == "error":
            alert.show_message(text or "建图失败", self._mapping_next_step(state, detail), "danger")
        elif state == "unknown" and text not in {"读取中", "未知"}:
            alert.show_message("建图状态未确认", self._mapping_next_step(state, detail), "warning")
        else:
            alert.clear_message()

    def set_mapping_operation(self, text: str, state: str = "idle") -> None:
        self.mapping_operation_title = text
        detail = "等待用户操作。" if state == "idle" else "任务执行中，请等待结果。"
        if state == "blocked":
            detail = "当前有任务占用，请稍后重试。"
        if state == "saving":
            detail = "正在保存地图并确认结果。"
        self.mapping_operation.set_status(text, detail, OPERATION_TONES.get(state, "neutral"))
        self.update_mapping_action_buttons()

    def update_mapping_action_buttons(self) -> None:
        if not hasattr(self, "start_mapping_btn"):
            return
        active_by_status = mapping.is_mapping_active_alg_status(
            self.profile(),
            self.last_mapping_alg_status,
        )
        active_by_operation = self.mapping_operation_title in {"开始建图中", "建图中", "保存中", "结束保存中", "取消建图中"}
        mapping_active = active_by_status or active_by_operation
        saving = self.mapping_operation_title == "结束保存中"
        cancelling = self.mapping_operation_title == "取消建图中"
        busy = saving or cancelling
        for button in (
            self.start_mapping_btn,
            self.finish_mapping_btn,
            self.cancel_mapping_btn,
            self.refresh_status_btn,
        ):
            button.setVisible(True)
        self.start_mapping_btn.setEnabled(not mapping_active and self.mapping_supported())
        self.finish_mapping_btn.setEnabled(mapping_active and not busy)
        self.cancel_mapping_btn.setEnabled(active_by_status and not busy)
        self.cancel_mapping_btn.setToolTip(
            "远端正在建图，可取消并放弃当前结果" if active_by_status and not busy else "仅远端 alg 状态确认为建图中时可取消"
        )
        self.refresh_status_btn.setEnabled(self.mapping_supported())
        page = _mapping_page_class()
        page._set_button_role(self, self.start_mapping_btn, "Primary" if not mapping_active else "SoftPrimary")
        page._set_button_role(self, self.finish_mapping_btn, "Primary" if mapping_active else "SoftPrimary")
        page._set_button_role(self, self.cancel_mapping_btn, "SoftDanger")
        page._set_button_role(self, self.refresh_status_btn, "")

    def _set_button_role(self, button: QPushButton, role: str) -> None:
        set_widget_role(button, role)

    def refresh_mapping_status(self) -> bool:
        if not self.page_active:
            return False
        if not self.mapping_supported():
            self.last_mapping_status_state = "unknown"
            self.last_mapping_alg_status = ""
            self.last_mapping_status_at = 0.0
            self.set_mapping_status("unknown", "当前设备不支持建图", "请选择小狗二代 S100、NX 或中狗建图目标。")
            return False
        if self.status_slot.is_running():
            return False
        _sensor_type, save_map_path, _calibration_file_path, _arc_calibration_file_path = self.mapping_values()
        profile = self.profile()
        process, request_id = self.status_slot.start_spec(
            CommandSpec(
                "刷新建图状态",
                mapping.probe_status_command(profile, save_map_path),
                concurrency="parallel",
                locks=("mapping", "app_ws"),
            )
        )
        if process is None:
            return False
        process.readyReadStandardOutput.connect(lambda: self.read_status_output(process, request_id))
        process.finished.connect(lambda exit_code, _status: self.status_finished(process, exit_code, request_id, profile))
        process.start()
        return True

    def refresh_mapping_page(self) -> bool:
        status_started = self.refresh_mapping_status()
        list_started = self.refresh_map_list(silent=False, force_preview=True, force_latest=True)
        return bool(status_started or list_started)

    def read_status_output(self, process: QProcess, request_id: int) -> bool:
        return self.status_slot.read_available_output(process, request_id)

    def capture_mapping_runner_output(self, text: str) -> bool:
        if not getattr(self, "page_active", False) or not self.mapping_supported():
            return False
        saved_match = re.search(r"地图已保存[:：]\s*(\S+)", text)
        if saved_match:
            remote_map = saved_match.group(1)
            self.last_mapping_status_state = "success"
            self.last_mapping_alg_status = "MappingSaved"
            self.last_mapping_status_at = time.monotonic()
            self.set_mapping_status(
                "success",
                "保存完成",
                f"远端状态：保存完成\n最新地图：{remote_map.rsplit('/', 1)[-1]}",
            )
            update_metrics = getattr(self, "_update_mapping_result_metrics", None)
            if callable(update_metrics):
                update_metrics("success", "保存完成", "", remote_map)
            update_buttons = getattr(self, "update_mapping_action_buttons", None)
            if callable(update_buttons):
                update_buttons()
            self.refresh_map_list(silent=False, force_preview=True, force_latest=True)
            return True
        match = re.search(r"建图状态[:：].*?[（(]([A-Za-z0-9_]+)[）)]", text)
        if not match:
            return False
        alg_status = match.group(1)
        current_status = mapping.mapping_status_from_alg_status(self.profile(), alg_status)
        if current_status is None:
            return False
        state, label = current_status
        if state == "ready" and "保存" in getattr(self, "mapping_operation_title", ""):
            state, label = "saving", "保存确认中"
        self.last_mapping_status_state = state
        self.last_mapping_alg_status = alg_status
        self.last_mapping_status_at = time.monotonic()
        details = [f"远端状态：{label}"]
        self.set_mapping_status(state, label, "；".join(details))
        update_buttons = getattr(self, "update_mapping_action_buttons", None)
        if callable(update_buttons):
            update_buttons()
        return True

    def status_finished(self, process: QProcess, exit_code: int, request_id: int, profile) -> bool:
        output = self.status_slot.finish(process, request_id)
        if output is None:
            return False
        summary = summarize_mapping_status(
            profile,
            output,
            exit_code,
            self.mapping_operation_title if self.mapping_operation_active else "",
        )
        if summary.failed:
            self.last_mapping_status_state = "unknown"
            self.last_mapping_alg_status = ""
            self.last_mapping_status_at = 0.0
            self.set_mapping_status(summary.state, summary.text, summary.detail)
            return True
        self.last_mapping_status_state = summary.state
        self.last_mapping_alg_status = summary.alg_status
        self.last_mapping_status_at = time.monotonic()
        self.set_mapping_status(
            summary.state,
            summary.text,
            summary.detail,
        )
        if (
            summary.state == "success"
            and getattr(self, "mapping_operation_active", False)
            and getattr(self, "mapping_operation_title", "") == "保存确认中"
        ):
            self.set_mapping_operation("保存完成", "done")
            self.mapping_operation_active = False
        return True

    def set_mapping_status(self, state: str, text: str, detail: str) -> None:
        tone = status_tone_for_mapping_state(state)
        detail_text = (detail or "远端状态：--").replace("；", "\n")
        self.mapping_state.set_status(text or tone.title, self._mapping_next_step(state, detail_text), tone.key)
        alg_status = self.last_mapping_alg_status or "--"
        if hasattr(self, "mapping_alg_state"):
            self.mapping_alg_state.set_status(alg_status, "", tone.key)
        self._update_mapping_result_metrics(state, text, detail_text)
        self._update_mapping_alert(state, text, detail_text)
        self.update_mapping_action_buttons()
