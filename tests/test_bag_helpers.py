from datetime import datetime

from PyQt5.QtWidgets import QMessageBox

from dog_remote_tool.core.profiles import get_product
from dog_remote_tool.modules import bag
from dog_remote_tool.ui.pages.bag import page as bag_page
from dog_remote_tool.ui.pages.bag.page import BagPage
from dog_remote_tool.ui.pages.bag import layout as bag_layout
from dog_remote_tool.ui.pages.bag import layout_sections as bag_layout_sections
from dog_remote_tool.ui.pages.bag import lifecycle as bag_lifecycle
from dog_remote_tool.ui.pages.bag import remote_topic_actions as bag_remote_topic_actions
from dog_remote_tool.ui.pages.bag import topic_config as bag_topic_config
from dog_remote_tool.ui.pages.bag import topic_actions as bag_topic_actions
from dog_remote_tool.ui.pages.bag import topic_editor as bag_topic_editor
from dog_remote_tool.ui.pages.bag import transfer_actions as bag_transfer_actions
from dog_remote_tool.ui.pages.bag import transfer_delete as bag_transfer_delete
from dog_remote_tool.ui.pages.bag import transfer_pull as bag_transfer_pull
from dog_remote_tool.ui.pages.bag import record_state as bag_record_state
from dog_remote_tool.ui.pages.bag import recording as bag_recording
from dog_remote_tool.ui.pages.bag import recording_lifecycle as bag_recording_lifecycle
from dog_remote_tool.ui.pages.bag import recording_remote as bag_recording_remote
from dog_remote_tool.ui.pages.bag import recording_session as bag_recording_session
from dog_remote_tool.ui.pages.bag import recording_size as bag_recording_size
from dog_remote_tool.ui.pages.bag.transfer_actions import BagTransferActionsMixin
from dog_remote_tool.ui.pages.bag import helpers as bag_helpers
from dog_remote_tool.ui.pages.bag import record_metadata as bag_record_metadata
from dog_remote_tool.ui.pages.bag import topic_helpers as bag_topic_helpers


def test_bag_page_layout_sections_come_from_sections_mixin():
    assert BagPage._build_page_header is bag_layout_sections.BagLayoutSectionsMixin._build_page_header
    assert BagPage._build_record_status_box is bag_layout_sections.BagLayoutSectionsMixin._build_record_status_box
    assert BagPage._build_topic_panel is bag_layout_sections.BagLayoutSectionsMixin._build_topic_panel


def test_topic_editing_helpers_cover_display_and_normalization():
    record_topics = {
        "nav": {"name": "导航", "topics": ["/cmd_vel", "/odom"]},
        "custom_preset::巡检": {"topics": ["/scan"]},
    }
    config = {"topics": ["/cmd_vel", "/cmd_vel"], "zstd_topics": ["/odom", "/cmd_vel"]}

    assert bag_helpers.topic_display_name(record_topics, "nav") == "导航"
    assert bag_helpers.topic_display_name(record_topics, "custom_preset::巡检") == "巡检"
    assert "内部标识：nav" in bag_helpers.topic_tooltip(record_topics, "nav")
    assert "类型：自定义主题" in bag_helpers.topic_tooltip(record_topics, "custom_preset::巡检")
    assert bag_helpers.topic_name_exists(record_topics, "导航") is True
    assert bag_helpers.topic_name_exists(record_topics, "导航", "nav") is False
    assert bag_helpers.editable_topic_list(config) == ["/cmd_vel", "/odom"]
    assert bag_helpers.normalize_topic_values(["cmd_vel", "/cmd_vel", "", "#comment", "odom"]) == ["/cmd_vel", "/odom"]
    bag_helpers.set_config_topics(config, ["/scan"])
    assert config == {"topics": ["/scan"]}


def test_bag_display_and_remote_list_helpers_cover_main_ui_states():
    remote_items = [
        {"path": "/a", "active": 1, "size": 1024, "mtime": "09:30", "name": "a"},
        {"path": "/b", "active": 0, "size": 2048, "mtime": "09:31", "name": "b"},
        {"path": "/c", "active": "2", "size": 1536, "mtime": "09:32", "name": "c"},
        {"path": "", "active": 1, "size": 1, "mtime": "", "name": ""},
    ]

    assert bag_helpers.compact_middle("abcdefghijklmnopqrstuvwxyz0123456789", 20) == "abcdefgh...23456789"
    assert bag_helpers.default_remote_bag_path("nxl2", "/home/robot") == "/opt/data"
    assert bag_helpers.current_bag_label_state([]) == ("无", "", False)
    assert bag_helpers.current_bag_label_state(["/tmp/a", "/tmp/b", "/tmp/c"]) == ("3 个Bag: a, b...", "/tmp/a\n/tmp/b\n/tmp/c", True)
    assert bag_helpers.known_remote_bag_size_text(["/a", "/b"], remote_items) == "3.0 KB"
    assert bag_helpers.active_remote_bag_paths(remote_items) == ["/a", "/c"]
    assert bag_helpers.active_remote_bag_paths(remote_items, ["/c"]) == ["/c"]
    assert bag_helpers.started_at_from_remote_bag_paths(["/opt/data/rosbag2_l2_20260525_093001"]) == datetime(2026, 5, 25, 9, 30, 1)
    assert bag_helpers.started_at_from_remote_bag_paths(["/opt/data/bad", "/home/robot/air_20260525_093101"]) == datetime(2026, 5, 25, 9, 31, 1)
    assert bag_helpers.started_at_from_remote_bag_paths(["/opt/data/bad"]) is None
    assert bag_helpers.remote_scan_dirs("/home/robot/", "/home/robot", "/tmp/zsibot") == ["/home/robot", "/tmp/zsibot"]
    assert bag_helpers.remote_disk_text({"available": 1024, "total": 2048}) == "可用空间: 1.0 KB / 2.0 KB"
    assert bag_helpers.remote_bag_status_text(remote_items) == "4 个Bag，3 个录制中"
    assert bag_helpers.remote_bag_table_row(remote_items[0]) == (True, ["录制中", "09:30", "1.0 KB", "a", "/a"], "/a")


def test_pull_progress_and_message_helpers_cover_transfer_ui():
    result = {
        "target_dir": "/data/L2_20260525_093001",
        "summary_file": "/data/L2_20260525_093001/record_summary.md",
        "bag_success": True,
        "log_success": False,
        "calibration_success": True,
        "validation": {"summary": "正常", "details": ["bag 完整"]},
        "deleted": ["/remote/a"],
        "delete_failed": ["/remote/b"],
    }

    assert bag_helpers.format_transfer_eta(3661) == "1:01:01"
    assert bag_helpers.pull_local_base(True, "") == bag.DEFAULT_LOCAL_BAG_DIR
    assert bag_helpers.pull_local_base(False, "/tmp/bags") == bag.DEFAULT_LOCAL_LOG_DIR
    assert bag_helpers.pull_confirm_detail(True, ["/a", "/b"]) == "/a\n/b"
    assert bag_helpers.pull_progress_value(101) == 100
    assert bag_helpers.should_reset_transfer_timer("A", 5, "A", 9) is True
    assert bag_helpers.pull_progress_texts("正在拉取Bag包 1/2", 25, "1.0 MB/s", 3.0) == (
        "拉取Bag 1/2",
        "25%",
        "速度 1.0 MB/s",
        "预计 00:09",
    )
    assert "标定文件: 成功" in bag_helpers.pull_result_log_lines(result, "nxl2")
    result["calibration_attempted"] = True
    assert "标定文件: 成功" in bag_helpers.pull_result_log_lines(result, "zgnx")
    assert bag_helpers.pull_finished_message(result).endswith("录制结果检查: 正常")


def test_delete_message_helpers_cover_safe_and_failed_paths():
    profile = get_product("xg2_s100")

    assert bag_helpers.unsafe_remote_bag_paths(["/opt/data/l2_20260525_093001", "/home/robot/not_a_bag"], profile) == ["/home/robot/not_a_bag"]
    assert bag_helpers.delete_confirm_message(["/a", "/b"]) == "此操作不可恢复。\n\n/a\n/b"
    assert bag_helpers.delete_finished_message(["/a"], []) == (False, "已删除远端Bag目录 1 个")
    assert bag_helpers.delete_finished_message(["/a"], ["/b"]) == (True, "已删除 1 个，失败 1 个。\n\n/b")


class _FakeButton:
    def __init__(self):
        self.enabled = False

    def setEnabled(self, enabled):
        self.enabled = enabled

    def isEnabled(self):
        return self.enabled


class _FakeCheckBox:
    def __init__(self, checked=False):
        self.checked = checked

    def isChecked(self):
        return self.checked


class _FakeText:
    def __init__(self, text=""):
        self._text = text
        self.texts = []
        self.cleared = False
        self.enabled = True
        self.tooltip = ""

    def text(self):
        return self._text

    def setText(self, text):
        self.texts.append(text)
        self._text = text

    def setEnabled(self, enabled):
        self.enabled = enabled

    def isEnabled(self):
        return self.enabled

    def setToolTip(self, tooltip):
        self.tooltip = tooltip

    def toolTip(self):
        return self.tooltip

    def clear(self):
        self.cleared = True
        self._text = ""


class _FakeTableIndex:
    def __init__(self, row):
        self._row = row

    def row(self):
        return self._row


class _FakeTableSelection:
    def __init__(self, table):
        self.table = table

    def selectedRows(self):
        return [_FakeTableIndex(row) for row in self.table.selected_rows]


class _FakeTableItem:
    def __init__(self, text):
        self._text = text

    def text(self):
        return self._text


class _FakeTopicTable:
    def __init__(self, topics=None, selected_rows=None):
        self.topics = list(topics or [])
        self.selected_rows = list(selected_rows or [])
        self.removed_rows = []
        self.enabled = True

    def rowCount(self):
        return len(self.topics)

    def item(self, row, _column):
        if 0 <= row < len(self.topics):
            return _FakeTableItem(self.topics[row])
        return None

    def selectionModel(self):
        return _FakeTableSelection(self)

    def removeRow(self, row):
        self.removed_rows.append(row)
        if 0 <= row < len(self.topics):
            self.topics.pop(row)

    def setRowCount(self, count):
        if count == 0:
            self.topics = []
        else:
            self.topics = self.topics[:count] + [""] * max(0, count - len(self.topics))

    def insertRow(self, row):
        self.topics.insert(row, "")

    def setItem(self, row, _column, item):
        while len(self.topics) <= row:
            self.topics.append("")
        self.topics[row] = item.text()

    def setEnabled(self, enabled):
        self.enabled = enabled

    def isEnabled(self):
        return self.enabled


class _FakeCombo:
    def __init__(self, value="mcap"):
        self.value = value

    def currentText(self):
        return self.value

    def setCurrentText(self, value):
        self.value = value


class _FakeSpin:
    def __init__(self, value=4):
        self._value = value

    def value(self):
        return self._value


class _FakeBackend:
    def __init__(self):
        self.profile = get_product("xg2_s100")


class _FakeProfile:
    home = "/home/robot"


class _FakeReloadTopicConfigPage:
    def __init__(self):
        self.profile_value = _FakeProfile()
        self.product = "old"
        self.topic_overrides = {}
        self.custom_presets = {}
        self.record_topics = {"old": {"topics": ["/old"]}}
        self.remote_path = _FakeText("/old")
        self.storage_combo = _FakeCombo("sqlite3")
        self.refreshed = []
        self.selection_updates = 0

    def profile(self):
        return self.profile_value

    def _refresh_topic_list(self, keep=None):
        self.refreshed.append(keep)

    def _topic_selection_changed(self):
        self.selection_updates += 1


class _FakeThread:
    started: list[tuple] = []

    def __init__(self, target=None, args=(), daemon=None):
        self.target = target
        self.args = args
        self.daemon = daemon
        _FakeThread.started.append((target, args, daemon))

    def start(self):
        pass


