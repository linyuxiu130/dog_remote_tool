from __future__ import annotations

from PyQt5.QtCore import Qt

from dog_remote_tool.modules import file_manager
from dog_remote_tool.ui.pages.file_manager.operation_refs import file_manager_page_module


class FileManagerNavigationMixin:
    def _open_table_index(self, index) -> None:
        item = self.table.item_data(index)
        if not item:
            return
        if item.kind == "dir":
            self.navigate_to(item.path)
        elif item.kind == "file":
            self.preview_item(item)

    def _open_icon_item(self, index) -> None:
        data = index.data(Qt.UserRole) if index else None
        if not isinstance(data, file_manager.RemoteFileItem):
            return
        if data.kind == "dir":
            self.navigate_to(data.path)
        elif data.kind == "file":
            self.preview_item(data)

    def navigate_to(self, path: str) -> None:
        self.searching = False
        self.search_edit.clear()
        self.current_path = file_manager.clean_remote_path(path, self.profile().home)
        self.refresh_directory(force=True, reason="切换目录")

    def go_parent(self) -> None:
        self.navigate_to(file_manager.parent_path(self.current_path))

    def go_home(self) -> None:
        self.navigate_to(self.profile().home)

    def search_files(self) -> bool:
        keyword = self.search_edit.text().strip()
        if not keyword:
            self.clear_search()
            return False
        spec = file_manager.search_command(self.profile(), self.current_path, keyword, True)
        return self._run_capture(spec, "搜索中", self._show_search_results)

    def clear_search(self) -> None:
        self.searching = False
        self.search_edit.clear()
        self.refresh_directory(force=True, reason="清除搜索")

    def _show_search_results(self, output: str, exit_code: int) -> None:
        current, items, error = file_manager.parse_list_output(output)
        if current:
            self.current_path = current
            self._set_path_edit(current)
        if exit_code != 0 or error:
            message = file_manager.summarize_list_failure(output, exit_code, error)
            file_manager_page_module().QMessageBox.warning(self, "搜索失败", message)
            self.status_label.setText("搜索失败")
            return
        self.searching = True
        self.current_items = items
        self.current_signature = self._signature(items)
        self._populate_table(items)
        suffix = "，仅显示前 500 项" if len(items) >= 500 else ""
        visible_count, hidden_count, omitted_count = self._visible_counts(items)
        hidden_note = f"，隐藏 {hidden_count}" if hidden_count and not self.show_hidden else ""
        render_note = f"，界面仅显示前 {self.MAX_RENDER_ITEMS} 项" if omitted_count else ""
        self.status_label.setText(f"搜索 {visible_count} 项{hidden_note}{suffix}{render_note}")
