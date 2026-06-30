from __future__ import annotations

from dog_remote_tool.modules import file_manager
from dog_remote_tool.ui.pages.file_manager.helpers import names_summary
from dog_remote_tool.ui.pages.file_manager.operation_refs import file_manager_page_module


class FileManagerEditMixin:
    def make_directory(self) -> bool:
        page = file_manager_page_module()
        dialog = page.NameDialog("新建目录", "目录名", helper=f"远端位置：{self.current_path}", parent=self)
        if dialog.exec_() != page.QDialog.Accepted:
            return False
        name = dialog.name()
        if name.strip() in self._existing_names():
            page.QMessageBox.warning(self, "名称已存在", "当前目录已有同名文件或目录。")
            return False
        try:
            spec = file_manager.mkdir_command(self.profile(), self.current_path, name)
        except ValueError as exc:
            page.QMessageBox.warning(self, "名称不可用", str(exc))
            return False
        self.pending_select_names = {name.strip()}
        return self._run_file_command(spec, refresh_after=True)

    def make_file(self) -> bool:
        page = file_manager_page_module()
        dialog = page.NameDialog("新建文件", "文件名", helper=f"远端位置：{self.current_path}", parent=self)
        if dialog.exec_() != page.QDialog.Accepted:
            return False
        name = dialog.name()
        if name.strip() in self._existing_names():
            page.QMessageBox.warning(self, "名称已存在", "当前目录已有同名文件或目录。")
            return False
        try:
            spec = file_manager.touch_command(self.profile(), self.current_path, name)
        except ValueError as exc:
            page.QMessageBox.warning(self, "名称不可用", str(exc))
            return False
        self.pending_select_names = {name.strip()}
        return self._run_file_command(spec, refresh_after=True)

    def rename_selected(self) -> bool:
        page = file_manager_page_module()
        items = self.selected_remote_items()
        if len(items) != 1:
            page.QMessageBox.information(self, "选择一项", "重命名一次只能选择一个文件或目录。")
            return False
        item = items[0]
        dialog = page.NameDialog(
            "重命名",
            "新名称",
            initial=item.name,
            helper=f"远端位置：{file_manager.parent_path(item.path)}",
            parent=self,
        )
        if dialog.exec_() != page.QDialog.Accepted:
            return False
        new_name = dialog.name()
        if new_name == item.name:
            return False
        if new_name.strip() in self._existing_names():
            page.QMessageBox.warning(self, "名称已存在", "当前目录已有同名文件或目录。")
            return False
        try:
            spec = file_manager.rename_command(self.profile(), item.path, new_name)
        except ValueError as exc:
            page.QMessageBox.warning(self, "名称不可用", str(exc))
            return False
        self.pending_select_names = {new_name.strip()}
        return self._run_file_command(spec, refresh_after=True)

    def delete_selected(self) -> bool:
        page = file_manager_page_module()
        items = self.selected_remote_items()
        if not items:
            page.QMessageBox.information(self, "未选择文件", "请先选择要删除的远端文件或目录。")
            return False
        outside_home = [item.path for item in items if not self._is_under_home(item.path)]
        if outside_home:
            answer = page.QMessageBox.warning(
                self,
                "高风险删除",
                "选中项不在当前设备 Home 目录下，可能需要 sudo 删除。\n确认继续？",
                page.QMessageBox.Yes | page.QMessageBox.No,
                page.QMessageBox.No,
            )
            if answer != page.QMessageBox.Yes:
                return False
        names = names_summary([item.name for item in items])
        answer = page.QMessageBox.question(
            self,
            "确认删除",
            f"确认删除远端 {names}？\n目录会递归删除，操作不可恢复。",
        )
        if answer != page.QMessageBox.Yes:
            return False
        try:
            spec = file_manager.delete_command(self.profile(), [item.path for item in items])
        except ValueError as exc:
            page.QMessageBox.warning(self, "无法删除", str(exc))
            return False
        return self._run_file_command(spec, refresh_after=True)