class _FakeTransferPage(BagTransferActionsMixin):
    def __init__(self):
        self.pull_request_id = 2
        self.delete_request_id = 4
        self.is_pulling = True
        self.is_deleting = True
        self.delete_selected_btn = _FakeButton()
        self.progress_visible_calls = []
        self.refresh_calls = 0

    def _set_pull_progress_visible(self, visible):
        self.progress_visible_calls.append(visible)

    def refresh_remote_bags(self, auto=False):
        self.refresh_calls += 1


class _FakeTransferStartPage(BagTransferActionsMixin):
    def __init__(self, tmp_path):
        self.product = "nxl2"
        self.is_recording = False
        self.is_starting_recording = False
        self.stop_requested = False
        self.start_time = None
        self.is_pulling = False
        self.is_deleting = False
        self.pull_request_id = 2
        self.delete_request_id = 4
        self.local_dir = _FakeText(str(tmp_path))
        self.current_bag_paths = ["/opt/data/l2_20260525_093001"]
        self.remote_bag_items = [{"path": "/opt/data/l2_20260525_093001", "active": 0, "size": 2048}]
        self.current_record_topics = ["/cmd_vel"]
        self.current_bag_size_label = _FakeText()
        self.transfer_percent_label = _FakeText()
        self.transfer_speed_label = _FakeText()
        self.transfer_eta_label = _FakeText()
        self.record_status_label = _FakeText()
        self.start_btn = _FakeButton()
        self.resume_btn = _FakeButton()
        self.stop_btn = _FakeButton()
        self.duration_timer = _FakeRecordTimer()
        self.bag_size_timer = _FakeRecordTimer()
        self.delete_selected_btn = _FakeButton()
        self.storage_combo = _FakeCombo()
        self.cache_spin = _FakeSpin()
        self.progress_visible_calls = []
        self.progress_values = []
        self.current_paths_calls = []
        self.applied_contexts = []
        self.selected_paths = ["/opt/data/l2_20260525_093001"]
        self.backend_instance = _FakeBackend()
        self.duration_updates = 0
        self.refresh_calls = []
        self.logs = []

    def profile(self):
        return self.backend_instance.profile

    def backend(self):
        return self.backend_instance

    def current_record_backend(self):
        return self.backend_instance

    def selected_remote_paths(self):
        return self.selected_paths[:]

    def _pull_worker(self, *args):
        pass

    def _delete_worker(self, *args):
        pass

    def _current_record_info(self):
        return {"dataset_name": "fake"}

    def _set_record_detail_visible(self, visible):
        self.record_detail_visible = visible

    def _set_pull_progress_value(self, value, animated=True):
        self.progress_values.append((value, animated))

    def _set_pull_progress_visible(self, visible):
        self.progress_visible_calls.append(visible)

    def refresh_current_bag_size(self, force=False):
        self.refreshed_size = force

    def _update_duration(self):
        self.duration_updates += 1

    def _log(self, message):
        self.logs.append(message)

    def _apply_record_context(self, context):
        self.applied_contexts.append(context)

    def _set_current_bag_paths(self, paths):
        self.current_paths_calls.append(paths)
        self.current_bag_paths = paths[:]

    def refresh_remote_bags(self, auto=False):
        self.refresh_calls.append(auto)


class _FakeRemoteTopicDialog:
    def __init__(self):
        self.busy = None
        self.status = ""
        self.cleared = False
        self.shown = 0
        self.raised = 0
        self.activated = 0
        self.populated = []
        self.theme_refreshes = []

    def set_busy(self, busy):
        self.busy = busy

    def set_status(self, status):
        self.status = status

    def clear_rows(self):
        self.cleared = True

    def show(self):
        self.shown += 1

    def raise_(self):
        self.raised += 1

    def activateWindow(self):
        self.activated += 1

    def populate_rows(self, rows, record_topics, display_name, selected_keys):
        self.populated.append((rows, record_topics, display_name, selected_keys))

    def refresh_theme_combo(self, record_topics, display_name):
        self.theme_refreshes.append((record_topics, display_name))


class _FakeDialogSignal:
    def __init__(self):
        self.connected = []

    def connect(self, callback):
        self.connected.append(callback)


class _FakeLogSignal:
    def __init__(self):
        self.messages = []

    def emit(self, message):
        self.messages.append(message)


class _FakeBuildRemoteTopicDialog(_FakeRemoteTopicDialog):
    def __init__(self, profile, parent, refresh_callback, view_changed_callback):
        super().__init__()
        self.profile = profile
        self.parent = parent
        self.refresh_callback = refresh_callback
        self.view_changed_callback = view_changed_callback
        self.finished = _FakeDialogSignal()


class _FakeRemoteBagTable:
    def __init__(self):
        self.updates_enabled = []
        self.row_counts = []
        self.items = {}

    def setUpdatesEnabled(self, enabled):
        self.updates_enabled.append(enabled)

    def setRowCount(self, count):
        self.row_counts.append(count)
        self.items = {key: value for key, value in self.items.items() if key[0] < count}

    def setItem(self, row, column, item):
        self.items[(row, column)] = item


class _FakeTopicPlan:
    def __init__(self, topics):
        self.all_topics = topics


class _FakeBagAsyncPage:
    def __init__(self, tmp_path):
        self.page_active = True
        self.is_recording = True
        self.current_bag_paths = ["/opt/data/l2_20260525_093001"]
        self.current_bag_size_label = _FakeText("--")
        self.is_reading_bag_size = False
        self.bag_size_request_id = 2
        self.is_scanning_remote_topics = False
        self.remote_topic_btn = _FakeButton()
        self.remote_topic_dialog = None
        self.remote_topic_rows = [{"name": "/cmd_vel"}]
        self.remote_topic_request_id = 4
        self.is_checking_topics = False
        self.topic_check_request_id = 6
        self.pull_request_id = 10
        self.delete_request_id = 12
        self.topic_check_btn = _FakeButton()
        self.topic_check_label = _FakeText()
        self.is_refreshing_remote = False
        self.is_pulling = False
        self.remote_bags_request_id = 8
        self.remote_status_label = _FakeText()
        self.remote_space_label = _FakeText()
        self.remote_table = _FakeRemoteBagTable()
        self.remote_path = _FakeText("/opt/data")
        self.logs = []
        self.topic_selection_updates = 0
        self.resume_updates = 0
        self.reload_calls = 0
        self.refresh_calls = []
        self.record_topics = {"nav": {"topics": ["/cmd_vel"]}}
        self.backend_instance = _FakeBackend()
        self.tmp_path = tmp_path

    def profile(self):
        return self.backend_instance.profile

    def backend(self):
        return self.backend_instance

    def current_record_backend(self):
        return self.backend_instance

    def default_remote_bag_path(self):
        return "/opt/data"

    def topic_plan(self):
        return _FakeTopicPlan(["/cmd_vel"])

    def _topic_display_name(self, key):
        return {"nav": "导航"}.get(key, key)

    def _set_label_status(self, label, state):
        label.status = state

    def reload_topic_config(self):
        self.reload_calls += 1

    def _log(self, message):
        self.logs.append(message)

    def _current_bag_size_worker(self, *args):
        pass

    def _remote_topic_list_worker(self, *args):
        pass

    def _remote_topic_scan_worker(self, *args):
        pass

    def _topic_check_worker(self, *args):
        pass

    def _remote_bags_worker(self, *args):
        pass

    def _build_remote_topic_dialog(self):
        self.remote_topic_dialog = _FakeRemoteTopicDialog()

    def _populate_remote_topic_table(self, rows):
        if self.remote_topic_dialog is not None:
            self.remote_topic_dialog.populate_rows(rows, {}, lambda key: key, set())

    def _topic_selection_changed(self):
        self.topic_selection_updates += 1

    def _update_resume_button(self):
        self.resume_updates += 1

    def _refresh_remote_topic_theme_combo(self):
        return BagPage._refresh_remote_topic_theme_combo(self)

    def refresh_remote_bags(self, auto=False):
        self.refresh_calls.append(auto)
        return True

    def _start_remote_topic_scan(self):
        return BagPage._start_remote_topic_scan(self)


def test_transfer_page_ignores_stale_pull_and_delete_callbacks():
    page = _FakeTransferPage()

    assert page._update_pull_progress("旧任务", 50, "1 MB/s", request_id=1) is False
    assert page._pull_finished({"bag_success": True, "log_success": True}, request_id=1) is False
    assert page._delete_finished(["/tmp/old"], [], request_id=3) is False

    assert page.is_pulling is True
    assert page.is_deleting is True
    assert page.delete_selected_btn.enabled is False
    assert page.progress_visible_calls == []
    assert page.refresh_calls == 0


