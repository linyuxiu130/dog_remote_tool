from __future__ import annotations

from PyQt5.QtWidgets import QMessageBox

from dog_remote_tool.ui.pages.bag.helpers import (
    delete_confirm_message,
    delete_finished_message,
    unsafe_remote_bag_paths,
)


def _transfer_actions_module():
    from dog_remote_tool.ui.pages.bag import transfer_actions

    return transfer_actions


class BagTransferDeleteMixin:
    def delete_selected_remote_bags(self) -> bool:
        if self.is_deleting:
            return False
        paths = self.selected_remote_paths()
        if not paths:
            QMessageBox.information(self, "提示", "请先选择要删除的远端Bag")
            return False
        backend = self.backend()
        unsafe = unsafe_remote_bag_paths(paths, backend.profile)
        if unsafe:
            QMessageBox.warning(self, "拒绝删除", "以下路径不符合录包目录规则：\n" + "\n".join(unsafe))
            return False
        answer = QMessageBox.question(self, "确认删除远端Bag", delete_confirm_message(paths), QMessageBox.Yes | QMessageBox.Cancel, QMessageBox.Cancel)
        if answer != QMessageBox.Yes:
            return False
        self.delete_request_id += 1
        request_id = self.delete_request_id
        self.is_deleting = True
        self.delete_selected_btn.setEnabled(False)
        _transfer_actions_module().threading.Thread(target=self._delete_worker, args=(backend, paths, request_id), daemon=True).start()
        return True

    def _delete_worker(self, backend, paths: list[str], request_id: int) -> None:
        deleted, failed = backend.delete_remote_bags(paths, auto_delete=False)
        self.delete_done.emit(deleted, failed, request_id)

    def _delete_finished(self, deleted: list, failed: list, request_id: int) -> bool:
        if request_id != self.delete_request_id:
            return False
        self.is_deleting = False
        self.delete_selected_btn.setEnabled(True)
        warn, message = delete_finished_message(deleted, failed)
        if warn:
            QMessageBox.warning(self, "删除完成", message)
        else:
            QMessageBox.information(self, "删除完成", message)
        self.refresh_remote_bags(auto=True)
        return True
