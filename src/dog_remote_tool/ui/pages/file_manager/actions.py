from __future__ import annotations

from PyQt5.QtCore import QProcess
from PyQt5.QtWidgets import QMessageBox

from dog_remote_tool.core.log_format import log_line
from dog_remote_tool.ui.pages.file_manager.helpers import overwrite_confirm_message, transfer_progress_percent


def _file_manager_page_module():
    from dog_remote_tool.ui.pages.file_manager import page as file_manager_page

    return file_manager_page


class FileManagerActionsMixin:
    def _run_file_command(self, spec, refresh_after: bool) -> bool:
        conflict = self.runner.conflict_reason(spec)
        if conflict:
            self.pending_select_names = set()
            self.runner.output.emit(log_line("warn", conflict))
            return False
        display = spec.display_command or spec.title
        task_id = self.runner.run(spec, display)
        if task_id is None:
            self.pending_refresh_after_task = False
            self.pending_select_names = set()
            self.runner_task_title = ""
            self.runner_task_id = 0
            self.status_label.setText("任务未启动")
            return False
        if refresh_after:
            self.searching = False
        self.pending_refresh_after_task = refresh_after
        self.runner_task_title = display
        self.status_label.setText("任务执行中")
        self.runner_task_id = task_id
        return True

    def _run_combined_commands(self, specs, display: str, refresh_after: bool) -> bool:
        specs = [spec for spec in specs if spec]
        if not specs:
            return False
        concurrency = "parallel" if all(getattr(spec, "concurrency", "exclusive") == "parallel" for spec in specs) else "exclusive"
        locks = tuple(dict.fromkeys(lock for spec in specs for lock in (getattr(spec, "locks", ()) or ())))
        conflict = self.runner.conflict_reason(concurrency=concurrency, locks=locks)
        if conflict:
            self.pending_select_names = set()
            self.runner.output.emit(log_line("warn", conflict))
            return False
        command = " && ".join(spec.command for spec in specs)
        task_id = self.runner.run(command, display, concurrency=concurrency, locks=locks)
        if task_id is None:
            self.pending_refresh_after_task = False
            self.pending_select_names = set()
            self.runner_task_title = ""
            self.runner_task_id = 0
            self.status_label.setText("任务未启动")
            return False
        if refresh_after:
            self.searching = False
        self.pending_refresh_after_task = refresh_after
        self.runner_task_title = display
        self.status_label.setText("传输中")
        self._show_transfer_progress(display)
        self.runner_task_id = task_id
        return True

    def _show_transfer_progress(self, title: str) -> None:
        self.transfer_active = True
        self.transfer_title = title
        self.transfer_label.setText(title)
        self.transfer_progress.setValue(0)
        self.transfer_panel.show()

    def _watch_transfer_output(self, text: str) -> None:
        if not self.transfer_active:
            return
        value = transfer_progress_percent(text)
        if value is None:
            return
        self.transfer_progress.setValue(value)
        self.transfer_label.setText(f"{self.transfer_title}  {value}%")

    def _finish_transfer_progress(self, code: int) -> None:
        self.transfer_active = False
        if code == 0:
            self.transfer_progress.setValue(100)
            self.transfer_label.setText("传输完成")
            _file_manager_page_module().QTimer.singleShot(1800, self.transfer_panel.hide)
        else:
            self.transfer_label.setText("传输失败")

    def _confirm_overwrite(self, action: str, names: list[str]) -> bool:
        answer = QMessageBox.question(self, "确认覆盖", overwrite_confirm_message(action, names))
        return answer == QMessageBox.Yes

    def _run_capture(self, spec, status: str, callback) -> bool:
        if self.action_slot.is_running():
            self.runner.output.emit(log_line("warn", "已有任务运行，请先停止或等待结束。", scope="文件管理"))
            return False
        conflict = self.runner.conflict_reason(spec)
        if conflict:
            self.runner.output.emit(log_line("warn", conflict))
            return False
        self.action_callback = callback
        process, request_id = self.action_slot.start_spec(spec)
        if process is None:
            self.action_callback = None
            return False
        process.readyReadStandardOutput.connect(lambda: self._read_action_output(process, request_id))
        process.finished.connect(lambda code, _status: self._action_finished(process, request_id, code))
        self.status_label.setText(status)
        self.cancel_action_btn.show()
        self.runner.output.emit(log_line("info", f"开始：{spec.display_command or spec.title}", scope="文件管理"))
        process.start()
        return True

    def cancel_action(self) -> bool:
        if not self.action_slot.is_running():
            return False
        self.status_label.setText("正在停止")
        self.action_callback = None
        self.cancel_action_btn.hide()
        self.action_slot.stop()
        self.status_label.setText("已停止")
        return True

    def _read_action_output(self, process: QProcess, request_id: int) -> bool:
        return self.action_slot.read_available_output(process, request_id)

    def _action_finished(self, process: QProcess, request_id: int, exit_code: int) -> bool:
        output = self.action_slot.finish(process, request_id)
        if output is None:
            return False
        callback = self.action_callback
        self.action_callback = None
        self.cancel_action_btn.hide()
        if callable(callback):
            callback(output, exit_code)
        return True