def test_bag_readonly_background_entries_return_start_result(monkeypatch, tmp_path):
    _FakeThread.started = []
    monkeypatch.setattr(bag_page.threading, "Thread", _FakeThread)
    warning_calls = []
    monkeypatch.setattr(QMessageBox, "warning", lambda *args, **kwargs: warning_calls.append(args))
    info_calls = []
    monkeypatch.setattr(QMessageBox, "information", lambda *args, **kwargs: info_calls.append(args))
    page = _FakeBagAsyncPage(tmp_path)

    assert BagPage.refresh_current_bag_size(page) is True
    assert page.is_reading_bag_size is True
    assert page.bag_size_request_id == 3
    assert _FakeThread.started[-1][1][2] == 3

    inactive = _FakeBagAsyncPage(tmp_path)
    inactive.page_active = False
    assert BagPage.refresh_current_bag_size(inactive) is False

    size_done = _FakeBagAsyncPage(tmp_path)
    size_done.is_reading_bag_size = True
    assert BagPage._current_bag_size_finished(size_done, "9.5 MB", request_id=1) is False
    assert size_done.is_reading_bag_size is True
    assert size_done.current_bag_size_label.text() == "--"
    assert BagPage._current_bag_size_finished(size_done, "9.5 MB", request_id=2) is True
    assert size_done.is_reading_bag_size is False
    assert size_done.current_bag_size_label.text() == "9.5 MB"

    size_done_empty = _FakeBagAsyncPage(tmp_path)
    size_done_empty.current_bag_paths = []
    size_done_empty.is_reading_bag_size = True
    assert BagPage._current_bag_size_finished(size_done_empty, "9.5 MB", request_id=2) is True
    assert size_done_empty.is_reading_bag_size is False
    assert size_done_empty.current_bag_size_label.text() == "--"

    profile_changed = _FakeBagAsyncPage(tmp_path)
    profile_changed.remote_topic_dialog = _FakeRemoteTopicDialog()
    profile_changed.remote_topic_btn.setEnabled(False)
    profile_changed.is_checking_topics = True
    profile_changed.is_scanning_remote_topics = True
    profile_changed.is_refreshing_remote = True
    profile_changed.is_reading_bag_size = True

    assert BagPage._profile_changed(profile_changed, None) is True
    assert profile_changed.remote_topic_request_id == 5
    assert profile_changed.topic_check_request_id == 7
    assert profile_changed.remote_bags_request_id == 9
    assert profile_changed.bag_size_request_id == 3
    assert profile_changed.pull_request_id == 11
    assert profile_changed.delete_request_id == 13
    assert profile_changed.is_checking_topics is False
    assert profile_changed.is_scanning_remote_topics is False
    assert profile_changed.is_refreshing_remote is False
    assert profile_changed.is_reading_bag_size is False
    assert profile_changed.reload_calls == 1
    assert profile_changed.remote_topic_rows == []
    assert profile_changed.remote_topic_dialog.busy is False
    assert profile_changed.remote_topic_dialog.cleared is True
    assert profile_changed.remote_topic_dialog.status == "设备已切换，请刷新"
    assert profile_changed.remote_topic_dialog.theme_refreshes
    assert profile_changed.remote_topic_btn.enabled is True
    assert profile_changed.topic_check_label.text() == "设备已切换"
    assert profile_changed.topic_check_label.status == "warn"
    assert profile_changed.refresh_calls == [True]

    scanning = _FakeBagAsyncPage(tmp_path)
    scanning.remote_topic_dialog = _FakeRemoteTopicDialog()
    assert BagPage._start_remote_topic_scan(scanning) is True
    assert scanning.is_scanning_remote_topics is True
    assert scanning.remote_topic_btn.enabled is False
    assert scanning.remote_topic_dialog.busy is True
    assert scanning.remote_topic_dialog.cleared is True
    assert scanning.remote_topic_request_id == 5
    assert _FakeThread.started[-1][1][1] == 5

    scanning_busy = _FakeBagAsyncPage(tmp_path)
    scanning_busy.is_scanning_remote_topics = True
    assert BagPage._start_remote_topic_scan(scanning_busy) is False

    topic_list = _FakeBagAsyncPage(tmp_path)
    topic_list.remote_topic_dialog = _FakeRemoteTopicDialog()
    assert BagPage._remote_topic_list_finished(topic_list, [], "", request_id=3, backend=topic_list.backend_instance) is False
    assert topic_list.remote_topic_rows == [{"name": "/cmd_vel"}]
    assert BagPage._remote_topic_list_finished(topic_list, [{"name": "/scan"}], "", request_id=4, backend=topic_list.backend_instance) is True
    assert topic_list.remote_topic_rows == [{"name": "/scan"}]
    assert topic_list.remote_topic_dialog.status == "已列出 1 个，正在采样 Hz..."
    assert _FakeThread.started[-1][1] == (topic_list.backend_instance, 4)

    topic_list_failed = _FakeBagAsyncPage(tmp_path)
    topic_list_failed.remote_topic_dialog = _FakeRemoteTopicDialog()
    topic_list_failed.is_scanning_remote_topics = True
    assert BagPage._remote_topic_list_finished(topic_list_failed, [], "ssh failed", request_id=4, backend=topic_list_failed.backend_instance) is True
    assert topic_list_failed.is_scanning_remote_topics is False
    assert topic_list_failed.remote_topic_btn.enabled is True
    assert topic_list_failed.remote_topic_dialog.busy is False
    assert topic_list_failed.remote_topic_dialog.status == "读取失败"
    assert warning_calls

    topic_scan = _FakeBagAsyncPage(tmp_path)
    topic_scan.remote_topic_dialog = _FakeRemoteTopicDialog()
    topic_scan.is_scanning_remote_topics = True
    assert BagPage._remote_topic_scan_finished(topic_scan, [], "", request_id=3) is False
    assert topic_scan.is_scanning_remote_topics is True
    assert BagPage._remote_topic_scan_finished(topic_scan, [{"name": "/scan", "hz": 10.0}], "", request_id=4) is True
    assert topic_scan.is_scanning_remote_topics is False
    assert topic_scan.remote_topic_btn.enabled is True
    assert topic_scan.remote_topic_dialog.busy is False
    assert topic_scan.remote_topic_rows == [{"name": "/scan", "hz": 10.0}]
    assert topic_scan.remote_topic_dialog.populated

    checking = _FakeBagAsyncPage(tmp_path)
    assert BagPage.check_selected_topics(checking) is True
    assert checking.is_checking_topics is True
    assert checking.topic_check_btn.enabled is False
    assert checking.topic_check_label.text() == "检查中..."
    assert checking.topic_check_label.status == "warn"
    assert checking.topic_check_request_id == 7
    assert _FakeThread.started[-1][1][2] == 7

    assert BagPage._topic_check_progress(checking, 1, 2, "/cmd_vel", request_id=6) is False
    assert checking.topic_check_label.text() == "检查中..."
    assert BagPage._topic_check_progress(checking, 1, 2, "/cmd_vel", request_id=7) is True
    assert checking.topic_check_label.text() == "检查中 1/2 /cmd_vel"
    assert BagPage._topic_check_finished(checking, ["/cmd_vel"], [], request_id=6) is False
    assert checking.is_checking_topics is True
    assert BagPage._topic_check_finished(checking, ["/cmd_vel"], [], request_id=7) is True
    assert checking.is_checking_topics is False
    assert checking.topic_selection_updates == 1
    assert checking.topic_check_label.text() == "正常 1 个"
    assert checking.topic_check_label.status == "ok"
    assert info_calls

    no_topics = _FakeBagAsyncPage(tmp_path)
    no_topics.topic_plan = lambda: _FakeTopicPlan([])
    assert BagPage.check_selected_topics(no_topics) is False

    remote = _FakeBagAsyncPage(tmp_path)
    assert BagPage.refresh_remote_bags(remote, auto=False) is True
    assert remote.is_refreshing_remote is True
    assert remote.remote_bags_request_id == 9
    assert remote.remote_status_label.text() == "刷新中..."
    assert remote.remote_space_label.text() == "可用空间: 查询中..."
    assert _FakeThread.started[-1][1][2] == 9

    remote_stale = _FakeBagAsyncPage(tmp_path)
    remote_stale.is_refreshing_remote = True
    assert BagPage._remote_bag_list_finished(remote_stale, [], None, "", request_id=7) is False
    assert remote_stale.is_refreshing_remote is True
    assert remote_stale.remote_table.updates_enabled == []

    remote_failed = _FakeBagAsyncPage(tmp_path)
    remote_failed.is_refreshing_remote = True
    assert BagPage._remote_bag_list_finished(remote_failed, [], None, "ssh failed while scanning", request_id=8) is True
    assert remote_failed.is_refreshing_remote is False
    assert remote_failed.remote_bag_items == []
    assert remote_failed.remote_status_label.text() == "刷新失败: ssh failed while scanning"
    assert remote_failed.remote_status_label.toolTip() == "ssh failed while scanning"
    assert remote_failed.remote_space_label.text() == "可用空间: 查询失败"
    assert remote_failed.remote_table.row_counts == [0]
    assert remote_failed.remote_table.updates_enabled == [False, True]
    assert remote_failed.resume_updates == 1

    remote_done = _FakeBagAsyncPage(tmp_path)
    remote_done.is_refreshing_remote = True
    items = [{"path": "/opt/data/rosbag2_l2_20260527_120000", "active": 1, "size": 2048, "mtime": "12:00", "name": "bag"}]
    disk = {"available": 1024, "total": 4096}
    assert BagPage._remote_bag_list_finished(remote_done, items, disk, "", request_id=8) is True
    assert remote_done.is_refreshing_remote is False
    assert remote_done.remote_bag_items == items
    assert remote_done.remote_status_label.text() == "1 个Bag，1 个录制中"
    assert remote_done.remote_status_label.toolTip() == ""
    assert remote_done.remote_space_label.text() == "可用空间: 1.0 KB / 4.0 KB"
    assert remote_done.remote_table.row_counts == [0, 1]
    assert remote_done.remote_table.items[(0, 4)].text() == "/opt/data/rosbag2_l2_20260527_120000"
    assert remote_done.remote_table.updates_enabled == [False, True]
    assert remote_done.resume_updates == 1

    auto_inactive = _FakeBagAsyncPage(tmp_path)
    auto_inactive.page_active = False
    assert BagPage.refresh_remote_bags(auto_inactive, auto=True) is False


def test_bag_show_remote_topic_dialog_returns_display_result(monkeypatch, tmp_path):
    _FakeThread.started = []
    monkeypatch.setattr(bag_page.threading, "Thread", _FakeThread)
    failed = _FakeBagAsyncPage(tmp_path)
    failed._build_remote_topic_dialog = lambda: None

    assert BagPage.show_remote_topic_dialog(failed) is False
    assert failed.remote_topic_dialog is None

    cached = _FakeBagAsyncPage(tmp_path)

    assert BagPage.show_remote_topic_dialog(cached) is True
    assert cached.remote_topic_dialog.shown == 1
    assert cached.remote_topic_dialog.raised == 1
    assert cached.remote_topic_dialog.activated == 1
    assert cached.remote_topic_dialog.populated
    assert cached.is_scanning_remote_topics is False

    scanning = _FakeBagAsyncPage(tmp_path)
    scanning.remote_topic_rows = []

    assert BagPage.show_remote_topic_dialog(scanning) is True
    assert scanning.is_scanning_remote_topics is True
    assert scanning.remote_topic_btn.enabled is False
    assert scanning.remote_topic_dialog.busy is True
    assert scanning.remote_topic_dialog.status == "读取列表..."
    assert _FakeThread.started[-1][1][1] == scanning.remote_topic_request_id


def test_bag_pull_actions_return_start_result(monkeypatch, tmp_path):
    _FakeThread.started = []
    monkeypatch.setattr(bag_transfer_actions.threading, "Thread", _FakeThread)
    monkeypatch.setattr(QMessageBox, "information", lambda *args, **kwargs: None)
    monkeypatch.setattr(QMessageBox, "question", lambda *args, **kwargs: QMessageBox.Yes)

    busy = _FakeTransferStartPage(tmp_path)
    busy.is_pulling = True

    assert BagTransferActionsMixin._start_pull(busy, ["/opt/data/l2_20260525_093001"], True, True, False) is False
    assert _FakeThread.started == []

    cancelled = _FakeTransferStartPage(tmp_path)
    monkeypatch.setattr(QMessageBox, "question", lambda *args, **kwargs: QMessageBox.Cancel)

    assert BagTransferActionsMixin._start_pull(cancelled, ["/opt/data/l2_20260525_093001"], True, True, False) is False
    assert _FakeThread.started == []

    page = _FakeTransferStartPage(tmp_path)
    monkeypatch.setattr(QMessageBox, "question", lambda *args, **kwargs: QMessageBox.Yes)

    assert BagTransferActionsMixin.pull_current_recording(page, delete_remote_on_success=True) is True
    assert page.is_pulling is True
    assert page.pull_request_id == 3
    assert page.record_status_label.text() == "正在回传"
    assert page.progress_visible_calls == [True]
    assert _FakeThread.started
    assert _FakeThread.started[-1][1][3] is True
    assert _FakeThread.started[-1][1][4] is False
    assert _FakeThread.started[-1][1][5] is True

    empty = _FakeTransferStartPage(tmp_path)
    empty.current_bag_paths = []

    assert BagTransferActionsMixin.pull_current_recording(empty) is False

    selected = _FakeTransferStartPage(tmp_path)

    assert BagTransferActionsMixin.pull_selected_remote_bags(selected) is True
    assert selected.applied_contexts
    assert selected.current_paths_calls == [["/opt/data/l2_20260525_093001"]]
    assert _FakeThread.started[-1][1][3] is True
    assert _FakeThread.started[-1][1][4] is False

    runtime_log = _FakeTransferStartPage(tmp_path)

    assert BagTransferActionsMixin.pull_runtime_log_only(runtime_log) is True
    assert _FakeThread.started[-1][1][3] is False
    assert _FakeThread.started[-1][1][4] is True
    assert _FakeThread.started[-1][1][8] == "runtime"

    ros_log = _FakeTransferStartPage(tmp_path)

    assert BagTransferActionsMixin.pull_ros_log_only(ros_log) is True
    assert _FakeThread.started[-1][1][3] is False
    assert _FakeThread.started[-1][1][4] is True
    assert _FakeThread.started[-1][1][8] == "ros"


def test_bag_pull_finished_returns_accept_result(monkeypatch, tmp_path):
    critical_calls = []
    info_calls = []
    monkeypatch.setattr(QMessageBox, "critical", lambda *args, **kwargs: critical_calls.append(args))
    monkeypatch.setattr(QMessageBox, "information", lambda *args, **kwargs: info_calls.append(args))

    failed = _FakeTransferStartPage(tmp_path)
    failed.is_pulling = True

    assert BagTransferActionsMixin._pull_finished(failed, {"error": "network down"}, request_id=2) is True
    assert failed.is_pulling is False
    assert failed.record_status_label.text() == "拉取失败"
    assert failed.progress_values == [(0, False)]
    assert failed.progress_visible_calls == [False]
    assert "✗ 拉取异常: network down" in failed.logs
    assert critical_calls

    finished = _FakeTransferStartPage(tmp_path)
    finished.is_pulling = True
    result = {
        "target_dir": str(tmp_path / "bags"),
        "summary_file": "",
        "bag_success": True,
        "log_success": True,
        "calibration_success": False,
        "validation": {"summary": "正常", "details": []},
    }

    assert BagTransferActionsMixin._pull_finished(finished, result, request_id=2) is True
    assert finished.is_pulling is False
    assert finished.record_status_label.text() == "拉取完成"
    assert finished.progress_values == [(100, False)]
    assert finished.progress_visible_calls == [False]
    assert finished.current_paths_calls == [[]]
    assert finished.applied_contexts
    assert finished.refresh_calls == [True]
    assert info_calls


