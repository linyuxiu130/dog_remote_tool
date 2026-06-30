from __future__ import annotations

import time

from PyQt5.QtCore import QProcess, QSignalBlocker, QTimer, Qt, pyqtSignal
from PyQt5.QtGui import QPixmap
from PyQt5.QtWidgets import (
    QMessageBox,
)

from dog_remote_tool.core.runner import ProcessRunner
from dog_remote_tool.core.shell import CommandSpec
from dog_remote_tool.modules import mapping
from dog_remote_tool.ui.components import CommandPage, DeviceBar, confirm_command_spec
from dog_remote_tool.ui.image_preview import show_zoomable_pixmap
from dog_remote_tool.ui.map_helpers import (
    parse_history_map_disk_detail,
    parse_history_map_entries,
)
from dog_remote_tool.ui.process_utils import ProcessSlot
from dog_remote_tool.ui.pages.mapping.actions import MappingActionsMixin
from dog_remote_tool.ui.pages.mapping.layout import MappingLayoutMixin
from dog_remote_tool.ui.pages.mapping.lifecycle import MappingLifecycleMixin
from dog_remote_tool.ui.pages.mapping.map_history import MapHistoryCard, MappingMapHistoryMixin
from dog_remote_tool.ui.pages.mapping.preview import MappingPreviewMixin
from dog_remote_tool.ui.pages.mapping.status import MappingStatusMixin
from dog_remote_tool.ui.pages.mapping.transfer_actions import MappingTransferActionsMixin


_MAPPING_PAGE_MONKEYPATCH_EXPORTS = (
    time,
    QMessageBox,
    confirm_command_spec,
    show_zoomable_pixmap,
    MapHistoryCard,
)


