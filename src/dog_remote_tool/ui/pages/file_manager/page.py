from __future__ import annotations

from PyQt5.QtCore import QSettings, QSignalBlocker, QTimer
from PyQt5.QtWidgets import (
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QWidget,
)

from dog_remote_tool.core.runner import ProcessRunner
from dog_remote_tool.modules import file_manager
from dog_remote_tool.ui.components import DeviceBar
from dog_remote_tool.ui.pages.file_manager.actions import FileManagerActionsMixin
from dog_remote_tool.ui.pages.file_manager.browser import FileManagerBrowserMixin
from dog_remote_tool.ui.pages.file_manager.clipboard import FileManagerClipboardMixin
from dog_remote_tool.ui.pages.file_manager.dialogs import NameDialog, TextPreviewDialog, UploadDialog
from dog_remote_tool.ui.pages.file_manager.helpers import (
    breadcrumb_segments,
    is_under_home,
    items_signature,
)
from dog_remote_tool.ui.pages.file_manager.layout import FileManagerLayoutMixin
from dog_remote_tool.ui.pages.file_manager.operations import FileManagerOperationsMixin
from dog_remote_tool.ui.process_utils import ProcessSlot


_FILE_MANAGER_PAGE_MONKEYPATCH_EXPORTS = (
    QDialog,
    QFileDialog,
    QMessageBox,
    NameDialog,
    TextPreviewDialog,
    UploadDialog,
    QTimer,
)


def add_breadcrumb_separator(layout: QHBoxLayout) -> None:
    separator = QLabel("/")
    separator.setObjectName("PathCrumbMuted")
    layout.addWidget(separator)


class FileManagerPage(
    FileManagerLayoutMixin,
    FileManagerOperationsMixin,
    FileManagerBrowserMixin,
    FileManagerActionsMixin,
    FileManagerClipboardMixin,
    QWidget,
):
    MAX_RENDER_ITEMS = 1200

    def __init__(self, runner: ProcessRunner, device_bar: DeviceBar) -> None:
        super().__init__()
        self.runner = runner
        self.device_bar = device_bar
        self.current_path = self.profile().home
        self.last_successful_path = self.current_path
        self.current_items: list[file_manager.RemoteFileItem] = []
        self.current_signature = ""
        self.list_slot = ProcessSlot(self, reserve_runner=False)
        self.action_slot = ProcessSlot(self, stop_timeout_ms=500)
        self.action_callback = None
        self.preview_dialog: TextPreviewDialog | None = None
        self.preview_path = ""
        self.pending_total_size_paths: list[str] = []
        self.pending_select_names: set[str] = set()
        self.pending_refresh_after_task = False
        self.page_active = False
        self.last_error_message = ""
        self.auto_error_repeats = 0
        self.searching = False
        self.show_hidden = False
        self.settings = QSettings()
        self.current_view_mode = self.settings.value("file_manager/view_mode", "icon", type=str) or "icon"
        if self.current_view_mode not in {"icon", "tree"}:
            self.current_view_mode = "icon"
        self.transfer_active = False
        self.transfer_title = ""
        self.runner_task_title = ""
        self.runner_task_id = 0
        self.remote_clipboard_paths: list[str] = []
        self.remote_clipboard_mode = ""
        self.clear_remote_clipboard_on_success = False
        self._build_ui()
        self.device_bar.profile_changed.connect(self._profile_changed)
        self.runner.output.connect(self._watch_transfer_output)
        self.runner.task_finished_detail.connect(self._runner_finished)

    def profile(self):
        return self.device_bar.current_profile()

    def _signature(self, items: list[file_manager.RemoteFileItem]) -> str:
        return items_signature(items)

    def _set_path_edit(self, path: str) -> None:
        with QSignalBlocker(self.path_edit):
            self.path_edit.setText(path)
        if hasattr(self, "icon_view"):
            self.icon_view.set_current_path(path)
            self.table.set_current_path(path)
        self._render_breadcrumb(path)

    def _is_under_home(self, path: str) -> bool:
        return is_under_home(path, self.profile().home)

    def _update_profile_badge(self) -> None:
        profile = self.profile()
        self.target_label.setText(profile.label)
        self.target_label.setToolTip(f"{profile.label} / {profile.platform}")

    def _render_breadcrumb(self, path: str) -> None:
        if not hasattr(self, "breadcrumb_layout"):
            return
        while self.breadcrumb_layout.count():
            item = self.breadcrumb_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()
        root_btn = QPushButton("/")
        root_btn.setObjectName("PathCrumbButton")
        root_btn.setToolTip("/")
        root_btn.clicked.connect(lambda _checked=False: self.navigate_to("/"))
        self.breadcrumb_layout.addWidget(root_btn)
        truncated, shown = breadcrumb_segments(path, self.profile().home)
        if truncated:
            add_breadcrumb_separator(self.breadcrumb_layout)
            ellipsis = QLabel("...")
            ellipsis.setObjectName("PathCrumbMuted")
            self.breadcrumb_layout.addWidget(ellipsis)
        for part, target in shown:
            add_breadcrumb_separator(self.breadcrumb_layout)
            button = QPushButton(part)
            button.setObjectName("PathCrumbButton")
            button.setToolTip(target)
            button.clicked.connect(lambda _checked=False, p=target: self.navigate_to(p))
            self.breadcrumb_layout.addWidget(button)

    def shutdown_processes(self) -> None:
        self.page_active = False
        self._stop_page_processes(stop_action=True)

    def _stop_page_processes(self, *, stop_action: bool) -> None:
        self.list_slot.stop()
        if not stop_action:
            return
        self.action_callback = None
        self.cancel_action_btn.hide()
        self.action_slot.stop()
