from __future__ import annotations

from PyQt5.QtCore import QProcess

from dog_remote_tool.core.text import strip_ansi
from dog_remote_tool.ui.status_text import task_not_started_text


def _dashboard_page_module():
    from dog_remote_tool.ui.pages.dashboard import page as dashboard_page

    return dashboard_page


class DashboardStatusMixin:
    def _release_title(self, profile) -> str:
        platform = str(getattr(profile, "platform", "") or "").strip()
        return f"{platform}版本" if platform else "平台版本"

    def _set_current_device(self, profile) -> bool:
        dashboard_page = _dashboard_page_module()
        release_title = self._release_title(profile)
        release_text = ""
        release_tooltip = ""
        package_text = "读取中"
        launch_text = "读取中"
        current_release_title = dashboard_page.widget_text(self.release_title_label)
        current_release = dashboard_page.widget_text(self.device_release_label)
        current_release_tooltip = dashboard_page.widget_tooltip(self.device_release_label)
        current_package = dashboard_page.widget_text(self.package_summary_label)
        current_launch = dashboard_page.widget_text(self.launch_summary_label)
        changed = (
            current_release_title != release_title
            or current_release != release_text
            or current_release_tooltip != release_tooltip
            or current_package != package_text
            or current_launch != launch_text
        )
        self._stop_status_process()
        self.release_title_label.setText(release_title)
        self.device_release_label.setText(release_text)
        self.device_release_label.setToolTip(release_tooltip)
        self.package_summary_label.setText(package_text)
        self.launch_summary_label.setText(launch_text)
        self._set_package_rows([])
        self._set_launch_rows([])
        if self.page_active:
            dashboard_page.QTimer.singleShot(150, self.refresh_status)
        return changed

    def refresh_status(self) -> bool:
        if not self.page_active:
            return False
        if self.status_slot.is_running():
            return False
        profile = self.device_bar.current_profile()
        spec = _dashboard_page_module().device_status.probe_command(profile)
        process, request_id = self.status_slot.start_spec(spec)
        if process is None:
            return False
        process.readyReadStandardOutput.connect(lambda: self._read_status_output(process, request_id))
        process.finished.connect(lambda exit_code, _status: self._status_finished(process, request_id, exit_code))
        process.start()
        return True

    def _read_status_output(self, process: QProcess, request_id: int) -> bool:
        return self.status_slot.read_available_output(process, request_id)

    def _status_finished(self, process: QProcess, request_id: int, exit_code: int) -> bool:
        output = self.status_slot.finish(process, request_id)
        if output is None:
            return False
        dashboard_page = _dashboard_page_module()
        device_status = dashboard_page.device_status
        profile = self.device_bar.current_profile()
        output = strip_ansi(output)
        if exit_code == 0:
            status = device_status.parse_probe_output(output)
            package_items = device_status.core_package_items(status.packages, profile)
            found_count = sum(1 for _label, _name, version in package_items if version != "未发现")
            release = status.release_version or "未找到"
            release_title = self._release_title(profile)
            self.release_title_label.setText(release_title)
            self.device_release_label.setText(release)
            self.device_release_label.setToolTip(f"{release_title}: {release}\n主机名: {status.hostname or '-'}")
            self.package_summary_label.setText(f"已发现 {found_count}/{len(package_items)} 项")
            self.package_summary_label.setToolTip("")
            self.launch_summary_label.setText(device_status.launch_summary(status.launch_items, status.raw_launch))
            self.launch_summary_label.setToolTip("")
            self._set_package_rows(package_items)
            self._set_launch_rows(list(status.launch_items))
        else:
            self.device_release_label.setText("读取失败")
            self.device_release_label.setToolTip("")
            self.package_summary_label.setText("读取失败")
            self.launch_summary_label.setText("读取失败")
            self.package_summary_label.setToolTip("")
            self.launch_summary_label.setToolTip("")
            self._set_package_rows([])
            self._set_launch_rows([])
        return True

    def _stop_status_process(self) -> bool:
        running = self.status_slot.is_running()
        self.status_slot.stop()
        return running

    def run_launch_action(self, name: str, action: str) -> bool:
        dashboard_page = _dashboard_page_module()
        spec = dashboard_page.device_status.launch_action_command(self.device_bar.current_profile(), name, action)
        if not dashboard_page.confirm_command_spec(self, spec):
            return False
        display_command = f"执行服务操作：{action} {name}"
        task_id = self.runner.run(spec, display_command)
        if task_id is None:
            self.launch_summary_label.setText("任务未启动")
            self.launch_summary_label.setToolTip(task_not_started_text("服务操作"))
            return False
        return True

    def activate_page(self) -> bool:
        changed = not self.page_active
        if not changed:
            return False
        self.page_active = True
        _dashboard_page_module().QTimer.singleShot(150, self.refresh_status)
        return changed

    def deactivate_page(self) -> bool:
        return self._stop_status_polling()

    def shutdown_processes(self) -> bool:
        return self._stop_status_polling()

    def _stop_status_polling(self) -> bool:
        changed = self.page_active
        self.page_active = False
        stopped = self._stop_status_process()
        return changed or stopped