class MappingPage(
    MappingLayoutMixin,
    MappingActionsMixin,
    MappingTransferActionsMixin,
    CommandPage,
    MappingStatusMixin,
    MappingMapHistoryMixin,
    MappingLifecycleMixin,
    MappingPreviewMixin,
):
    open_page_requested = pyqtSignal(str)

    def __init__(self, runner: ProcessRunner, device_bar: DeviceBar) -> None:
        super().__init__("建图", runner, device_bar)
        self.controls_panel.hide()
        self.map_fetch_slot = ProcessSlot(self, stop_timeout_ms=200, reserve_runner=False)
        self.map_thumbnail_slot = ProcessSlot(self, stop_timeout_ms=200, reserve_runner=False)
        self.map_list_slot = ProcessSlot(self, reserve_runner=False)
        self.status_slot = ProcessSlot(self, reserve_runner=False)
        self.preview_file = ""
        self.preview_pixmap: QPixmap | None = None
        self.preview_autoload_enabled = False
        self.map_entry_details: dict[str, str] = {}
        self.map_entries_signature: tuple[tuple[str, str, str], ...] = ()
        self.preview_remote_pgm = ""
        self.fetching_preview_remote_pgm = ""
        self.map_thumbnail_queue: list[str] = []
        self.force_latest_after_list = False
        self.force_preview_after_list = False
        self.last_mapping_status_state = "unknown"
        self.last_mapping_alg_status = ""
        self.last_mapping_status_at = 0.0
        self.mapping_operation_active = False
        self.mapping_operation_title = "空闲"
        self.mapping_runner_task_id = 0

        self.body.addWidget(self._build_config_box())
        action_box = self._build_action_box()
        self.update_mapping_action_buttons()
        self.body.addWidget(action_box)

        self.body.addWidget(self._build_preview_box())

        self.page_active = False
        self.runner.output.connect(self.capture_mapping_runner_output)
        self.runner.task_finished_detail.connect(self.handle_mapping_runner_finished)
        self.device_bar.profile_changed.connect(self.on_mapping_profile_changed)

    def on_mapping_profile_changed(self, profile) -> None:
        self._stop_refresh_processes(clear_maps=True)
        self.force_latest_after_list = False
        self.force_preview_after_list = False
        self.mapping_operation_active = False
        self.mapping_runner_task_id = 0
        self.set_mapping_operation("空闲", "idle")
        hide_next_steps = getattr(self, "hide_mapping_next_steps", None)
        if callable(hide_next_steps):
            hide_next_steps()
        self.sensor_type.setText(mapping.default_sensor_type(profile))
        self.save_map_path.setText(mapping.default_save_map_path(profile))
        self.calibration_file_path.setText(mapping.default_calibration_file_path(profile))
        self.arc_calibration_file_path.setText(mapping.default_arc_calibration_file_path(profile))
        self.last_mapping_status_state = "unknown"
        self.last_mapping_alg_status = ""
        self.last_mapping_status_at = 0.0
        self.preview_remote_pgm = ""
        if hasattr(self, "edit_map_pgm_button"):
            self.edit_map_pgm_button.setEnabled(False)
        self.preview_status.setText("已切换地图保存位置")

    def mapping_supported(self) -> bool:
        return "mapping" in self.profile().capabilities

    def refresh_map_list(self, silent: bool = False, force_preview: bool = False, force_latest: bool = False) -> bool:
        if not self.page_active:
            return False
        if force_preview:
            self.force_preview_after_list = True
        if force_latest:
            self.force_latest_after_list = True
        if not self.mapping_supported():
            self.preview_autoload_enabled = False
            self.map_selector.clear()
            self.map_entry_details = {}
            self.map_entries_signature = ()
            MappingPage.clear_map_cards(self)
            self.update_selected_map_detail()
            self.preview_status.setText("当前设备不支持地图读取")
            return False
        if self.map_list_slot.is_running():
            if not silent:
                self.preview_status.setText("历史列表正在刷新")
            return False
        _sensor_type, save_map_path, _calibration_file_path, _arc_calibration_file_path = self.mapping_values()
        profile = self.profile()
        command = mapping.list_map_pgm_command(profile, save_map_path)
        process, request_id = self.map_list_slot.start_spec(
            CommandSpec("读取历史地图", command, concurrency="parallel", locks=("mapping-history",))
        )
        if process is None:
            return False
        process.readyReadStandardOutput.connect(lambda: self.read_map_list_output(process, request_id))
        process.finished.connect(lambda exit_code, _status: self.map_list_finished(process, exit_code, request_id))
        process.start()
        return True

    def read_map_list_output(self, process: QProcess, request_id: int) -> bool:
        return self.map_list_slot.read_available_output(process, request_id)

    def map_list_finished(self, process: QProcess, exit_code: int, request_id: int) -> bool:
        output = self.map_list_slot.finish(process, request_id)
        if output is None:
            return False
        if exit_code != 0:
            self.force_latest_after_list = False
            self.force_preview_after_list = False
            self.preview_status.setText("历史列表读取失败")
            return True
        disk_detail = parse_history_map_disk_detail(output)
        entries = parse_history_map_entries(output)
        current = self.selected_remote_map_pgm()
        was_at_top = self.map_selector.currentIndex() <= 0
        force_latest = self.force_latest_after_list
        force_preview = self.force_preview_after_list
        self.force_latest_after_list = False
        self.force_preview_after_list = False
        previous_signature = self.map_entries_signature
        self.map_entries_signature = tuple(entries)
        self.map_entry_details = {remote_path: detail for _label, remote_path, detail in entries}
        signature_changed = self.map_entries_signature != previous_signature
        self.preview_autoload_enabled = False
        if entries and not signature_changed and not force_latest and not force_preview:
            self.preview_autoload_enabled = True
            self.update_selected_map_detail()
            return True
        with QSignalBlocker(self.map_selector):
            self.map_selector.clear()
            for label, remote_path, detail in entries:
                self.map_selector.addItem(label, remote_path)
                self.map_selector.setItemData(self.map_selector.count() - 1, detail, Qt.ToolTipRole)
            if current:
                index = self.map_selector.findData(current)
                if index >= 0:
                    self.map_selector.setCurrentIndex(index)
        self.update_selected_map_detail()
        if entries:
            if signature_changed:
                suffix = f"；{disk_detail}" if disk_detail else ""
                self.preview_status.setText(f"发现 {len(entries)} 张历史图{suffix}")
            self.preview_autoload_enabled = True
            latest_remote = entries[0][1]
            if force_latest or not current or self.map_selector.findData(current) < 0 or (was_at_top and latest_remote != current):
                with QSignalBlocker(self.map_selector):
                    self.map_selector.setCurrentIndex(0)
                self.update_selected_map_detail()
            MappingPage.update_map_cards(self, entries)
            selected = self.selected_remote_map_pgm()
            if selected and (force_preview or selected != self.preview_remote_pgm or not self.preview_pixmap):
                self.fetch_selected_map_preview(force=force_preview)
        else:
            self.preview_autoload_enabled = False
            self.preview_remote_pgm = ""
            self.preview_pixmap = None
            if hasattr(self, "edit_map_pgm_button"):
                self.edit_map_pgm_button.setEnabled(False)
            MappingPage.clear_map_cards(self)
            _sensor_type, save_map_path, _calibration_file_path, _arc_calibration_file_path = self.mapping_values()
            suffix = f"；{disk_detail}" if disk_detail else ""
            self.preview_status.setText(f"当前保存位置下没有找到历史图{suffix}")
        return True
