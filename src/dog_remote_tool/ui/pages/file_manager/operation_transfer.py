from __future__ import annotations

from pathlib import Path

from dog_remote_tool.core.log_format import log_line
from dog_remote_tool.modules import file_manager
from dog_remote_tool.ui.pages.file_manager.operation_refs import file_manager_page_module


class FileManagerTransferMixin:
    def pick_upload_files(self) -> bool:
        page = file_manager_page_module()
        dialog = page.UploadDialog(self.current_path, self)
        if dialog.exec_() != page.QDialog.Accepted:
            return False
        return self.upload_paths(dialog.paths())

    def upload_paths(self, paths: list[str], remote_dir: str | None = None) -> bool:
        target_dir = file_manager.clean_remote_path(remote_dir or self.current_path, self.profile().home)
        existing = self._existing_names() if target_dir == self.current_path else set()
        conflicts = [Path(path).name for path in paths if Path(path).name in existing]
        if conflicts and not self._confirm_overwrite("上传", conflicts):
            return False
        if conflicts:
            self.runner.output.emit(log_line("warn", f"上传将覆盖：{'、'.join(conflicts[:8])}", scope="文件"))
        specs = [file_manager.upload_command(self.profile(), path, target_dir) for path in paths]
        self.pending_select_names = {Path(path).name for path in paths} if target_dir == self.current_path else set()
        return self._run_combined_commands(specs, f"上传 {len(specs)} 项到 {target_dir}", refresh_after=True)

    def download_selected(self) -> bool:
        page = file_manager_page_module()
        items = self.selected_remote_items()
        if not items:
            page.QMessageBox.information(self, "未选择文件", "请先选择要下载的远端文件或目录。")
            return False
        local_dir = page.QFileDialog.getExistingDirectory(self, "选择下载目录", str(Path.home()))
        if not local_dir:
            return False
        conflicts = [item.name for item in items if (Path(local_dir) / item.name).exists()]
        if conflicts and not self._confirm_overwrite("下载", conflicts):
            return False
        if conflicts:
            self.runner.output.emit(log_line("warn", f"下载将覆盖：{'、'.join(conflicts[:8])}", scope="文件"))
        specs = [file_manager.download_command(self.profile(), item.path, local_dir) for item in items]
        return self._run_combined_commands(specs, f"下载 {len(specs)} 项到 {local_dir}", refresh_after=False)