def test_bag_delete_action_returns_start_result(monkeypatch, tmp_path):
    _FakeThread.started = []
    monkeypatch.setattr(bag_transfer_actions.threading, "Thread", _FakeThread)
    monkeypatch.setattr(QMessageBox, "information", lambda *args, **kwargs: None)
    monkeypatch.setattr(QMessageBox, "warning", lambda *args, **kwargs: None)

    busy = _FakeTransferStartPage(tmp_path)
    busy.is_deleting = True

    assert BagTransferActionsMixin.delete_selected_remote_bags(busy) is False
    assert _FakeThread.started == []

    empty = _FakeTransferStartPage(tmp_path)
    empty.selected_paths = []

    assert BagTransferActionsMixin.delete_selected_remote_bags(empty) is False
    assert _FakeThread.started == []

    unsafe = _FakeTransferStartPage(tmp_path)
    unsafe.selected_paths = ["/home/robot/not_a_bag"]

    assert BagTransferActionsMixin.delete_selected_remote_bags(unsafe) is False
    assert _FakeThread.started == []

    cancelled = _FakeTransferStartPage(tmp_path)
    monkeypatch.setattr(QMessageBox, "question", lambda *args, **kwargs: QMessageBox.Cancel)

    assert BagTransferActionsMixin.delete_selected_remote_bags(cancelled) is False
    assert _FakeThread.started == []

    page = _FakeTransferStartPage(tmp_path)
    monkeypatch.setattr(QMessageBox, "question", lambda *args, **kwargs: QMessageBox.Yes)

    assert BagTransferActionsMixin.delete_selected_remote_bags(page) is True
    assert page.is_deleting is True
    assert page.delete_request_id == 5
    assert page.delete_selected_btn.enabled is False
    assert _FakeThread.started


def test_bag_delete_finished_returns_accept_result(monkeypatch, tmp_path):
    warning_calls = []
    info_calls = []
    monkeypatch.setattr(QMessageBox, "warning", lambda *args, **kwargs: warning_calls.append(args))
    monkeypatch.setattr(QMessageBox, "information", lambda *args, **kwargs: info_calls.append(args))

    page = _FakeTransferStartPage(tmp_path)
    page.is_deleting = True
    page.delete_selected_btn.setEnabled(False)

    assert BagTransferActionsMixin._delete_finished(page, ["/opt/data/a"], [], request_id=4) is True
    assert page.is_deleting is False
    assert page.delete_selected_btn.enabled is True
    assert page.refresh_calls == [True]
    assert info_calls
    assert warning_calls == []

    failed = _FakeTransferStartPage(tmp_path)
    failed.is_deleting = True
    failed.delete_selected_btn.setEnabled(False)

    assert BagTransferActionsMixin._delete_finished(failed, ["/opt/data/a"], ["/opt/data/b"], request_id=4) is True
    assert failed.is_deleting is False
    assert failed.delete_selected_btn.enabled is True
    assert failed.refresh_calls == [True]
    assert warning_calls


def test_bag_update_resume_button_returns_change_result(tmp_path):
    class NoResumeButtonPage(BagTransferActionsMixin):
        pass

    assert BagTransferActionsMixin._update_resume_button(NoResumeButtonPage()) is False

    page = _FakeTransferStartPage(tmp_path)
    page.remote_bag_items = [{"path": "/opt/data/rosbag2_l2_20260527_120000", "active": 1}]

    assert BagTransferActionsMixin._update_resume_button(page) is True
    assert page.resume_btn.enabled is True

    assert BagTransferActionsMixin._update_resume_button(page) is False

    page.is_recording = True

    assert BagTransferActionsMixin._update_resume_button(page) is True
    assert page.resume_btn.enabled is False


def test_bag_resume_remote_recording_returns_takeover_result(monkeypatch, tmp_path):
    monkeypatch.setattr(QMessageBox, "information", lambda *args, **kwargs: None)
    monkeypatch.setattr(QMessageBox, "question", lambda *args, **kwargs: QMessageBox.Yes)

    busy = _FakeTransferStartPage(tmp_path)
    busy.is_recording = True

    assert BagTransferActionsMixin.resume_remote_recording(busy) is False
    assert busy.applied_contexts == []

    empty = _FakeTransferStartPage(tmp_path)
    empty.selected_paths = []
    empty.remote_bag_items = []

    assert BagTransferActionsMixin.resume_remote_recording(empty) is False
    assert empty.applied_contexts == []

    cancelled = _FakeTransferStartPage(tmp_path)
    cancelled.selected_paths = []
    cancelled.remote_bag_items = [
        {"path": "/opt/data/rosbag2_l2_20260527_120000", "active": 1, "size": 2048},
        {"path": "/opt/data/rosbag2_l2_20260527_120100", "active": 1, "size": 2048},
    ]
    monkeypatch.setattr(QMessageBox, "question", lambda *args, **kwargs: QMessageBox.Cancel)

    assert BagTransferActionsMixin.resume_remote_recording(cancelled) is False
    assert cancelled.applied_contexts == []

    page = _FakeTransferStartPage(tmp_path)
    page.remote_bag_items = [{"path": "/opt/data/rosbag2_l2_20260527_120000", "active": 1, "size": 2048}]
    monkeypatch.setattr(QMessageBox, "question", lambda *args, **kwargs: QMessageBox.Yes)

    assert BagTransferActionsMixin.resume_remote_recording(page) is True
    assert page.is_recording is True
    assert page.stop_requested is False
    assert page.start_btn.enabled is False
    assert page.resume_btn.enabled is False
    assert page.stop_btn.enabled is True
    assert page.record_status_label.text() == "正在录制(已接管)"
    assert page.current_bag_size_label.text() == "查询中..."
    assert page.current_paths_calls == [["/opt/data/rosbag2_l2_20260527_120000"]]
    assert page.duration_timer.started == 1
    assert page.bag_size_timer.started == 1
    assert page.duration_updates == 1
    assert page.refreshed_size is False
    assert page.applied_contexts[-1]["paths"] == ["/opt/data/rosbag2_l2_20260527_120000"]
    assert page.applied_contexts[-1]["profile"] is page.backend_instance.profile
    assert page.logs == ["[录制] 已接管远端录制: /opt/data/rosbag2_l2_20260527_120000"]


def test_bag_choose_local_dir_returns_selection_result(monkeypatch, tmp_path):
    page = _FakeTransferStartPage(tmp_path)
    monkeypatch.setattr("dog_remote_tool.ui.pages.bag.page.QFileDialog.getExistingDirectory", lambda *args, **kwargs: "")

    assert BagPage.choose_local_dir(page) is False
    assert page.local_dir.text() == str(tmp_path)

    monkeypatch.setattr("dog_remote_tool.ui.pages.bag.page.QFileDialog.getExistingDirectory", lambda *args, **kwargs: "/tmp/bags")

    assert BagPage.choose_local_dir(page) is True
    assert page.local_dir.text() == "/tmp/bags"


def test_bag_topic_add_and_remove_return_change_result(monkeypatch):
    monkeypatch.setattr(QMessageBox, "information", lambda *args, **kwargs: None)
    no_key = _FakeTopicEditPage(key="", topic_entry="/odom")

    assert BagPage.add_topic_to_active_theme(no_key) is False
    assert no_key.record_topics["nav"]["topics"] == ["/cmd_vel"]

    duplicate = _FakeTopicEditPage(topic_entry="/cmd_vel")

    assert BagPage.add_topic_to_active_theme(duplicate) is False
    assert duplicate.topic_entry.cleared is False
    assert duplicate.persisted == []

    page = _FakeTopicEditPage(topic_entry="odom")

    assert BagPage.add_topic_to_active_theme(page) is True
    assert page.record_topics["nav"]["topics"] == ["/cmd_vel", "/odom"]
    assert page.topic_entry.cleared is True
    assert page.persisted == ["nav"]
    assert page.selection_updates == 1
    assert page.logs == ["[主题Topic] 已添加: nav -> /odom"]

    no_selection = _FakeTopicEditPage(selected_rows=[])

    assert BagPage.remove_selected_topics_from_active_theme(no_selection) is False
    assert no_selection.record_topics["nav"]["topics"] == ["/cmd_vel"]

    remove_page = _FakeTopicEditPage(topics=["/cmd_vel", "/odom"], selected_rows=[1])

    assert BagPage.remove_selected_topics_from_active_theme(remove_page) is True
    assert remove_page.topic_table.removed_rows == [1]
    assert remove_page.record_topics["nav"]["topics"] == ["/cmd_vel"]
    assert remove_page.persisted == ["nav"]
    assert remove_page.selection_updates == 1
    assert remove_page.logs == ["[主题Topic] 已从 nav 删除: /odom"]


def test_bag_topic_theme_management_returns_change_result(monkeypatch):
    monkeypatch.setattr(QMessageBox, "information", lambda *args, **kwargs: None)
    monkeypatch.setattr(QMessageBox, "warning", lambda *args, **kwargs: None)
    monkeypatch.setattr(bag, "save_topic_overrides", lambda overrides: None)
    monkeypatch.setattr(bag, "save_custom_presets", lambda presets: None)
    monkeypatch.setattr(bag, "load_record_topics", lambda product: {"nav": {"name": "导航", "topics": ["/cmd_vel"]}})
    monkeypatch.setattr(bag, "apply_topic_overrides", lambda topics, product, overrides: topics)
    monkeypatch.setattr(
        bag,
        "apply_custom_presets",
        lambda topics, presets: {
            **topics,
            **{bag.custom_preset_key(name): {"name": name, "topics": values} for name, values in presets.items()},
        },
    )

    no_name = _FakeTopicEditPage(topic_name="")

    assert BagPage.save_active_topic_name(no_name) is False
    assert no_name.refreshed == []

    duplicate = _FakeTopicEditPage(topic_name="巡检")

    assert BagPage.save_active_topic_name(duplicate) is False
    assert duplicate.refreshed == []

    builtin = _FakeTopicEditPage(topic_name="导航改名")

    assert BagPage.save_active_topic_name(builtin) is True
    assert builtin.record_topics["nav"]["name"] == "导航改名"
    assert builtin.topic_overrides["nxl2"]["nav"]["name"] == "导航改名"
    assert builtin.refreshed == [["nav"]]
    assert builtin.selection_updates == 1
    assert builtin.logs == ["[主题Topic] 已更新主题名称: nav -> 导航改名"]

    same_custom = _FakeTopicEditPage(key="custom_preset::巡检", topic_name="巡检")

    assert BagPage.save_active_topic_name(same_custom) is False

    custom = _FakeTopicEditPage(key="custom_preset::巡检", topic_name="巡检改名")

    assert BagPage.save_active_topic_name(custom) is True
    assert custom.custom_presets == {"巡检改名": ["/scan"]}
    assert custom.refreshed == [[bag.custom_preset_key("巡检改名")]]
    assert custom.selection_updates == 1
    assert custom.logs == ["[自定义Topic] 已重命名主题: 巡检 -> 巡检改名"]

    monkeypatch.setattr("dog_remote_tool.ui.pages.bag.topic_actions.QInputDialog.getText", lambda *args, **kwargs: ("", False))
    cancelled = _FakeTopicEditPage()

    assert BagPage.create_custom_theme(cancelled) is False
    assert cancelled.custom_presets == {"巡检": ["/scan"]}

    monkeypatch.setattr("dog_remote_tool.ui.pages.bag.topic_actions.QInputDialog.getText", lambda *args, **kwargs: ("巡检", True))
    exists = _FakeTopicEditPage()

    assert BagPage.create_custom_theme(exists) is False
    assert exists.custom_presets == {"巡检": ["/scan"]}

    monkeypatch.setattr("dog_remote_tool.ui.pages.bag.topic_actions.QInputDialog.getText", lambda *args, **kwargs: ("新主题", True))
    created = _FakeTopicEditPage()

    assert BagPage.create_custom_theme(created) is True
    assert created.custom_presets["新主题"] == []
    assert created.refreshed == [[bag.custom_preset_key("新主题")]]
    assert created.selection_updates == 1
    assert created.logs == ["[主题] 已新增: 新主题"]

    no_delete_key = _FakeTopicEditPage(key="")

    assert BagPage.delete_active_theme(no_delete_key) is False

    builtin_delete = _FakeTopicEditPage(key="nav")

    assert BagPage.delete_active_theme(builtin_delete) is False
    assert builtin_delete.custom_presets == {"巡检": ["/scan"]}

    monkeypatch.setattr(QMessageBox, "question", lambda *args, **kwargs: QMessageBox.No)
    cancelled_delete = _FakeTopicEditPage(key="custom_preset::巡检")

    assert BagPage.delete_active_theme(cancelled_delete) is False
    assert cancelled_delete.custom_presets == {"巡检": ["/scan"]}

    monkeypatch.setattr(QMessageBox, "question", lambda *args, **kwargs: QMessageBox.Yes)
    deleted = _FakeTopicEditPage(key="custom_preset::巡检")

    assert BagPage.delete_active_theme(deleted) is True
    assert deleted.custom_presets == {}
    assert deleted.refreshed == [[]]
    assert deleted.selection_updates == 1
    assert deleted.logs == ["[主题] 已删除: 巡检"]


