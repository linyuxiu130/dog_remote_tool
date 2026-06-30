from __future__ import annotations

from dog_remote_tool.core.log_format import log_line
from dog_remote_tool.core.text import last_nonempty_line
from dog_remote_tool.modules import file_manager
from dog_remote_tool.ui.pages.file_manager.operation_refs import file_manager_page_module


class FileManagerPreviewMixin:
    def preview_selected(self) -> bool:
        page = file_manager_page_module()
        items = self.selected_remote_items()
        if len(items) != 1 or items[0].kind != "file":
            page.QMessageBox.information(self, "选择文件", "请选择一个普通文件进行预览。")
            return False
        return self.preview_item(items[0])

    def preview_item(self, item: file_manager.RemoteFileItem) -> bool:
        spec = file_manager.preview_command(self.profile(), item.path)
        return self._run_capture(spec, "预览读取中", self._show_preview)

    def _show_preview(self, output: str, exit_code: int) -> None:
        page = file_manager_page_module()
        payload, error = file_manager.parse_preview_output(output)
        if exit_code != 0 or error:
            page.QMessageBox.warning(self, "预览失败", error or "预览失败，请查看详细日志。")
            self.status_label.setText("预览失败")
            return
        dialog = page.TextPreviewDialog(
            str(payload.get("path") or ""),
            str(payload.get("text") or ""),
            file_manager.format_size(int(payload.get("size") or 0)),
            bool(payload.get("truncated")),
            self,
        )
        self.preview_dialog = dialog
        self.preview_path = str(payload.get("path") or "")
        dialog.save_requested.connect(self.save_preview_text)
        dialog.exec_()
        self.preview_dialog = None
        self.preview_path = ""
        self.status_label.setText("预览完成")

    def save_preview_text(self, text: str) -> bool:
        if not self.preview_path:
            return False
        if self.runner.is_running() or self.action_slot.is_running():
            if self.preview_dialog:
                self.preview_dialog.mark_save_failed("等待任务")
            self.runner.output.emit(log_line("warn", "当前已有任务运行，请先停止或等待结束。"))
            return False
        spec = file_manager.save_text_command(self.profile(), self.preview_path, text)
        return self._run_capture(spec, "保存中", lambda output, code, saved_text=text: self._show_save_result(output, code, saved_text))

    def _show_save_result(self, output: str, exit_code: int, text: str) -> None:
        page = file_manager_page_module()
        if exit_code == 0:
            if self.preview_dialog:
                self.preview_dialog.mark_saved(text)
            self.status_label.setText("已保存")
            self.runner.output.emit(log_line("info", "远端文本已保存。", scope="文件"))
            page.QTimer.singleShot(400, lambda: self.refresh_directory(force=True, reason="保存完成"))
            return
        message = last_nonempty_line(output) or "保存失败，请查看详细日志。"
        if self.preview_dialog:
            self.preview_dialog.mark_save_failed("保存失败")
        page.QMessageBox.warning(self, "保存失败", message)
        self.status_label.setText("保存失败")
