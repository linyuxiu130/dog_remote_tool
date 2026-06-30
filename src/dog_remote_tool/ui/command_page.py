from __future__ import annotations

from typing import TYPE_CHECKING

from PyQt5.QtCore import QTimer, Qt
from PyQt5.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QScrollArea, QSizePolicy, QVBoxLayout, QWidget

from dog_remote_tool.core.profiles import ProductProfile
from dog_remote_tool.core.runner import ProcessRunner
from dog_remote_tool.core.shell import CommandSpec
from dog_remote_tool.ui.command_confirm import command_display_command, confirm_command_spec
from dog_remote_tool.ui.widget_roles import set_widget_text_tooltip

if TYPE_CHECKING:
    from dog_remote_tool.ui.components import DeviceBar


class CommandPage(QWidget):
    def __init__(self, title: str, runner: ProcessRunner, device_bar: "DeviceBar") -> None:
        super().__init__()
        self.runner = runner
        self.device_bar = device_bar
        self.current_spec: CommandSpec | None = None
        self.autorun_enabled = False

        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(12)

        header = QFrame()
        header.setObjectName("PageHeader")
        self.page_header = header
        header_layout = QVBoxLayout(header)
        self.page_header_layout = header_layout
        header_layout.setContentsMargins(16, 10, 16, 10)
        label = QLabel(title)
        self.page_title_label = label
        label.setObjectName("AppTitle")
        header_layout.addWidget(label)
        root.addWidget(header)

        body_widget = QWidget()
        self.body_widget = body_widget
        body_widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.body = QVBoxLayout(body_widget)
        self.body.setContentsMargins(0, 0, 0, 0)
        self.body.setSpacing(12)
        self.body.setAlignment(Qt.AlignTop)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setWidget(body_widget)
        root.addWidget(scroll, 1)

        controls = QFrame()
        controls.setObjectName("Panel")
        self.controls_panel = controls
        controls_layout = QVBoxLayout(controls)
        controls_layout.setContentsMargins(10, 7, 10, 7)
        action_row = QHBoxLayout()
        self.stop_btn = QPushButton("停止任务")
        self.stop_btn.setObjectName("Danger")
        self.stop_btn.clicked.connect(self.runner.stop)
        action_row.addStretch(1)
        action_row.addWidget(self.stop_btn)
        controls_layout.addLayout(action_row)
        root.addWidget(controls)
        self.runner.state_changed.connect(lambda _running: self.refresh_stop_button())
        self.runner.task_status_changed.connect(self.refresh_stop_button)
        self.refresh_stop_button()
        QTimer.singleShot(0, self._enable_autorun)

    def profile(self) -> ProductProfile:
        return self.device_bar.current_profile()

    def set_command(self, spec: CommandSpec) -> bool | None:
        self.current_spec = spec
        if self.autorun_enabled:
            return self.run_current()
        return None

    def _enable_autorun(self) -> None:
        self.autorun_enabled = True

    def refresh_stop_button(self) -> None:
        running = self.runner.is_running()
        if self.runner.stop_locked:
            self.stop_btn.setEnabled(False)
            set_widget_text_tooltip(self.stop_btn, "刷机中，停止锁定", "OTA 已进入远端刷写阶段，本地停止按钮锁定。请等待远端升级完成。")
        elif running:
            self.stop_btn.setEnabled(True)
            set_widget_text_tooltip(self.stop_btn, "停止任务", "停止当前本地执行任务。正式刷机前可停止，进入刷机阶段后会自动锁定。")
        else:
            self.stop_btn.setEnabled(False)
            set_widget_text_tooltip(self.stop_btn, "无运行任务", "当前没有正在运行的任务。")

    def run_current(self) -> bool:
        if not self.current_spec:
            return False
        if not confirm_command_spec(self, self.current_spec):
            return False
        task_id = self.runner.run(self.current_spec, self.display_command_for_log())
        return task_id is not None

    def display_command_for_log(self) -> str:
        if not self.current_spec:
            return ""
        return command_display_command(self.current_spec)


def field_row(*widgets: QWidget) -> QWidget:
    box = QWidget()
    layout = QHBoxLayout(box)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(8)
    for widget in widgets:
        layout.addWidget(widget)
    return box
