from __future__ import annotations

import os

from PyQt5.QtCore import QProcess, QTimer
from PyQt5.QtWidgets import QMessageBox

from dog_remote_tool.core.log_format import log_line
from dog_remote_tool.core.shell import quote


RESTART_CONFIRM_EXEMPT_TITLES = {
    "结束并保存建图",
}


class MainWindowRestartMixin:
    def restart_tool(self) -> None:
        if not self._confirm_restart_when_busy():
            return
        launcher = self.app_root / "启动.sh"
        if launcher.exists():
            restart_command = f"cd {quote(str(self.app_root))}; exec bash {quote(str(launcher))}"
        else:
            launcher = self.app_root / "AppRun"
            if not launcher.exists():
                QMessageBox.warning(self, "无法重启", f"未找到启动脚本：{self.app_root / '启动.sh'} 或 {launcher}")
                return
            restart_command = f"exec {quote(str(launcher))}"
        current_pid = os.getpid()
        command = (
            f"while kill -0 {current_pid} 2>/dev/null; do sleep 0.2; done; "
            f"{restart_command}"
        )
        if not QProcess.startDetached("bash", ["-lc", command]):
            QMessageBox.warning(self, "无法重启", "启动新工具进程失败。")
            return
        self.restart_tool_btn.setEnabled(False)
        self.restart_tool_btn.setText("重启中...")
        self._append_log(log_line("info", "正在重启工具..."))
        QTimer.singleShot(50, self.close)

    def _active_task_titles(self) -> list[str]:
        titles: list[str] = []
        for task in self.runner.tasks.values():
            try:
                if task.process.state() != QProcess.NotRunning:
                    title = str(task.title or "执行任务").strip()
                    titles.append(title if len(title) <= 120 else title[:117] + "...")
            except RuntimeError:
                continue
        return titles

    def _restart_blocking_task_titles(self) -> list[str]:
        return [title for title in self._active_task_titles() if title not in RESTART_CONFIRM_EXEMPT_TITLES]

    def _confirm_restart_when_busy(self) -> bool:
        blocking_titles = self._restart_blocking_task_titles()
        if not blocking_titles:
            return True
        if self.runner.stop_locked:
            QMessageBox.warning(
                self,
                "暂不能重启",
                "当前任务已进入 OTA/刷机保护阶段，本地停止按钮已锁定。\n请等待远端升级完成后再重启工具。",
            )
            return False

        dialog = QMessageBox(self)
        dialog.setIcon(QMessageBox.Warning)
        dialog.setWindowTitle("确认重启工具")
        dialog.setText("当前有任务正在运行")
        dialog.setInformativeText("重启会关闭当前工具窗口，并停止本地正在执行的命令。远端已启动的后台任务不一定会自动停止。")
        dialog.setDetailedText("\n".join(blocking_titles))
        cancel_button = dialog.addButton("取消", QMessageBox.RejectRole)
        restart_button = dialog.addButton("仍然重启", QMessageBox.DestructiveRole)
        restart_button.setObjectName("Danger")
        dialog.setDefaultButton(cancel_button)
        dialog.setEscapeButton(cancel_button)
        dialog.exec_()
        return dialog.clickedButton() is restart_button
