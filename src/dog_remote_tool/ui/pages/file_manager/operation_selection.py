from __future__ import annotations

from dog_remote_tool.core.log_format import log_line
from dog_remote_tool.modules import file_manager
from dog_remote_tool.ui.pages.file_manager.helpers import selected_detail_text
from dog_remote_tool.ui.pages.file_manager.operation_refs import file_manager_page_module


class FileManagerSelectionMixin:
    def selected_remote_items(self) -> list[file_manager.RemoteFileItem]:
        return self._active_view().selected_remote_items()

    def _active_view(self):
        if hasattr(self, "view_stack"):
            current = self.view_stack.currentWidget()
            if current in (self.icon_view, self.table):
                return current
        return self.icon_view if self.current_view_mode == "icon" else self.table

    def _update_selection_detail(self) -> None:
        if not hasattr(self, "detail_label"):
            return
        self.detail_label.setText(selected_detail_text(self.selected_remote_items()))

    def calculate_total_size(self) -> bool:
        page = file_manager_page_module()
        items = self.selected_remote_items()
        targets = [item for item in items if item.kind == "dir"] or items
        if not targets:
            page.QMessageBox.information(self, "未选择项目", "请先选择要计算大小的远端目录或文件。")
            return False
        try:
            spec = file_manager.dir_total_size_command(self.profile(), [item.path for item in targets])
        except ValueError as exc:
            page.QMessageBox.warning(self, "无法计算", str(exc))
            return False
        self.pending_total_size_paths = [item.path for item in targets]
        return self._run_capture(spec, "计算大小中", self._show_total_size)

    def _show_total_size(self, output: str, exit_code: int) -> None:
        page = file_manager_page_module()
        size, error = file_manager.parse_total_size_output(output)
        if exit_code != 0 or size is None:
            page.QMessageBox.warning(self, "计算失败", error or "计算失败，请查看详细日志。")
            self.status_label.setText("计算失败")
            self.pending_total_size_paths = []
            return
        value = file_manager.format_size(size)
        self.status_label.setText(f"总大小 {value}")
        self.runner.output.emit(log_line("info", f"选中项总大小：{value}", scope="文件"))
        if len(self.pending_total_size_paths) == 1:
            self._update_item_size_display(self.pending_total_size_paths[0], size)
        self.pending_total_size_paths = []

    def _update_item_size_display(self, path: str, size: int) -> None:
        item = next((existing for existing in self.current_items if existing.path == path), None)
        if not item:
            return
        updated = file_manager.RemoteFileItem(
            item.name,
            item.path,
            item.kind,
            size,
            item.mtime,
            item.mode,
            item.owner,
            item.group,
        )
        self.table.update_item(updated)
        self.icon_view.update_item(updated)
        self.current_items = [updated if existing.path == path else existing for existing in self.current_items]
        self.current_signature = self._signature(self.current_items)
