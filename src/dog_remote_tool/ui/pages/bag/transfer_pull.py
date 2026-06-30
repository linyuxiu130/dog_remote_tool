from __future__ import annotations

import os

from PyQt5.QtWidgets import QMessageBox

from dog_remote_tool.ui.pages.bag.helpers import (
    known_remote_bag_size_text,
    pull_confirm_detail,
    pull_finished_message,
    pull_local_base,
    pull_progress_texts,
    pull_progress_value,
    pull_result_log_lines,
    should_reset_transfer_timer,
)
from dog_remote_tool.ui.pages.bag.record_metadata import empty_record_context, record_context, record_info
from dog_remote_tool.ui.widget_roles import set_widget_texts


def _transfer_actions_module():
    from dog_remote_tool.ui.pages.bag import transfer_actions

    return transfer_actions


class BagTransferPullMixin:
    def pull_selected_remote_bags(self) -> bool:
        paths = self.selected_remote_paths()
        if not paths:
            QMessageBox.information(self, "提示", "请先选择远端Bag")
            return False
        self._apply_record_context(record_context(paths, self.product, self.storage_combo.currentText(), self.cache_spin.value(), profile=self.profile()))
        self._set_current_bag_paths(paths)
        return self.pull_current_recording(delete_remote_on_success=False)

    def pull_runtime_log_only(self) -> bool:
        return self._start_pull([], include_bag=False, include_log=True, delete_remote_on_success=False, log_kind="runtime")

    def pull_ros_log_only(self) -> bool:
        return self._start_pull([], include_bag=False, include_log=True, delete_remote_on_success=False, log_kind="ros")

    def pull_log_only(self) -> bool:
        return self._start_pull([], include_bag=False, include_log=True, delete_remote_on_success=False, log_kind="all")

    def pull_current_recording(self, delete_remote_on_success: bool = False, include_log: bool = False) -> bool:
        if not self.current_bag_paths:
            QMessageBox.information(self, "提示", "当前没有可回传的Bag路径")
            return False
        return self._start_pull(self.current_bag_paths[:], include_bag=True, include_log=include_log, delete_remote_on_success=delete_remote_on_success)

    def _current_record_info(self) -> dict:
        profile = self.current_record_profile or self.profile()
        return record_info(
            profile,
            self.product,
            self.current_bag_paths,
            self.current_record_product,
            self.current_record_themes,
            self.current_record_topics,
            self.current_record_started_at,
            self.current_record_finished_at,
            self.current_record_duration_seconds,
            self.current_record_storage,
            self.storage_combo.currentText(),
            self.current_record_cache_gb,
            self.cache_spin.value(),
        )

    def _start_pull(
        self,
        remote_paths: list[str],
        include_bag: bool,
        include_log: bool,
        delete_remote_on_success: bool,
        log_kind: str = "all",
    ) -> bool:
        if self.is_pulling:
            QMessageBox.information(self, "提示", "正在回传中，请等待当前任务完成")
            return False
        local_base = pull_local_base(include_bag, self.local_dir.text())
        os.makedirs(local_base, exist_ok=True)
        detail = pull_confirm_detail(include_bag, remote_paths)
        backend = self.current_record_backend() if include_bag and remote_paths else self.backend()
        answer = QMessageBox.question(self, "确认回传", f"设备: {backend.profile.target}\n本地路径: {local_base}\n\n{detail}", QMessageBox.Yes | QMessageBox.Cancel, QMessageBox.Yes)
        if answer != QMessageBox.Yes:
            return False
        self.pull_request_id += 1
        request_id = self.pull_request_id
        self.is_pulling = True
        self._set_record_detail_visible(bool(remote_paths))
        if include_bag and remote_paths:
            known_size = known_remote_bag_size_text(remote_paths, self.remote_bag_items)
            self.current_bag_size_label.setText(known_size or "查询中...")
            if not known_size:
                self.refresh_current_bag_size(force=True)
        else:
            self.current_bag_size_label.setText("--")
        self._set_pull_progress_value(0, animated=False)
        set_widget_texts(
            (
                (self.transfer_percent_label, "0%"),
                (self.transfer_speed_label, "速度 --"),
                (self.transfer_eta_label, "预计 --"),
            )
        )
        transfer_actions = _transfer_actions_module()
        self.transfer_started_at = transfer_actions.time.monotonic()
        self.transfer_progress_label = ""
        self._set_pull_progress_visible(True)
        self.record_status_label.setText("正在回传")
        transfer_actions.threading.Thread(
            target=self._pull_worker,
            args=(
                backend,
                remote_paths,
                local_base,
                include_bag,
                include_log,
                delete_remote_on_success,
                self.current_record_topics[:],
                self._current_record_info(),
                log_kind,
                request_id,
            ),
            daemon=True,
        ).start()
        return True

    def _pull_worker(
        self,
        backend,
        remote_paths: list[str],
        local_base: str,
        include_bag: bool,
        include_log: bool,
        delete_remote_on_success: bool,
        expected_topics: list[str],
        record_info: dict,
        log_kind: str,
        request_id: int,
    ) -> None:
        try:
            result = backend.pull_bag_and_log(
                remote_paths,
                local_base,
                expected_topics,
                include_bag,
                include_log,
                delete_remote_on_success,
                lambda label, percent, speed: self.pull_progress.emit(label, percent, speed, request_id),
                record_info,
                log_kind,
            )
        except Exception as exc:
            result = {"error": str(exc), "target_dir": "", "bag_success": False, "log_success": False, "validation": {"summary": "回传异常", "details": [str(exc)]}}
        self.pull_done.emit(result, request_id)

    def _update_pull_progress(self, label: str, percent: float, speed: str, request_id: int) -> bool:
        if request_id != self.pull_request_id:
            return False
        progress_value = pull_progress_value(percent)
        transfer_actions = _transfer_actions_module()
        if should_reset_transfer_timer(label, progress_value, self.transfer_progress_label, self.progress_bar.value()):
            self.transfer_started_at = transfer_actions.time.monotonic()
            self.transfer_progress_label = label
        self._set_pull_progress_value(progress_value)
        elapsed = transfer_actions.time.monotonic() - self.transfer_started_at if self.transfer_started_at else 0.0
        status_text, percent_text, speed_text, eta_text = pull_progress_texts(label, progress_value, speed, elapsed)
        set_widget_texts(
            (
                (self.record_status_label, status_text),
                (self.transfer_percent_label, percent_text),
                (self.transfer_speed_label, speed_text),
                (self.transfer_eta_label, eta_text),
            )
        )
        return True

    def _pull_finished(self, result: dict, request_id: int) -> bool:
        if request_id != self.pull_request_id:
            return False
        self.is_pulling = False
        if result.get("error"):
            self.record_status_label.setText("拉取失败")
            self._set_pull_progress_value(0, animated=False)
            self._set_pull_progress_visible(False)
            self._log(f"✗ 拉取异常: {result['error']}")
            QMessageBox.critical(self, "拉取失败", result["error"])
            return True
        self._set_pull_progress_value(100, animated=False)
        set_widget_texts(
            (
                (self.transfer_percent_label, "100%"),
                (self.transfer_speed_label, "速度 --"),
                (self.transfer_eta_label, "预计 00:00"),
                (self.record_status_label, "拉取完成"),
            )
        )
        self._set_pull_progress_visible(False)
        for line in pull_result_log_lines(result, self.product):
            self._log(line)
        QMessageBox.information(self, "拉取完成", pull_finished_message(result))
        self._apply_record_context(empty_record_context())
        self._set_current_bag_paths([])
        self.refresh_remote_bags(auto=True)
        return True