def test_bag_reload_topic_config_returns_change_result(monkeypatch):
    topics = {"nav": {"name": "导航", "topics": ["/cmd_vel"]}}
    monkeypatch.setattr(bag, "profile_product_key", lambda profile: "nxl2")
    monkeypatch.setattr(bag, "load_record_topics", lambda product: topics)
    monkeypatch.setattr(bag, "apply_topic_overrides", lambda loaded, product, overrides: loaded)
    monkeypatch.setattr(bag, "apply_custom_presets", lambda loaded, presets: dict(loaded))
    monkeypatch.setattr(bag, "recording_storage_for_profile", lambda profile, product: "mcap")
    monkeypatch.setattr(bag_topic_config, "default_remote_bag_path", lambda product, home: "/opt/data")

    page = _FakeReloadTopicConfigPage()

    assert BagPage.reload_topic_config(page) is True
    assert page.product == "nxl2"
    assert page.record_topics == topics
    assert page.remote_path.text() == "/opt/data"
    assert page.storage_combo.currentText() == "mcap"
    assert page.refreshed == [None]
    assert page.selection_updates == 1

    assert BagPage.reload_topic_config(page) is False
    assert page.refreshed == [None, None]
    assert page.selection_updates == 2


class _FakeRecordPage:
    def __init__(self):
        self.record_start_request_id = 2
        self.record_stop_request_id = 4
        self.is_starting_recording = True
        self.is_recording = True
        self.stop_requested = True


class _FakeRecordPlan:
    def __init__(self):
        self.remote_paths = ["/opt/data/rosbag2_l2_20260527_120000"]
        self.storage = "mcap"
        self.topics = ["/cmd_vel", "/odom"]
        self.command = "record-command"


class _FakeRecordBackend:
    def __init__(self, profile, product, log):
        self.profile = profile
        self.product = product
        self.log = log
        self.build_calls = []

    def build_record_plan(self, remote_path, storage, cache_gb, topic_plan):
        self.build_calls.append((remote_path, storage, cache_gb, topic_plan))
        return _FakeRecordPlan()


class _FakeRecordTimer:
    def __init__(self):
        self.started = 0
        self.stopped = 0

    def start(self):
        self.started += 1

    def stop(self):
        self.stopped += 1


class _FakeRecordingProcess:
    def __init__(self, *, running=True, timeout_on_wait=False):
        self.running = running
        self.timeout_on_wait = timeout_on_wait
        self.terminated = 0
        self.killed = 0
        self.waits = []

    def poll(self):
        return None if self.running else 0

    def terminate(self):
        self.terminated += 1

    def wait(self, timeout=None):
        self.waits.append(timeout)
        if self.timeout_on_wait and self.terminated and not self.killed:
            raise bag_page.subprocess.TimeoutExpired("ssh", timeout)
        self.running = False

    def kill(self):
        self.killed += 1


class _FakeCleanupPage:
    def __init__(self, process=None):
        self.recording_process = process
        self.logs = []

    def _log(self, message):
        self.logs.append(message)


class _FakeShutdownPage:
    def __init__(self):
        self.page_active = True
        self.remote_topic_request_id = 10
        self.topic_check_request_id = 12
        self.remote_bags_request_id = 14
        self.bag_size_request_id = 16
        self.pull_request_id = 2
        self.delete_request_id = 4
        self.record_start_request_id = 6
        self.record_stop_request_id = 8
        self.duration_timer = _FakeRecordTimer()
        self.bag_size_timer = _FakeRecordTimer()
        self.recording_process = _FakeRecordingProcess()
        self.logs = []

    def _log(self, message):
        self.logs.append(message)

    def _cleanup_local_recording_process(self):
        return BagPage._cleanup_local_recording_process(self)


class _FakeRecordContextPage:
    def __init__(self):
        self.bag_size_request_id = 2
        self.is_reading_bag_size = False
        self.current_bag_paths = []
        self.current_record_profile = None
        self.current_record_topics = []
        self.current_record_product = ""
        self.current_record_themes = []
        self.current_record_started_at = None
        self.current_record_finished_at = None
        self.current_record_duration_seconds = None
        self.current_record_storage = ""
        self.current_record_cache_gb = 0


class _FakeLifecyclePage:
    def __init__(self, *, active=False, recording=False):
        self.page_active = active
        self.is_recording = recording
        self.duration_timer = _FakeRecordTimer()
        self.bag_size_timer = _FakeRecordTimer()
        self.refresh_calls = []

    def refresh_remote_bags(self, auto=False):
        self.refresh_calls.append(auto)
        return True


class _FakeCurrentBagPathPage:
    def __init__(self):
        self.current_bag_label = _FakeText("无")
        self.current_bag_size_label = _FakeText("--")
        self.record_detail_visible = False
        self.detail_visible_calls = []

    def _set_record_detail_visible(self, visible):
        self.detail_visible_calls.append(visible)
        self.record_detail_visible = visible


class _FakeVisibleWidget:
    def __init__(self, visible=False):
        self.visible = visible
        self.calls = []

    def isVisible(self):
        return self.visible

    def setVisible(self, visible):
        self.calls.append(visible)
        self.visible = visible


class _FakeStyle:
    def __init__(self):
        self.unpolished = 0
        self.polished = 0

    def unpolish(self, _widget):
        self.unpolished += 1

    def polish(self, _widget):
        self.polished += 1


class _FakeStatusLabel:
    def __init__(self, text="", object_name="BagStatusWarn", visible=False):
        self._text = text
        self.object_name = object_name
        self.visible = visible
        self.style_obj = _FakeStyle()

    def text(self):
        return self._text

    def objectName(self):
        return self.object_name

    def setObjectName(self, object_name):
        self.object_name = object_name

    def isVisible(self):
        return self.visible

    def setVisible(self, visible):
        self.visible = visible

    def style(self):
        return self.style_obj


class _FakeRecordDetailVisiblePage:
    def __init__(self, visible=False):
        self.record_detail_widget = _FakeVisibleWidget(visible)


class _FakePullProgressVisiblePage:
    def __init__(self, visible=False):
        self.progress_bar = _FakeVisibleWidget(visible)
        self.transfer_percent_label = _FakeVisibleWidget(visible)
        self.transfer_speed_label = _FakeVisibleWidget(visible)
        self.transfer_eta_label = _FakeVisibleWidget(visible)


class _FakeProgressBar:
    def __init__(self, value=0):
        self._value = value
        self.values = []

    def value(self):
        return self._value

    def setValue(self, value):
        self.values.append(value)
        self._value = value


class _FakeProgressAnimation:
    def __init__(self, state=None):
        self._state = bag_page.QAbstractAnimation.Stopped if state is None else state
        self.stopped = 0
        self.started = 0
        self.start_values = []
        self.end_values = []

    def state(self):
        return self._state

    def stop(self):
        self.stopped += 1
        self._state = bag_page.QAbstractAnimation.Stopped

    def setStartValue(self, value):
        self.start_values.append(value)

    def setEndValue(self, value):
        self.end_values.append(value)

    def start(self):
        self.started += 1
        self._state = bag_page.QAbstractAnimation.Running


class _FakePullProgressValuePage:
    def __init__(self, value=0, animation_state=None):
        self.progress_bar = _FakeProgressBar(value)
        self.progress_animation = _FakeProgressAnimation(animation_state)


class _FakePullProgressUpdatePage(BagTransferActionsMixin):
    def __init__(self):
        self.pull_request_id = 7
        self.transfer_progress_label = ""
        self.transfer_started_at = 0.0
        self.progress_bar = _FakeProgressBar(0)
        self.record_status_label = _FakeText()
        self.transfer_percent_label = _FakeText()
        self.transfer_speed_label = _FakeText()
        self.transfer_eta_label = _FakeText()
        self.progress_values = []

    def _set_pull_progress_value(self, value, animated=True):
        self.progress_values.append((value, animated))
        self.progress_bar.setValue(value)


class _FakeRemoteTopicPopulatePage:
    def __init__(self, dialog=None):
        self.remote_topic_dialog = dialog
        self.remote_topic_rows = [{"name": "/cmd_vel"}]
        self.record_topics = {"nav": {"topics": ["/cmd_vel"]}}

    def _topic_display_name(self, key):
        return {"nav": "导航"}.get(key, key)

    def selected_keys(self):
        return ["nav"]

    def _populate_remote_topic_table(self, rows):
        return BagPage._populate_remote_topic_table(self, rows)


class _FakeRemoteTopicDialogLifecyclePage(_FakeRemoteTopicPopulatePage):
    def __init__(self):
        super().__init__(None)
        self.profile_value = _FakeProfile()
        self.scan_starts = 0
        self.view_changes = 0

    def profile(self):
        return self.profile_value

    def _start_remote_topic_scan(self):
        self.scan_starts += 1

    def _remote_topic_view_changed(self):
        self.view_changes += 1

    def _refresh_remote_topic_theme_combo(self):
        return BagPage._refresh_remote_topic_theme_combo(self)

    def _remote_topic_dialog_closed(self):
        return BagPage._remote_topic_dialog_closed(self)


def test_bag_record_detail_visible_returns_change_result():
    page = _FakeRecordDetailVisiblePage(visible=False)

    assert BagPage._set_record_detail_visible(page, False) is False
    assert page.record_detail_widget.calls == [False]

    assert BagPage._set_record_detail_visible(page, True) is True
    assert page.record_detail_widget.visible is True

    assert BagPage._set_record_detail_visible(page, True) is False
    assert page.record_detail_widget.calls == [False, True, True]


def test_bag_pull_progress_visible_returns_change_result():
    page = _FakePullProgressVisiblePage(visible=False)

    assert BagPage._set_pull_progress_visible(page, False) is False
    assert page.progress_bar.calls == [False]
    assert page.transfer_percent_label.calls == [False]
    assert page.transfer_speed_label.calls == [False]
    assert page.transfer_eta_label.calls == [False]

    assert BagPage._set_pull_progress_visible(page, True) is True
    assert page.progress_bar.visible is True
    assert page.transfer_percent_label.visible is True
    assert page.transfer_speed_label.visible is True
    assert page.transfer_eta_label.visible is True

    assert BagPage._set_pull_progress_visible(page, True) is False


