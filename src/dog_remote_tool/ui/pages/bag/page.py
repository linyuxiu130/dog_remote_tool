from __future__ import annotations

import os
import subprocess
import threading
import time
from datetime import datetime

from PyQt5.QtCore import QSettings, QTimer, Qt, pyqtSignal
from PyQt5.QtGui import QColor
from PyQt5.QtWidgets import (
    QFileDialog,
    QMessageBox,
    QTableWidgetItem,
    QWidget,
)

from dog_remote_tool.core.profiles import ProductProfile
from dog_remote_tool.core.runner import ProcessRunner
from dog_remote_tool.modules import bag
from dog_remote_tool.ui.components import DeviceBar
from dog_remote_tool.ui.pages.bag.layout import BagLayoutMixin
from dog_remote_tool.ui.pages.bag.lifecycle import BagLifecycleMixin
from dog_remote_tool.ui.pages.bag.topic_config import BagTopicConfigMixin
from dog_remote_tool.ui.pages.bag.transfer_actions import BagTransferActionsMixin
from dog_remote_tool.ui.pages.bag.remote_topic_actions import BagRemoteTopicActionsMixin
from dog_remote_tool.ui.pages.bag.remote_topic_dialog import RemoteTopicDialog
from dog_remote_tool.ui.pages.bag.record_state import BagRecordStateMixin, QAbstractAnimation
from dog_remote_tool.ui.pages.bag.recording import BagRecordingMixin


_BAG_PAGE_MONKEYPATCH_EXPORTS = (
    QAbstractAnimation,
    QFileDialog,
    QMessageBox,
    QColor,
    QTableWidgetItem,
    Qt,
    os,
    subprocess,
    threading,
    time,
)


class BagPage(
    BagLayoutMixin,
    BagLifecycleMixin,
    QWidget,
    BagTopicConfigMixin,
    BagTransferActionsMixin,
    BagRemoteTopicActionsMixin,
    BagRecordStateMixin,
    BagRecordingMixin,
):
    AUTO_PULL_AFTER_RECORD_KEY = "bag/auto_pull_after_record"

    log_signal = pyqtSignal(str)
    topic_progress = pyqtSignal(int, int, str, int)
    topic_done = pyqtSignal(list, list, int)
    remote_topic_list_done = pyqtSignal(list, str, int, object)
    remote_topics_done = pyqtSignal(list, str, int)
    record_start_done = pyqtSignal(bool, str, int)
    record_done = pyqtSignal(bool, str, int)
    remote_bags_done = pyqtSignal(list, object, str, int)
    pull_progress = pyqtSignal(str, float, str, int)
    pull_done = pyqtSignal(dict, int)
    delete_done = pyqtSignal(list, list, int)
    bag_size_done = pyqtSignal(str, int)

    def __init__(self, runner: ProcessRunner, device_bar: DeviceBar) -> None:
        super().__init__()
        self.runner = runner
        self.device_bar = device_bar
        self.settings = QSettings()
        self.product = bag.profile_product_key(self.profile())
        self.record_topics: dict = {}
        self.custom_presets = bag.load_custom_presets()
        self.topic_overrides = bag.load_topic_overrides()
        self.remote_bag_items: list[dict] = []
        self.current_record_topics: list[str] = []
        self.current_bag_paths: list[str] = []
        self.current_record_profile: ProductProfile | None = None
        self.current_record_product = ""
        self.current_record_themes: list[str] = []
        self.current_record_started_at: datetime | None = None
        self.current_record_finished_at: datetime | None = None
        self.current_record_duration_seconds: int | None = None
        self.current_record_storage = ""
        self.current_record_cache_gb = 0
        self.recording_process: subprocess.Popen | None = None
        self.is_recording = False
        self.is_starting_recording = False
        self.stop_requested = False
        self.is_checking_topics = False
        self.is_scanning_remote_topics = False
        self.is_refreshing_remote = False
        self.is_pulling = False
        self.is_deleting = False
        self.is_reading_bag_size = False
        self.transfer_started_at = 0.0
        self.transfer_progress_label = ""
        self.start_time: float | None = None
        self.page_active = False
        self._updating_topic_table = False
        self.remote_topic_dialog: RemoteTopicDialog | None = None
        self.remote_topic_rows: list[dict] = []
        self.remote_topic_request_id = 0
        self.topic_check_request_id = 0
        self.remote_bags_request_id = 0
        self.bag_size_request_id = 0
        self.pull_request_id = 0
        self.delete_request_id = 0
        self.record_start_request_id = 0
        self.record_stop_request_id = 0

        self.log_signal.connect(lambda text: self.runner.output.emit(text))
        self.topic_progress.connect(self._topic_check_progress)
        self.topic_done.connect(self._topic_check_finished)
        self.remote_topic_list_done.connect(self._remote_topic_list_finished)
        self.remote_topics_done.connect(self._remote_topic_scan_finished)
        self.record_start_done.connect(self._record_start_finished)
        self.record_done.connect(self._recording_finished)
        self.remote_bags_done.connect(self._remote_bag_list_finished)
        self.pull_progress.connect(self._update_pull_progress)
        self.pull_done.connect(self._pull_finished)
        self.delete_done.connect(self._delete_finished)
        self.bag_size_done.connect(self._current_bag_size_finished)

        self.duration_timer = QTimer(self)
        self.duration_timer.setInterval(1000)
        self.duration_timer.timeout.connect(self._update_duration)
        self.bag_size_timer = QTimer(self)
        self.bag_size_timer.setInterval(15_000)
        self.bag_size_timer.timeout.connect(self.refresh_current_bag_size)

        self._build_ui()
        self.reload_topic_config()
        self.device_bar.profile_changed.connect(self._profile_changed)
