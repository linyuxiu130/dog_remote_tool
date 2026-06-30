from __future__ import annotations

import json

from PyQt5.QtCore import QProcess, Qt

from dog_remote_tool.core.log_format import log_line
from dog_remote_tool.modules import file_manager
from dog_remote_tool.ui.pages.file_manager.favorites import favorite_storage_key, short_path_label, stored_favorites
from dog_remote_tool.ui.pages.file_manager.helpers import (
    visible_counts,
    visible_items,
)


def _file_manager_page_module():
    from dog_remote_tool.ui.pages.file_manager import page as file_manager_page

    return file_manager_page


class FileManagerBrowserMixin:
    def _favorite_key(self) -> str:
        return favorite_storage_key(self.profile().key)

    def _stored_favorites(self) -> list[str]:
        raw = self.settings.value(self._favorite_key(), "", type=str)
        profile = self.profile()
        return stored_favorites(profile.key, profile.home, raw)

    def _reload_favorites(self) -> None:
        if not hasattr(self, "favorite_combo"):
            return
        favorites = self._stored_favorites()
        with _file_manager_page_module().QSignalBlocker(self.favorite_combo):
            self.favorite_combo.clear()
            self.favorite_combo.addItem("常用路径", "")
            for path in favorites:
                label = short_path_label(path)
                self.favorite_combo.addItem(label, path)
                self.favorite_combo.setItemData(self.favorite_combo.count() - 1, path, Qt.ToolTipRole)
            self.favorite_combo.setCurrentIndex(0)
        self.favorite_combo.setVisible(bool(favorites))

    def _favorite_selected(self, index: int) -> None:
        path = self.favorite_combo.itemData(index)
        if path:
            self.navigate_to(str(path))
        with _file_manager_page_module().QSignalBlocker(self.favorite_combo):
            self.favorite_combo.setCurrentIndex(0)

    def add_current_favorite(self) -> None:
        path = file_manager.clean_remote_path(self.current_path, self.profile().home)
        favorites = self._stored_favorites()
        if path not in favorites:
            favorites.append(path)
            self.settings.setValue(self._favorite_key(), json.dumps(favorites, ensure_ascii=False))
            self._reload_favorites()

    def activate_page(self) -> None:
        if self.page_active:
            return
        self.page_active = True
        self.refresh_directory(force=True, reason="打开页面")

    def deactivate_page(self) -> None:
        self.page_active = False
        self._stop_page_processes(stop_action=False)

    def _profile_changed(self, _profile) -> None:
        self._stop_page_processes(stop_action=True)
        self.pending_refresh_after_task = False
        self.pending_total_size_paths = []
        self.pending_select_names = set()
        self.remote_clipboard_paths = []
        self.remote_clipboard_mode = ""
        self.clear_remote_clipboard_on_success = False
        self.transfer_active = False
        self.transfer_title = ""
        self.runner_task_title = ""
        self.runner_task_id = 0
        self.transfer_panel.hide()
        self.preview_path = ""
        self.current_path = self.profile().home
        self.last_successful_path = self.current_path
        self.current_items = []
        self.current_signature = ""
        self.last_error_message = ""
        self.auto_error_repeats = 0
        self.searching = False
        self.search_edit.clear()
        self._set_path_edit(self.current_path)
        self._update_profile_badge()
        self._reload_favorites()
        self._populate_table([])
        if self.page_active:
            _file_manager_page_module().QTimer.singleShot(100, lambda: self.refresh_directory(force=True, reason="设备切换"))

    def _runner_finished(self, task_id: int, code: int, title: str) -> None:
        _ = title
        if task_id != self.runner_task_id:
            return
        self.runner_task_title = ""
        self.runner_task_id = 0
        if code == 0 and self.clear_remote_clipboard_on_success:
            self.remote_clipboard_paths = []
            self.remote_clipboard_mode = ""
            self.clear_remote_clipboard_on_success = False
        elif code != 0:
            self.clear_remote_clipboard_on_success = False
        if self.transfer_active:
            self._finish_transfer_progress(code)
        if not self.pending_refresh_after_task:
            return
        self.pending_refresh_after_task = False
        if code != 0:
            self.status_label.setText("任务失败，未刷新")
            return
        self.status_label.setText("任务完成，刷新中")
        _file_manager_page_module().QTimer.singleShot(700, lambda: self.refresh_directory(force=True, reason="任务完成"))

    def refresh_directory(self, force: bool = False, reason: str = "") -> bool:
        if not self.page_active:
            return False
        if self.list_slot.is_running():
            return False
        profile = self.profile()
        self.current_path = file_manager.clean_remote_path(self.current_path, profile.home)
        self._set_path_edit(self.current_path)
        spec = file_manager.list_command(profile, self.current_path)
        process, request_id = self.list_slot.start_spec(spec)
        if process is None:
            return False
        process.readyReadStandardOutput.connect(lambda: self._read_list_output(process, request_id))
        process.finished.connect(lambda code, _status: self._list_finished(process, request_id, code, force, reason))
        self.status_label.setText(reason or "读取中")
        process.start()
        return True

    def _read_list_output(self, process: QProcess, request_id: int) -> bool:
        return self.list_slot.read_available_output(process, request_id)

    def _list_finished(self, process: QProcess, request_id: int, exit_code: int, force: bool, reason: str) -> bool:
        output = self.list_slot.finish(process, request_id)
        if output is None:
            return False
        current, items, error = file_manager.parse_list_output(output)
        if current:
            self.current_path = current
            self._set_path_edit(current)
        if exit_code == 0 and not error:
            self.last_successful_path = self.current_path
            self.last_error_message = ""
            self.auto_error_repeats = 0
            signature = self._signature(items)
            if force or signature != self.current_signature:
                self.current_items = items
                self.current_signature = signature
                self._populate_table(items)
            self._set_items_status(items)
        else:
            message = file_manager.summarize_list_failure(output, exit_code, error)
            self.status_label.setText("读取失败")
            self.current_items = []
            self.current_signature = ""
            self._populate_table([])
            self.runner.output.emit(log_line("warn", f"远端目录读取失败：{message}", scope="文件"))
            self.last_error_message = message
        return True

    def _populate_table(self, items: list[file_manager.RemoteFileItem]) -> None:
        selected_paths = {item.path for item in self.selected_remote_items()}
        shown_items = self._visible_items(items)
        if self.current_view_mode == "icon":
            matched_pending = self.icon_view.populate(shown_items, selected_paths, self.pending_select_names)
        else:
            matched_pending = self.table.populate(shown_items, selected_paths, self.pending_select_names)
        if matched_pending:
            self.pending_select_names.clear()
        self._update_selection_detail()

    def _visible_items(self, items: list[file_manager.RemoteFileItem]) -> list[file_manager.RemoteFileItem]:
        return visible_items(items, self.show_hidden, self.MAX_RENDER_ITEMS)

    def _visible_counts(self, items: list[file_manager.RemoteFileItem]) -> tuple[int, int, int]:
        return visible_counts(items, self.show_hidden, self.MAX_RENDER_ITEMS)

    def _set_items_status(self, items: list[file_manager.RemoteFileItem]) -> None:
        visible_count, hidden_count, omitted_count = self._visible_counts(items)
        parts = [f"{visible_count} 项"]
        if omitted_count:
            parts.append(f"仅显示前 {self.MAX_RENDER_ITEMS} 项")
        if hidden_count and not self.show_hidden:
            parts.append(f"隐藏 {hidden_count}")
        self.status_label.setText("，".join(parts))

    def toggle_hidden_files(self) -> None:
        self.show_hidden = self.hidden_btn.isChecked()
        self.hidden_btn.setText("关闭隐藏" if self.show_hidden else "显示隐藏")
        self._populate_table(self.current_items)
        self._set_items_status(self.current_items)

    def toggle_view_mode(self) -> None:
        selected_paths = {item.path for item in self.selected_remote_items()}
        self.current_view_mode = "tree" if self.current_view_mode == "icon" else "icon"
        self.settings.setValue("file_manager/view_mode", self.current_view_mode)
        self.view_stack.setCurrentWidget(self.icon_view if self.current_view_mode == "icon" else self.table)
        self.view_toggle_btn.setText("列表显示" if self.current_view_mode == "icon" else "图标显示")
        self._populate_table_with_selection(self.current_items, selected_paths)

    def _populate_table_with_selection(self, items: list[file_manager.RemoteFileItem], selected_paths: set[str]) -> None:
        shown_items = self._visible_items(items)
        if self.current_view_mode == "icon":
            self.icon_view.populate(shown_items, selected_paths, set())
        else:
            self.table.populate(shown_items, selected_paths, set())
        self._update_selection_detail()