def test_bag_pull_progress_value_returns_change_result():
    page = _FakePullProgressValuePage(value=0)

    assert BagPage._set_pull_progress_value(page, 0) is False
    assert page.progress_animation.started == 0
    assert page.progress_bar.values == []

    assert BagPage._set_pull_progress_value(page, 55) is True
    assert page.progress_animation.start_values == [0]
    assert page.progress_animation.end_values == [55]
    assert page.progress_animation.started == 1

    running_page = _FakePullProgressValuePage(value=55, animation_state=bag_page.QAbstractAnimation.Running)
    assert BagPage._set_pull_progress_value(running_page, 55, animated=False) is True
    assert running_page.progress_animation.stopped == 1
    assert running_page.progress_bar.values == [55]

    clamp_page = _FakePullProgressValuePage(value=0)
    assert BagPage._set_pull_progress_value(clamp_page, 150, animated=False) is True
    assert clamp_page.progress_bar.values == [100]


def test_bag_update_pull_progress_returns_accept_result(monkeypatch):
    page = _FakePullProgressUpdatePage()
    ticks = iter([100.0, 103.0])
    monkeypatch.setattr(bag_transfer_actions.time, "monotonic", lambda: next(ticks))

    assert page._update_pull_progress("正在拉取Bag包 1/2", 25, "1 MB/s", request_id=7) is True
    assert page.transfer_progress_label == "正在拉取Bag包 1/2"
    assert page.transfer_started_at == 100.0
    assert page.progress_values == [(25, True)]
    assert page.record_status_label.text() == "拉取Bag 1/2"
    assert page.transfer_percent_label.text() == "25%"
    assert page.transfer_speed_label.text() == "速度 1 MB/s"
    assert page.transfer_eta_label.text() == "预计 00:09"


def test_bag_remote_topic_table_population_returns_update_result():
    no_dialog = _FakeRemoteTopicPopulatePage()

    assert BagPage._refresh_remote_topic_theme_combo(no_dialog) is False
    assert BagPage._populate_remote_topic_table(no_dialog, [{"name": "/cmd_vel"}]) is False
    assert BagPage._remote_topic_view_changed(no_dialog) is False

    dialog = _FakeRemoteTopicDialog()
    page = _FakeRemoteTopicPopulatePage(dialog)

    assert BagPage._refresh_remote_topic_theme_combo(page) is True
    record_topics, display_name = dialog.theme_refreshes[-1]
    assert record_topics == page.record_topics
    assert display_name("nav") == "导航"

    assert BagPage._populate_remote_topic_table(page, [{"name": "/scan"}]) is True
    rows, record_topics, display_name, selected_keys = dialog.populated[-1]
    assert rows == [{"name": "/scan"}]
    assert record_topics == page.record_topics
    assert display_name("nav") == "导航"
    assert selected_keys == {"nav"}

    assert BagPage._remote_topic_view_changed(page) is True
    assert dialog.populated[-1][0] == [{"name": "/cmd_vel"}]


def test_bag_remote_topic_dialog_lifecycle_returns_change_result(monkeypatch):
    monkeypatch.setattr(bag_page, "RemoteTopicDialog", _FakeBuildRemoteTopicDialog)
    page = _FakeRemoteTopicDialogLifecyclePage()

    assert BagPage._build_remote_topic_dialog(page) is True
    assert isinstance(page.remote_topic_dialog, _FakeBuildRemoteTopicDialog)
    assert page.remote_topic_dialog.finished.connected == [page._remote_topic_dialog_closed]
    record_topics, display_name = page.remote_topic_dialog.theme_refreshes[-1]
    assert record_topics == page.record_topics
    assert display_name("nav") == "导航"

    assert BagPage._remote_topic_dialog_closed(page) is True
    assert page.remote_topic_dialog is None
    assert BagPage._remote_topic_dialog_closed(page) is False


def test_bag_label_status_returns_change_result():
    label = _FakeStatusLabel(text="", object_name="BagStatusWarn", visible=False)

    assert BagPage._set_label_status(None, label, "warn") is False
    assert label.object_name == "BagStatusWarn"
    assert label.visible is False
    assert label.style_obj.unpolished == 1
    assert label.style_obj.polished == 1

    label._text = "正常"

    assert BagPage._set_label_status(None, label, "ok") is True
    assert label.object_name == "BagStatusOk"
    assert label.visible is True

    assert BagPage._set_label_status(None, label, "ok") is False
    assert label.style_obj.unpolished == 3
    assert label.style_obj.polished == 3


def test_bag_log_returns_emit_result():
    page = type("FakeLogPage", (), {"log_signal": _FakeLogSignal()})()

    assert BagPage._log(page, "开始录制") is True
    assert page.log_signal.messages == ["[信息] 录包 开始录制\n"]


def test_bag_page_lifecycle_returns_active_change_result(monkeypatch):
    single_shots = []

    def fake_single_shot(delay, callback):
        single_shots.append(delay)
        callback()

    monkeypatch.setattr(bag_page.QTimer, "singleShot", fake_single_shot)

    active = _FakeLifecyclePage(active=True)

    assert BagPage.activate_page(active) is False
    assert single_shots == []

    idle = _FakeLifecyclePage(active=False, recording=False)

    assert BagPage.activate_page(idle) is True
    assert idle.page_active is True
    assert idle.duration_timer.started == 0
    assert idle.bag_size_timer.started == 0
    assert idle.refresh_calls == [True]
    assert single_shots == [150]

    recording = _FakeLifecyclePage(active=False, recording=True)

    assert BagPage.activate_page(recording) is True
    assert recording.duration_timer.started == 1
    assert recording.bag_size_timer.started == 1

    assert BagPage.deactivate_page(recording) is True
    assert recording.page_active is False
    assert recording.duration_timer.stopped == 1
    assert recording.bag_size_timer.stopped == 1

    inactive = _FakeLifecyclePage(active=False)

    assert BagPage.deactivate_page(inactive) is False
    assert inactive.duration_timer.stopped == 1
    assert inactive.bag_size_timer.stopped == 1


def test_bag_cleanup_local_recording_process_returns_cleanup_result():
    empty = _FakeCleanupPage()

    assert BagPage._cleanup_local_recording_process(empty) is False

    exited_process = _FakeRecordingProcess(running=False)
    exited = _FakeCleanupPage(exited_process)

    assert BagPage._cleanup_local_recording_process(exited) is True
    assert exited.recording_process is None
    assert exited_process.terminated == 0

    running_process = _FakeRecordingProcess()
    running = _FakeCleanupPage(running_process)

    assert BagPage._cleanup_local_recording_process(running) is True
    assert running.recording_process is None
    assert running_process.terminated == 1
    assert running_process.killed == 0
    assert running.logs == ["[录制] 本地录制连接已退出"]

    stuck_process = _FakeRecordingProcess(timeout_on_wait=True)
    stuck = _FakeCleanupPage(stuck_process)

    assert BagPage._cleanup_local_recording_process(stuck) is True
    assert stuck.recording_process is None
    assert stuck_process.terminated == 1
    assert stuck_process.killed == 1
    assert stuck.logs == ["[录制] 本地录制连接未正常退出，已结束该连接"]


def test_bag_shutdown_processes_returns_shutdown_result():
    page = _FakeShutdownPage()
    process = page.recording_process

    assert BagPage.shutdown_processes(page) is True
    assert page.page_active is False
    assert page.remote_topic_request_id == 11
    assert page.topic_check_request_id == 13
    assert page.remote_bags_request_id == 15
    assert page.bag_size_request_id == 17
    assert page.pull_request_id == 3
    assert page.delete_request_id == 5
    assert page.record_start_request_id == 7
    assert page.record_stop_request_id == 9
    assert page.duration_timer.stopped == 1
    assert page.bag_size_timer.stopped == 1
    assert page.recording_process is None
    assert process.terminated == 1
    assert page.logs == ["[录制] 本地录制连接已退出"]


def test_bag_apply_record_context_returns_change_result():
    page = _FakeRecordContextPage()
    profile = get_product("xg2_s100")
    started_at = datetime(2026, 5, 27, 12, 0, 0)
    context = bag_helpers.record_context(
        ["/opt/data/rosbag2_l2_20260527_120000"],
        "nxl2",
        "mcap",
        8,
        profile=profile,
        topics=["/cmd_vel"],
        themes=["导航"],
        started_at=started_at,
    )

    assert BagPage._apply_record_context(page, context) is True
    assert page.bag_size_request_id == 3
    assert page.is_reading_bag_size is False
    assert page.current_bag_paths == ["/opt/data/rosbag2_l2_20260527_120000"]
    assert page.current_record_profile is profile
    assert page.current_record_topics == ["/cmd_vel"]
    assert page.current_record_product == "nxl2"
    assert page.current_record_themes == ["导航"]
    assert page.current_record_started_at == started_at
    assert page.current_record_storage == "mcap"
    assert page.current_record_cache_gb == 8

    assert BagPage._apply_record_context(page, context) is False
    assert page.bag_size_request_id == 4

    page.is_reading_bag_size = True

    assert BagPage._apply_record_context(page, context) is True
    assert page.is_reading_bag_size is False
    assert page.bag_size_request_id == 5


def test_bag_current_bag_paths_return_ui_change_result():
    page = _FakeCurrentBagPathPage()

    assert BagPage._set_current_bag_paths(page, []) is False
    assert page.current_bag_label.text() == "无"
    assert page.current_bag_label.toolTip() == ""
    assert page.current_bag_size_label.text() == "--"
    assert page.detail_visible_calls == [False]

    assert BagPage._set_current_bag_paths(page, ["/tmp/a"]) is True
    assert page.current_bag_label.text() == "a"
    assert page.current_bag_label.toolTip() == "/tmp/a"
    assert page.record_detail_visible is True

    assert BagPage._set_current_bag_paths(page, ["/tmp/a"]) is False

    page.current_bag_size_label.setText("12 MB")

    assert BagPage._set_current_bag_paths(page, []) is True
    assert page.current_bag_label.text() == "无"
    assert page.current_bag_size_label.text() == "--"
    assert page.record_detail_visible is False


class _FakeRecordStartStopPage:
    def __init__(self):
        self.is_recording = False
        self.is_starting_recording = False
        self.stop_requested = False
        self.product = "nxl2"
        self.remote_path = _FakeText("/opt/data")
        self.storage_combo = _FakeCombo("mcap")
        self.cache_spin = _FakeSpin(8)
        self.start_btn = _FakeButton()
        self.resume_btn = _FakeButton()
        self.stop_btn = _FakeButton()
        self.record_status_label = _FakeText()
        self.current_bag_size_label = _FakeText()
        self.duration_label = _FakeText()
        self.duration_timer = _FakeRecordTimer()
        self.bag_size_timer = _FakeRecordTimer()
        self.record_start_request_id = 2
        self.record_stop_request_id = 4
        self.start_time = 123.0
        self.current_record_finished_at = None
        self.current_record_duration_seconds = None
        self.current_bag_paths = ["/old"]
        self.current_record_topics = ["/cmd_vel", "/odom"]
        self.logs = []
        self.contexts = []
        self.current_paths_calls = []
        self.progress_visible_calls = []
        self.detail_visible_calls = []
        self.progress_values = []
        self.resume_updates = 0
        self.refreshed_size = None
        self.remote_refresh_calls = []
        self.pull_calls = []
        self.backend_instance = _FakeBackend()

    def profile(self):
        return self.backend_instance.profile

    def topic_plan(self):
        return _FakeTopicPlan(["/cmd_vel", "/odom"])

    def selected_keys(self):
        return ["nav"]

    def _topic_display_name(self, key):
        return {"nav": "导航"}.get(key, key)

    def _apply_record_context(self, context):
        self.contexts.append(context)

    def _set_pull_progress_visible(self, visible):
        self.progress_visible_calls.append(visible)

    def _set_record_detail_visible(self, visible):
        self.detail_visible_calls.append(visible)

    def _set_current_bag_paths(self, paths):
        self.current_paths_calls.append(paths)
        self.current_bag_paths = paths[:]

    def _set_pull_progress_value(self, value, animated=True):
        self.progress_values.append((value, animated))

    def _update_resume_button(self):
        self.resume_updates += 1

    def refresh_current_bag_size(self, force=False):
        self.refreshed_size = force

    def refresh_remote_bags(self, auto=False):
        self.remote_refresh_calls.append(auto)

    def pull_current_recording(self, delete_remote_on_success=False):
        self.pull_calls.append(delete_remote_on_success)
        return True

    def _log(self, message):
        self.logs.append(message)

    def _recording_worker(self, *args):
        pass

    def _stop_recording_worker(self, *args):
        pass

    def current_record_backend(self):
        return self.backend_instance


