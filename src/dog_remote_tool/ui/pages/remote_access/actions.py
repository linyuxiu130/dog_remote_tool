from __future__ import annotations

from dog_remote_tool.core.shell import CommandSpec
from dog_remote_tool.modules import remote_access
from dog_remote_tool.ui.label_status import set_label_text_style
from dog_remote_tool.ui.pages.remote_access.layout import STATUS_INFO, STATUS_PENDING
from dog_remote_tool.ui.status_text import task_not_started_text


class RemoteAccessActionsMixin:
    def run_remote_access_command(self, spec: CommandSpec) -> bool:
        started = self.set_command(spec)
        if started is False:
            set_label_text_style(self.remote_command_status, f"{spec.title}：{task_not_started_text()}", STATUS_PENDING)
        elif started is True:
            set_label_text_style(self.remote_command_status, f"{spec.title}：已启动", STATUS_INFO)
        return bool(started)

    def run_public_access_action(self) -> bool:
        action = "close" if self.public_state == "running" else "open"
        started = self.set_command(remote_access.public_access_action_command(self.profile(), self.public_ssid.text(), action))
        if started is False:
            set_label_text_style(self.public_status, "公网状态：任务未启动", STATUS_PENDING)
        return bool(started)
