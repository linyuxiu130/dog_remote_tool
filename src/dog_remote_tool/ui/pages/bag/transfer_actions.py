from __future__ import annotations

import threading
import time
from datetime import datetime

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QMessageBox

from dog_remote_tool.ui.widget_roles import widget_enabled
from dog_remote_tool.ui.pages.bag.helpers import (
    active_remote_bag_paths,
    started_at_from_remote_bag_paths,
)
from dog_remote_tool.ui.pages.bag.record_metadata import record_context
from dog_remote_tool.ui.pages.bag.transfer_delete import BagTransferDeleteMixin
from dog_remote_tool.ui.pages.bag.transfer_pull import BagTransferPullMixin


_TRANSFER_ACTIONS_PATCH_EXPORTS = (threading,)


class BagTransferActionsMixin(BagTransferPullMixin, BagTransferDeleteMixin):
    def selected_remote_paths(self) -> list[str]:
        rows = sorted({index.row() for index in self.remote_table.selectionModel().selectedRows()})
        paths = []
        for row in rows:
            item = self.remote_table.item(row, 0)
            if item:
                paths.append(item.data(Qt.UserRole))
        return paths

    def active_remote_bag_paths(self, selected_only: bool = False) -> list[str]:
        selected_paths = self.selected_remote_paths() if selected_only else None
        return active_remote_bag_paths(self.remote_bag_items, selected_paths)

    def _update_resume_button(self) -> bool:
        if not hasattr(self, "resume_btn"):
            return False
        active_paths = self.active_remote_bag_paths(selected_only=False)
        enabled = bool(active_paths) and not self.is_recording and not self.is_starting_recording
        current = widget_enabled(self.resume_btn, enabled)
        self.resume_btn.setEnabled(enabled)
        return current != enabled

    def resume_remote_recording(self) -> bool:
        if self.is_recording or self.is_starting_recording:
            QMessageBox.information(self, "提示", "当前已有录制任务")
            return False
        paths = self.active_remote_bag_paths(selected_only=True) or self.active_remote_bag_paths(selected_only=False)
        if not paths:
            QMessageBox.information(self, "提示", "未发现远端正在录制的Bag，请先刷新远端Bag列表")
            return False
        if len(paths) > 1:
            answer = QMessageBox.question(
                self,
                "接管录制",
                "将接管以下远端录制任务：\n\n" + "\n".join(paths),
                QMessageBox.Yes | QMessageBox.Cancel,
                QMessageBox.Yes,
            )
            if answer != QMessageBox.Yes:
                return False
        started_at = started_at_from_remote_bag_paths(paths)
        self._apply_record_context(
            record_context(
                paths,
                self.product,
                self.storage_combo.currentText(),
                self.cache_spin.value(),
                profile=self.profile(),
                started_at=started_at,
            )
        )
        self.is_recording = True
        self.stop_requested = False
        self.start_time = time.time()
        if started_at is not None:
            elapsed = max(0, int((datetime.now() - started_at).total_seconds()))
            self.start_time -= elapsed
        self.start_btn.setEnabled(False)
        self.resume_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self.record_status_label.setText("正在录制(已接管)")
        self._set_current_bag_paths(paths)
        self.current_bag_size_label.setText("查询中...")
        self.duration_timer.start()
        self._update_duration()
        self.bag_size_timer.start()
        self.refresh_current_bag_size()
        self._log("[录制] 已接管远端录制: " + "; ".join(paths))
        return True
