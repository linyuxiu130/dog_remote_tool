from __future__ import annotations

from PyQt5.QtCore import Qt

from dog_remote_tool.modules import bag
from dog_remote_tool.ui.pages.bag.helpers import (
    remote_bag_status_text,
    remote_bag_table_row,
    remote_disk_text,
    remote_scan_dirs,
)
from dog_remote_tool.ui.pages.bag.recording_refs import bag_page_module
from dog_remote_tool.ui.widget_roles import set_widget_text, set_widget_text_tooltip, set_widget_texts


class BagRecordingRemoteMixin:
    def refresh_remote_bags(self, auto: bool = False) -> bool:
        if auto and not self.page_active:
            return False
        if self.is_refreshing_remote or self.is_pulling or (auto and self.is_recording):
            return False
        self.is_refreshing_remote = True
        self.remote_bags_request_id += 1
        request_id = self.remote_bags_request_id
        set_widget_texts(
            (
                (self.remote_status_label, "刷新中..."),
                (self.remote_space_label, "可用空间: 查询中..."),
            )
        )
        backend = self.backend()
        scan_dirs = remote_scan_dirs(self.remote_path.text().strip(), self.default_remote_bag_path(), self.profile().home)
        bag_page_module().threading.Thread(target=self._remote_bags_worker, args=(backend, scan_dirs, request_id), daemon=True).start()
        return True

    def _remote_bags_worker(self, backend: bag.BagBackend, scan_dirs: list[str], request_id: int) -> None:
        try:
            items, disk = backend.scan_remote_bags(scan_dirs)
            self.remote_bags_done.emit(items, disk, "", request_id)
        except Exception as exc:
            self.remote_bags_done.emit([], None, str(exc), request_id)

    def _remote_bag_list_finished(self, items: list, disk, error: str, request_id: int) -> bool:
        if request_id != self.remote_bags_request_id:
            return False
        bag_page = bag_page_module()
        self.is_refreshing_remote = False
        self.remote_bag_items = items
        self.remote_table.setUpdatesEnabled(False)
        try:
            self.remote_table.setRowCount(0)
            if error:
                detail = error[:80]
                set_widget_text_tooltip(self.remote_status_label, f"刷新失败: {detail}", error)
                set_widget_text(self.remote_space_label, "可用空间: 查询失败")
                return True
            set_widget_text(self.remote_space_label, remote_disk_text(disk))
            self.remote_table.setRowCount(len(items))
            for row, item in enumerate(items):
                active, values, path = remote_bag_table_row(item)
                for col, value in enumerate(values):
                    cell = bag_page.QTableWidgetItem(value)
                    cell.setData(Qt.UserRole, path)
                    if active:
                        cell.setForeground(bag_page.QColor("#047857"))
                    self.remote_table.setItem(row, col, cell)
            set_widget_text_tooltip(self.remote_status_label, remote_bag_status_text(items), "")
            return True
        finally:
            self.remote_table.setUpdatesEnabled(True)
            self._update_resume_button()