class _FakeTopicEditPage:
    def __init__(self, *, key="nav", topics=None, topic_entry="/odom", topic_name="导航", selected_rows=None):
        self.active_key = key
        self.topic_name_entry = _FakeText(topic_name)
        self.topic_entry = _FakeText(topic_entry)
        self.topic_table = _FakeTopicTable(topics or ["/cmd_vel"], selected_rows)
        self.record_topics = {
            "nav": {"name": "导航", "topics": topics or ["/cmd_vel"]},
            "custom_preset::巡检": {"name": "巡检", "topics": ["/scan"]},
        }
        self.custom_presets = {"巡检": ["/scan"]}
        self.topic_overrides = {}
        self.product = "nxl2"
        self.persisted = []
        self.refreshed = []
        self.selection_updates = 0
        self.logs = []

    def _active_topic_key(self):
        return self.active_key

    def _parse_topic_table(self):
        return bag_topic_editor.topic_table_values(self.topic_table)

    def _apply_topic_table_to_theme(self, key):
        return BagPage._apply_topic_table_to_theme(self, key)

    def _topic_name_exists(self, name, current_key=""):
        return bag_helpers.topic_name_exists(self.record_topics, name, current_key)

    def _persist_topic_config(self, key):
        self.persisted.append(key)

    def _refresh_topic_list(self, keep=None):
        self.refreshed.append(list(keep or []))

    def _topic_selection_changed(self):
        self.selection_updates += 1

    def _log(self, message):
        self.logs.append(message)


class _FakePersistTopicConfigPage:
    def __init__(self):
        self.product = "nxl2"
        self.topic_overrides = {}
        self.custom_presets = {}
        self.record_topics = {}


class _FakeActiveTopicPage:
    def __init__(self, *, key="", table_topics=None):
        self.active_key = key
        self.active_topic_label = _FakeText("当前主题: -")
        self.topic_name_entry = _FakeText("")
        self.topic_table = _FakeTopicTable(table_topics or [])
        self.record_topics = {
            "nav": {"name": "导航", "topics": ["/cmd_vel", "/odom"]},
        }
        self._updating_topic_table = False

    def _active_topic_key(self):
        return self.active_key

    def _topic_display_name(self, key):
        return self.record_topics.get(key, {}).get("name", key)

    def _set_topic_table_from_config(self, config):
        return BagPage._set_topic_table_from_config(self, config)


def test_bag_active_topic_label_refresh_returns_ui_change_result():
    none = _FakeActiveTopicPage(table_topics=["/old"])

    assert BagPage._refresh_active_topic_label(none) is True
    assert none.active_topic_label.text() == "当前主题: -"
    assert none.active_topic_label.toolTip() == ""
    assert none.topic_name_entry.text() == ""
    assert none.topic_name_entry.enabled is False
    assert none.topic_table.topics == []
    assert none.topic_table.enabled is False

    assert BagPage._refresh_active_topic_label(none) is False

    active = _FakeActiveTopicPage(key="nav")

    assert BagPage._refresh_active_topic_label(active) is True
    assert active.active_topic_label.text() == "当前主题: 导航"
    assert active.active_topic_label.toolTip() == "导航"
    assert active.topic_name_entry.text() == "导航"
    assert active.topic_name_entry.enabled is True
    assert active.topic_table.topics == ["/cmd_vel", "/odom"]
    assert active.topic_table.enabled is True

    assert BagPage._refresh_active_topic_label(active) is False


def test_bag_topic_table_refresh_returns_content_change_result():
    page = _FakeActiveTopicPage(table_topics=["/cmd_vel"])
    config = {"topics": ["/cmd_vel", "/odom"]}

    assert BagPage._set_topic_table_from_config(page, config) is True
    assert page.topic_table.topics == ["/cmd_vel", "/odom"]
    assert page._updating_topic_table is False

    assert BagPage._set_topic_table_from_config(page, config) is False
    assert page.topic_table.topics == ["/cmd_vel", "/odom"]

    assert BagPage._set_topic_table_from_config(page, {"topics": ["/scan"]}) is True
    assert page.topic_table.topics == ["/scan"]


def test_bag_topic_table_changed_returns_writeback_result():
    updating = _FakeTopicEditPage(topic_entry="/scan")
    updating._updating_topic_table = True

    assert BagPage._topic_table_changed(updating, None) is False
    assert updating.persisted == []
    assert updating.selection_updates == 0

    no_key = _FakeTopicEditPage(key="", topic_entry="/scan")
    no_key._updating_topic_table = False

    assert BagPage._topic_table_changed(no_key, None) is False
    assert no_key.persisted == []
    assert no_key.selection_updates == 0

    page = _FakeTopicEditPage(topics=["/cmd_vel", "/odom"])
    page._updating_topic_table = False

    assert BagPage._topic_table_changed(page, None) is False
    assert page.record_topics["nav"]["topics"] == ["/cmd_vel", "/odom"]
    assert page.persisted == ["nav"]
    assert page.selection_updates == 1

    changed = _FakeTopicEditPage(topics=["/cmd_vel"])
    changed.topic_table.topics = ["/cmd_vel", "/scan"]
    changed._updating_topic_table = False

    assert BagPage._topic_table_changed(changed, None) is True
    assert changed.record_topics["nav"]["topics"] == ["/cmd_vel", "/scan"]
    assert changed.persisted == ["nav"]
    assert changed.selection_updates == 1


def test_bag_persist_topic_config_returns_save_result(monkeypatch):
    saved_custom = []
    saved_overrides = []
    monkeypatch.setattr(bag, "save_custom_presets", lambda presets: saved_custom.append(dict(presets)))
    monkeypatch.setattr(bag, "save_topic_overrides", lambda overrides: saved_overrides.append(dict(overrides)))

    builtin = _FakePersistTopicConfigPage()
    builtin.record_topics = {"nav": {"name": "导航", "topics": ["/cmd_vel", "/cmd_vel", "/odom"]}}

    assert BagPage._persist_topic_config(builtin, "nav") is True
    assert builtin.topic_overrides == {
        "nxl2": {
            "nav": {
                "name": "导航",
                "topics": ["/cmd_vel", "/odom"],
                "zstd_topics": [],
                "lz4_topics": [],
            }
        }
    }
    assert saved_overrides == [builtin.topic_overrides]

    custom = _FakePersistTopicConfigPage()
    custom_key = bag.custom_preset_key("巡检")
    custom.record_topics = {custom_key: {"name": "巡检", "topics": ["/scan", "/scan"]}}

    assert BagPage._persist_topic_config(custom, custom_key) is True
    assert custom.custom_presets == {"巡检": ["/scan"]}
    assert saved_custom == [{"巡检": ["/scan"]}]

    skipped = _FakePersistTopicConfigPage()

    assert BagPage._persist_topic_config(skipped, "custom") is False
    assert skipped.topic_overrides == {}


class _FakeTopicList:
    def __init__(self, *, count=0, selected=0):
        self._count = count
        self.selected_count = selected
        self.select_all_calls = 0
        self.clear_selection_calls = 0

    def count(self):
        return self._count

    def selectedItems(self):
        return [object()] * self.selected_count

    def selectAll(self):
        self.select_all_calls += 1
        self.selected_count = self._count

    def clearSelection(self):
        self.clear_selection_calls += 1
        self.selected_count = 0


class _FakeListWidgetItem:
    def __init__(self, text):
        self._text = text
        self._data = {}
        self._tooltip = ""
        self._selected = False

    def text(self):
        return self._text

    def setData(self, role, value):
        self._data[role] = value

    def data(self, role):
        return self._data.get(role)

    def setToolTip(self, tooltip):
        self._tooltip = tooltip

    def toolTip(self):
        return self._tooltip

    def setSelected(self, selected):
        self._selected = selected

    def isSelected(self):
        return self._selected


class _FakeRefreshTopicList:
    def __init__(self):
        self.items = []
        self.blocked = []
        self.clear_calls = 0

    def count(self):
        return len(self.items)

    def item(self, row):
        return self.items[row]

    def selectedItems(self):
        return [item for item in self.items if item.isSelected()]

    def blockSignals(self, blocked):
        self.blocked.append(blocked)

    def clear(self):
        self.clear_calls += 1
        self.items = []

    def addItem(self, item):
        self.items.append(item)


class _FakeRefreshTopicListPage:
    def __init__(self):
        self.topic_list = _FakeRefreshTopicList()
        self.record_topics = {
            "nav": {"name": "导航", "topics": ["/cmd_vel"]},
            "sensor": {"name": "传感器", "topics": ["/scan"]},
        }

    def selected_keys(self):
        return bag_page.selected_topic_keys(self.topic_list)

    def _topic_display_name(self, key, config=None):
        return bag_helpers.topic_display_name(self.record_topics, key, config)

    def _topic_tooltip(self, key, config=None):
        return bag_helpers.topic_tooltip(self.record_topics, key, config)


class _FakeTopicSelectionPage:
    def __init__(self, *, count=0, selected=0):
        self.topic_list = _FakeTopicList(count=count, selected=selected)
        self.selection_updates = 0

    def _topic_selection_changed(self):
        self.selection_updates += 1


class _FakeTopicSelectionStatusPage:
    def __init__(self, *, selected=None, topics=None, checking=False):
        self.selected = list(selected or [])
        self.plan = _FakeTopicPlan(list(topics or []))
        self.is_checking_topics = checking
        self.selected_count_label = _FakeText()
        self.preview_count_label = _FakeText()
        self.topic_check_btn = _FakeButton()
        self.active_refreshes = 0

    def selected_keys(self):
        return self.selected

    def topic_plan(self):
        return self.plan

    def _refresh_active_topic_label(self):
        self.active_refreshes += 1


def test_bag_topic_selection_changed_returns_ui_change_result():
    empty = _FakeTopicSelectionStatusPage()

    assert BagPage._topic_selection_changed(empty) is True
    assert empty.selected_count_label.text() == "已选择: 0 个主题"
    assert empty.preview_count_label.text() == "当前录制Topic: 0 个"
    assert empty.topic_check_btn.enabled is False
    assert empty.active_refreshes == 1

    assert BagPage._topic_selection_changed(empty) is False
    assert empty.active_refreshes == 2

    selected = _FakeTopicSelectionStatusPage(selected=["nav"], topics=["/cmd_vel", "/odom"])

    assert BagPage._topic_selection_changed(selected) is True
    assert selected.selected_count_label.text() == "已选择: 1 个主题"
    assert selected.preview_count_label.text() == "当前录制Topic: 2 个"
    assert selected.topic_check_btn.enabled is True

    selected.is_checking_topics = True

    assert BagPage._topic_selection_changed(selected) is True
    assert selected.topic_check_btn.enabled is False


def test_bag_refresh_topic_list_returns_content_change_result(monkeypatch):
    monkeypatch.setattr(bag_topic_config, "QListWidgetItem", _FakeListWidgetItem)
    page = _FakeRefreshTopicListPage()

    assert BagPage._refresh_topic_list(page, keep=["sensor"]) is True
    assert [item.text() for item in page.topic_list.items] == ["导航", "传感器"]
    assert [item.data(bag_page.Qt.UserRole) for item in page.topic_list.items] == ["nav", "sensor"]
    assert [item.isSelected() for item in page.topic_list.items] == [False, True]
    assert page.topic_list.blocked == [True, False]

    assert BagPage._refresh_topic_list(page, keep=["sensor"]) is False

    page.record_topics["nav"]["name"] = "导航改名"

    assert BagPage._refresh_topic_list(page, keep=["sensor"]) is True
    assert [item.text() for item in page.topic_list.items] == ["导航改名", "传感器"]


