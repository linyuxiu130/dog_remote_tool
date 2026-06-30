from __future__ import annotations

from PyQt5.QtWidgets import QApplication, QMenu, QMessageBox

from dog_remote_tool.modules import file_manager


class FileManagerClipboardMixin:
    def copy_selected_paths(self) -> None:
        items = self.selected_remote_items()
        if not items:
            QApplication.clipboard().setText(self.current_path)
            self.status_label.setText("已复制当前路径")
            return
        QApplication.clipboard().setText("\n".join(item.path for item in items))
        self.status_label.setText(f"已复制 {len(items)} 项路径")

    def copy_remote_selection(self) -> None:
        self._set_remote_clipboard("copy")

    def cut_remote_selection(self) -> None:
        self._set_remote_clipboard("cut")

    def _set_remote_clipboard(self, mode: str) -> None:
        items = self.selected_remote_items()
        if not items:
            self.status_label.setText("未选择项目")
            return
        self.remote_clipboard_paths = [item.path for item in items]
        self.remote_clipboard_mode = mode
        self.clear_remote_clipboard_on_success = False
        label = "复制" if mode == "copy" else "剪切"
        self.status_label.setText(f"已{label} {len(items)} 项，选择目录后粘贴")

    def paste_remote_clipboard(self) -> bool:
        if not self.remote_clipboard_paths or self.remote_clipboard_mode not in {"copy", "cut"}:
            self.status_label.setText("剪贴板为空")
            return False
        try:
            spec = file_manager.paste_command(
                self.profile(),
                self.remote_clipboard_paths,
                self.current_path,
                move=self.remote_clipboard_mode == "cut",
            )
        except ValueError as exc:
            QMessageBox.warning(self, "无法粘贴", str(exc))
            return False
        action = "剪切粘贴" if self.remote_clipboard_mode == "cut" else "复制粘贴"
        started = self._run_file_command(spec, refresh_after=True)
        self.clear_remote_clipboard_on_success = started and self.remote_clipboard_mode == "cut"
        if started:
            self.status_label.setText(f"{action}中")
        return started

    def _show_context_menu(self, pos) -> None:
        view = self.sender() if self.sender() in (self.icon_view, self.table) else self._active_view()
        view.select_item_at(pos)
        items = self.selected_remote_items()
        menu = QMenu(self)
        single = items[0] if len(items) == 1 else None
        open_action = menu.addAction("进入目录")
        open_action.setEnabled(bool(single and single.kind == "dir"))
        preview_action = menu.addAction("编辑文本")
        preview_action.setEnabled(bool(single and single.kind == "file"))
        download_action = menu.addAction("下载")
        download_action.setEnabled(bool(items))
        size_action = menu.addAction("计算总大小")
        size_action.setEnabled(bool(items))
        copy_item_action = menu.addAction("复制")
        copy_item_action.setEnabled(bool(items))
        cut_item_action = menu.addAction("剪切")
        cut_item_action.setEnabled(bool(items))
        paste_action = menu.addAction("粘贴到当前目录")
        paste_action.setEnabled(bool(self.remote_clipboard_paths))
        rename_action = menu.addAction("重命名")
        rename_action.setEnabled(len(items) == 1)
        delete_action = menu.addAction("删除")
        delete_action.setEnabled(bool(items))
        upload_action = menu.addAction("上传到当前目录")
        new_file_action = menu.addAction("新建文件")
        new_dir_action = menu.addAction("新建目录")
        copy_action = menu.addAction("复制路径")
        favorite_action = menu.addAction("收藏当前路径")
        refresh_action = menu.addAction("刷新")
        chosen = menu.exec_(view.viewport().mapToGlobal(pos))
        if chosen == open_action and single:
            self.navigate_to(single.path)
        elif chosen == preview_action:
            self.preview_selected()
        elif chosen == download_action:
            self.download_selected()
        elif chosen == size_action:
            self.calculate_total_size()
        elif chosen == copy_item_action:
            self.copy_remote_selection()
        elif chosen == cut_item_action:
            self.cut_remote_selection()
        elif chosen == paste_action:
            self.paste_remote_clipboard()
        elif chosen == rename_action:
            self.rename_selected()
        elif chosen == delete_action:
            self.delete_selected()
        elif chosen == upload_action:
            self.pick_upload_files()
        elif chosen == new_file_action:
            self.make_file()
        elif chosen == new_dir_action:
            self.make_directory()
        elif chosen == copy_action:
            self.copy_selected_paths()
        elif chosen == favorite_action:
            self.add_current_favorite()
        elif chosen == refresh_action:
            self.refresh_directory(force=True, reason="手动刷新")

    def _existing_names(self) -> set[str]:
        return {item.name for item in self.current_items}