def test_bag_topic_bulk_selection_returns_change_result():
    empty = _FakeTopicSelectionPage(count=0, selected=0)

    assert BagPage.select_all_topics(empty) is False
    assert empty.topic_list.select_all_calls == 1
    assert empty.selection_updates == 1

    partial = _FakeTopicSelectionPage(count=3, selected=1)

    assert BagPage.select_all_topics(partial) is True
    assert partial.topic_list.selected_count == 3
    assert partial.selection_updates == 1

    already_all = _FakeTopicSelectionPage(count=2, selected=2)

    assert BagPage.select_all_topics(already_all) is False
    assert already_all.topic_list.selected_count == 2
    assert already_all.selection_updates == 1

    none = _FakeTopicSelectionPage(count=3, selected=0)

    assert BagPage.deselect_all_topics(none) is False
    assert none.topic_list.clear_selection_calls == 1
    assert none.selection_updates == 1

    selected = _FakeTopicSelectionPage(count=3, selected=2)

    assert BagPage.deselect_all_topics(selected) is True
    assert selected.topic_list.selected_count == 0
    assert selected.selection_updates == 1


def test_bag_start_recording_returns_thread_start_result(monkeypatch):
    _FakeThread.started = []
    monkeypatch.setattr(bag_page.threading, "Thread", _FakeThread)
    monkeypatch.setattr(bag, "BagBackend", _FakeRecordBackend)
    monkeypatch.setattr(QMessageBox, "warning", lambda *args, **kwargs: None)
    monkeypatch.setattr(QMessageBox, "critical", lambda *args, **kwargs: None)

    busy = _FakeRecordStartStopPage()
    busy.is_recording = True

    assert BagPage.start_recording(busy) is False
    assert _FakeThread.started == []

    broken = _FakeRecordStartStopPage()
    broken.topic_plan = lambda: (_ for _ in ()).throw(RuntimeError("bad topics"))

    assert BagPage.start_recording(broken) is False
    assert _FakeThread.started == []

    page = _FakeRecordStartStopPage()

    assert BagPage.start_recording(page) is True
    assert page.is_starting_recording is True
    assert page.is_recording is False
    assert page.stop_requested is False
    assert page.record_start_request_id == 3
    assert page.start_time is None
    assert page.start_btn.enabled is False
    assert page.resume_btn.enabled is False
    assert page.stop_btn.enabled is False
    assert page.record_status_label.text() == "启动录制..."
    assert page.current_bag_size_label.text() == "查询中..."
    assert page.progress_visible_calls == [False]
    assert page.detail_visible_calls == [True]
    assert page.current_paths_calls == [["/opt/data/rosbag2_l2_20260527_120000"]]
    assert page.progress_values == [(0, False)]
    assert page.contexts[-1]["paths"] == ["/opt/data/rosbag2_l2_20260527_120000"]
    assert page.contexts[-1]["topics"] == ["/cmd_vel", "/odom"]
    assert page.contexts[-1]["themes"] == ["导航"]
    assert _FakeThread.started[-1][1][3] == 3


def test_bag_stop_recording_returns_thread_start_result(monkeypatch):
    _FakeThread.started = []
    monkeypatch.setattr(bag_page.threading, "Thread", _FakeThread)
    idle = _FakeRecordStartStopPage()

    assert BagPage.stop_recording(idle) is False
    assert _FakeThread.started == []

    page = _FakeRecordStartStopPage()
    page.is_recording = True
    page.current_bag_paths = ["/opt/data/rosbag2_l2_20260527_120000"]

    assert BagPage.stop_recording(page) is True
    assert page.record_status_label.text() == "正在停止..."
    assert page.stop_btn.enabled is False
    assert page.stop_requested is True
    assert page.record_stop_request_id == 5
    assert _FakeThread.started[-1][1][1] == ["/opt/data/rosbag2_l2_20260527_120000"]
    assert _FakeThread.started[-1][1][2] == ["/cmd_vel", "/odom"]
    assert _FakeThread.started[-1][1][3] == 5


def test_bag_quick_check_remote_recording_logs_summary():
    class Backend:
        def validate_remote_recorded_topics(self, paths, topics):
            assert paths == ["/opt/data/rosbag2_l2_20260527_120000"]
            assert topics == ["/cmd_vel", "/odom"]
            return {
                "ok": False,
                "summary": "话题部分异常，1/2 个目标Topic有数据",
                "details": ["缺失Topic: /odom", "有数据Topic: 1/2"],
            }

    page = _FakeRecordStartStopPage()

    summary = BagPage._quick_check_remote_recording(
        page,
        Backend(),
        ["/opt/data/rosbag2_l2_20260527_120000"],
        ["/cmd_vel", "/odom"],
    )

    assert summary == "话题部分异常，1/2 个目标Topic有数据"
    assert page.logs == [
        "[录后检查] 异常: 话题部分异常，1/2 个目标Topic有数据",
        "[录后检查] 缺失Topic: /odom",
        "[录后检查] 有数据Topic: 1/2",
    ]


def test_bag_update_duration_returns_label_change_result(monkeypatch):
    monkeypatch.setattr(bag_page.time, "time", lambda: 3761.9)
    idle = _FakeRecordStartStopPage()
    idle.is_recording = False

    assert BagPage._update_duration(idle) is False
    assert idle.duration_label.text() == ""

    missing_start = _FakeRecordStartStopPage()
    missing_start.is_recording = True
    missing_start.start_time = None

    assert BagPage._update_duration(missing_start) is False
    assert missing_start.duration_label.text() == ""

    page = _FakeRecordStartStopPage()
    page.is_recording = True
    page.start_time = 100.0

    assert BagPage._update_duration(page) is True
    assert page.duration_label.text() == "01:01:01"

    assert BagPage._update_duration(page) is False
    assert page.duration_label.text() == "01:01:01"


def test_bag_record_start_finished_returns_accept_result(monkeypatch):
    monkeypatch.setattr(QMessageBox, "warning", lambda *args, **kwargs: None)

    failed = _FakeRecordStartStopPage()
    failed.is_starting_recording = True

    assert BagPage._record_start_finished(failed, False, "ssh failed", request_id=2) is True
    assert failed.is_starting_recording is False
    assert failed.is_recording is False
    assert failed.start_btn.enabled is True
    assert failed.stop_btn.enabled is False
    assert failed.resume_updates == 1
    assert failed.duration_label.text() == "00:00:00"
    assert failed.record_status_label.text() == "启动失败"
    assert failed.current_paths_calls == [[]]
    assert failed.logs == ["✗ 远端录制启动失败: ssh failed"]

    success = _FakeRecordStartStopPage()
    success.is_starting_recording = True
    success.is_recording = False
    success.stop_requested = True

    assert BagPage._record_start_finished(success, True, "", request_id=2) is True
    assert success.is_starting_recording is False
    assert success.is_recording is True
    assert success.stop_requested is False
    assert success.start_btn.enabled is False
    assert success.resume_btn.enabled is False
    assert success.stop_btn.enabled is True
    assert success.record_status_label.text() == "正在录制..."
    assert success.duration_timer.started == 1
    assert success.bag_size_timer.started == 1
    assert success.refreshed_size is False
    assert success.remote_refresh_calls == [False]
    assert success.logs == ["[录制] 本地工具可关闭，远端录制会继续运行；重新打开后可刷新并接管。"]


def test_bag_recording_finished_returns_accept_result(monkeypatch):
    monkeypatch.setattr(QMessageBox, "warning", lambda *args, **kwargs: None)

    def fail_question(*args, **kwargs):
        raise AssertionError("record completion should not prompt for transfer")

    monkeypatch.setattr(QMessageBox, "question", fail_question)

    success = _FakeRecordStartStopPage()
    success.is_recording = True
    success.stop_requested = True

    assert BagPage._recording_finished(success, True, "", request_id=4) is True
    assert success.stop_requested is False
    assert success.is_starting_recording is False
    assert success.is_recording is False
    assert success.current_record_finished_at is not None
    assert success.current_record_duration_seconds is not None
    assert success.duration_timer.stopped == 1
    assert success.bag_size_timer.stopped == 1
    assert success.start_btn.enabled is True
    assert success.stop_btn.enabled is False
    assert success.resume_updates == 1
    assert success.duration_label.text() == "00:00:00"
    assert success.record_status_label.text() == "录制完成，待手动回传"
    assert success.logs == ["✓ 录制完成"]
    assert success.pull_calls == []
    assert success.remote_refresh_calls == [False]

    checked = _FakeRecordStartStopPage()

    assert BagPage._recording_finished(checked, True, "话题完整，2/2 个目标Topic均有数据", request_id=4) is True
    assert checked.record_status_label.text() == "录制完成，待手动回传"
    assert checked.remote_refresh_calls == [False]

    auto_pull = _FakeRecordStartStopPage()
    auto_pull.auto_pull_after_record = _FakeCheckBox(True)

    assert BagPage._recording_finished(auto_pull, True, "", request_id=4) is True
    assert auto_pull.pull_calls == [False]
    assert auto_pull.record_status_label.text() == "录制完成，自动回传中"
    assert auto_pull.remote_refresh_calls == [False]

    failed = _FakeRecordStartStopPage()
    failed.is_recording = True
    failed.stop_requested = True

    assert BagPage._recording_finished(failed, False, "stop failed", request_id=4) is True
    assert failed.stop_requested is False
    assert failed.is_recording is False
    assert failed.record_status_label.text() == "录制异常"
    assert failed.current_record_finished_at is None
    assert failed.current_record_duration_seconds is None
    assert failed.logs == ["⚠ 录制任务异常: stop failed"]


def test_bag_page_ignores_stale_record_start_and_stop_callbacks():
    page = _FakeRecordPage()

    assert BagPage._record_start_finished(page, True, "", request_id=1) is False
    assert BagPage._recording_finished(page, True, "", request_id=3) is False

    assert page.is_starting_recording is True
    assert page.is_recording is True
    assert page.stop_requested is True


def test_record_context_and_info_cover_new_and_resumed_recordings():
    profile = get_product("xg2_s100")
    started_at = datetime(2026, 5, 25, 9, 30, 1)
    finished_at = datetime(2026, 5, 25, 9, 31, 1)
    paths = ["/tmp/a"]
    topics = ["/cmd_vel"]
    themes = ["导航"]

    context = bag_helpers.record_context(paths, "nxl2", "sqlite3", 8, profile=profile, topics=topics, themes=themes, started_at=started_at)
    paths.append("/tmp/b")
    topics.append("/odom")
    themes.append("定位")

    assert context["paths"] == ["/tmp/a"]
    assert context["profile"] is profile
    assert context["topics"] == ["/cmd_vel"]
    assert bag_helpers.empty_record_context()["paths"] == []
    assert bag_helpers.empty_record_context()["profile"] is None

    resumed = bag_helpers.record_info(
        profile,
        "nxl2",
        ["/opt/data/rosbag2_l2_20260525_093001"],
        "nxl2",
        [],
        [],
        None,
        None,
        None,
        "",
        "sqlite3",
        0,
        4,
        now=datetime(2026, 5, 25, 10, 0, 0),
    )
    fresh = bag_helpers.record_info(
        profile,
        "nxl2",
        ["/opt/data/custom"],
        "nxl2",
        ["导航"],
        ["/cmd_vel"],
        started_at,
        finished_at,
        60,
        "sqlite3",
        "mcap",
        8,
        4,
    )

    assert resumed["dataset_name"] == "L2_20260525_093001"
    assert resumed["storage"] == "sqlite3"
    assert resumed["cache_gb"] == 4
    assert bag_helpers.record_info(
        profile,
        "nxl2",
        ["/opt/data/rosbag2_l2_20260525_093001"],
        "nxl2",
        [],
        [],
        datetime(2026, 5, 25, 9, 30, 1),
        None,
        None,
        "",
        "sqlite3",
        0,
        4,
    )["dataset_name"] == "L2_20260525_093001"
    assert fresh["started_at"] == "2026-05-25 09:30:01"
    assert fresh["finished_at"] == "2026-05-25 09:31:01"
    assert fresh["topics"] == ["/cmd_vel"]
