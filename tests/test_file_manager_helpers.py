from dog_remote_tool.modules import file_manager
import json
from dog_remote_tool.core.shell import CommandSpec
from dog_remote_tool.ui.pages.file_manager import drag_drop as file_manager_drag_drop
from dog_remote_tool.ui.pages.file_manager import favorites as file_manager_favorites
from dog_remote_tool.ui.pages.file_manager import browser as file_manager_browser
from dog_remote_tool.ui.pages.file_manager import actions as file_manager_actions
from dog_remote_tool.ui.pages.file_manager import clipboard as file_manager_clipboard
from dog_remote_tool.ui.pages.file_manager import dialogs as file_manager_dialogs
from dog_remote_tool.ui.pages.file_manager import helpers as file_manager_helpers
from dog_remote_tool.ui.pages.file_manager import icon_view as file_manager_icon_view
from dog_remote_tool.ui.pages.file_manager import icon_delegate as file_manager_icon_delegate
from dog_remote_tool.ui.pages.file_manager import layout as file_manager_layout
from dog_remote_tool.ui.pages.file_manager import operation_edit as file_manager_operation_edit
from dog_remote_tool.ui.pages.file_manager import operation_navigation as file_manager_operation_navigation
from dog_remote_tool.ui.pages.file_manager import operation_preview as file_manager_operation_preview
from dog_remote_tool.ui.pages.file_manager import operation_selection as file_manager_operation_selection
from dog_remote_tool.ui.pages.file_manager import operation_transfer as file_manager_operation_transfer
from dog_remote_tool.ui.pages.file_manager import operations as file_manager_operations
from dog_remote_tool.ui.pages.file_manager import page as file_manager_page
from dog_remote_tool.ui.pages.file_manager import tree_view as file_manager_tree_view
from dog_remote_tool.ui.pages.file_manager import upload_dialog as file_manager_upload_dialog
from dog_remote_tool.ui.pages.file_manager import view_drop as file_manager_view_drop
from dog_remote_tool.ui.pages.file_manager import view_helpers as file_manager_view_helpers
from dog_remote_tool.ui.pages.file_manager import view_models as file_manager_view_models
from dog_remote_tool.ui.pages.file_manager.page import FileManagerPage
from helpers import FakeSignal as _FakeSignal, FakeRunner as _FakeRunner


class _FakeDropUrl:
    def __init__(self, path: str = "", *, local: bool = True):
        self.path = path
        self.local = local

    def isLocalFile(self):
        return self.local

    def toLocalFile(self):
        return self.path


class _FakeDropMime:
    def __init__(self, urls):
        self._urls = urls

    def hasUrls(self):
        return bool(self._urls)

    def urls(self):
        return self._urls


class _FakeDropEvent:
    def __init__(self, urls):
        self._mime = _FakeDropMime(urls)
        self.accepted = 0
        self.ignored = 0

    def mimeData(self):
        return self._mime

    def acceptProposedAction(self):
        self.accepted += 1

    def ignore(self):
        self.ignored += 1


def _item(name: str, kind: str = "file", path: str | None = None) -> file_manager.RemoteFileItem:
    return file_manager.RemoteFileItem(
        name=name,
        path=path or f"/home/robot/{name}",
        kind=kind,
        size=1024,
        mtime=0,
        mode="-rw-r--r--",
        owner="robot",
        group="robot",
    )


def test_file_manager_drag_drop_helpers_accept_local_paths():
    event = _FakeDropEvent([_FakeDropUrl("/tmp/a.txt"), _FakeDropUrl("", local=True), _FakeDropUrl("http://x", local=False)])

    assert file_manager_drag_drop.event_has_local_paths(event) is True
    assert file_manager_drag_drop.local_paths_from_event(event) == ["/tmp/a.txt"]

    file_manager_drag_drop.accept_local_paths_or_ignore(event)

    assert event.accepted == 1
    assert event.ignored == 0

    empty = _FakeDropEvent([])

    assert file_manager_drag_drop.event_has_local_paths(empty) is False

    file_manager_drag_drop.accept_local_paths_or_ignore(empty)

    assert empty.accepted == 0
    assert empty.ignored == 1


def test_file_manager_view_item_helpers_share_model_lookup_logic():
    items = [_item("a.txt"), _item("b.txt")]
    replacement = _item("b.txt", path=items[1].path)
    missing = _item("missing.txt", path="/missing")

    assert file_manager_view_helpers.item_at(items, 0) == items[0]
    assert file_manager_view_helpers.item_at(items, -1) is None
    assert file_manager_view_helpers.item_at(items, 2) is None
    assert file_manager_view_helpers.row_for_path(items, items[1].path) == 1
    assert file_manager_view_helpers.row_for_path(items, "/missing") == -1
    assert file_manager_view_helpers.replace_item_by_path(items, replacement) == 1
    assert items[1] == replacement
    assert file_manager_view_helpers.replace_item_by_path(items, missing) == -1
    assert missing not in items


def test_file_manager_delete_whitelist_uses_ota_map_path_not_old_robot_path():
    assert file_manager.validate_delete_path("/ota/alg_data/map/history_map/a") == "/ota/alg_data/map/history_map/a"

    try:
        file_manager.validate_delete_path("/opt/data/.robot/map/history_map/a")
    except ValueError as exc:
        assert "未授权路径" in str(exc)
    else:
        raise AssertionError("old .robot map path should not be delete-whitelisted")


def test_file_manager_icon_helper_reuses_kind_cache(monkeypatch):
    class FakeStyle:
        def __init__(self):
            self.calls = []

        def standardIcon(self, icon_kind):
            icon = object()
            self.calls.append((icon_kind, icon))
            return icon

    style = FakeStyle()
    monkeypatch.setattr(file_manager_view_helpers.QApplication, "style", lambda: style)
    cache = {}

    dir_icon = file_manager_view_helpers.icon_for_item_kind("dir", cache)
    same_dir_icon = file_manager_view_helpers.icon_for_item_kind("dir", cache)
    file_icon = file_manager_view_helpers.icon_for_item_kind("file", cache)

    assert dir_icon is same_dir_icon
    assert cache["dir"] is dir_icon
    assert cache["file"] is file_icon
    assert len(style.calls) == 2


def test_file_manager_helper_scenario_for_page_state():
    items = [_item("a.txt"), _item(".hidden"), _item("maps", "dir")]

    assert file_manager_helpers.visible_items(items, False, 2) == [_item("a.txt"), _item("maps", "dir")]
    assert file_manager_helpers.visible_items([_item(".hidden"), _item("a"), _item("b"), _item("c")], False, 2) == [
        _item("a"),
        _item("b"),
    ]
    assert file_manager_helpers.visible_counts(items, False, 1) == (1, 1, 1)
    assert file_manager_helpers.visible_counts(items, True, 2) == (2, 0, 1)
    assert file_manager_helpers.selected_detail_text(items[:2]) == "已选择 2 项，目录 0 个，文件 2 个"
    assert file_manager_helpers.is_under_home("/home/robot/log/a.txt", "/home/robot")
    assert not file_manager_helpers.is_under_home("/opt/robot", "/home/robot")
    assert file_manager_helpers.transfer_progress_percent("file 8%\nsummary 101%") == 100
    assert file_manager_helpers.overwrite_confirm_message("上传", ["a", "b"]) == "上传目标已存在：a、b\n是否覆盖？"
    assert file_manager_helpers.breadcrumb_segments("/home/robot/a/b/c/d/e/f", "/home/robot") == (
        True,
        [
            ("b", "/home/robot/a/b"),
            ("c", "/home/robot/a/b/c"),
            ("d", "/home/robot/a/b/c/d"),
            ("e", "/home/robot/a/b/c/d/e"),
            ("f", "/home/robot/a/b/c/d/e/f"),
        ],
    )


def test_file_manager_favorites_merge_defaults_and_user_paths():
    favorites = file_manager_helpers.stored_favorites(
        "xg3588",
        "/home/firefly",
        '["logs", "/tmp", "/custom"]',
    )

    assert favorites[0] == "/home/firefly"
    assert "/home/firefly/logs" in favorites
    assert favorites.count("/tmp") == 1
    assert "/custom" in favorites


def test_s100_file_manager_favorites_use_runtime_map_path():
    for profile_key in ("xg2_s100", "zg_surround_s100"):
        favorites = file_manager_helpers.default_favorites(profile_key, "/home/robot")

        assert "/ota/alg_data/map" in favorites
        assert "/opt/data/.robot/map" not in favorites


class _FakeLabel:
    def __init__(self):
        self.text = ""

    def setText(self, text):
        self.text = text


class _FakeProgress:
    def __init__(self):
        self.value = None

    def setValue(self, value):
        self.value = value


class _FakeTimer:
    def __init__(self, interval=30_000):
        self._interval = interval
        self.intervals = []
        self.started = False
        self.stopped = False
        self.start_count = 0
        self.stop_count = 0

    def interval(self):
        return self._interval

    def setInterval(self, interval):
        self._interval = interval
        self.intervals.append(interval)

    def start(self):
        self.started = True
        self.start_count += 1

    def stop(self):
        self.stopped = True
        self.stop_count += 1


class _FakePanel:
    def __init__(self):
        self.shown = False
        self.hidden = False

    def show(self):
        self.shown = True

    def hide(self):
        self.hidden = True



class _FakeProcess:
    def __init__(self):
        self.readyReadStandardOutput = _FakeSignal()
        self.finished = _FakeSignal()
        self.started = False

    def start(self):
        self.started = True


class _FakeActionSlot:
    def __init__(self, running=False, read_result=False, output=""):
        self.running = running
        self.start_calls = []
        self.stop_calls = 0
        self.read_result = read_result
        self.read_calls = []
        self.finish_output = output
        self.finish_calls = []
        self.process = _FakeProcess()

    def is_running(self):
        return self.running

    def start_bash(self, command):
        self.start_calls.append(command)
        self.running = True
        return self.process, 12

    def start_spec(self, spec):
        return self.start_bash(spec.command)

    def stop(self):
        self.stop_calls += 1
        self.running = False

    def read_available_output(self, process, request_id):
        self.read_calls.append((process, request_id))
        return self.read_result

    def finish(self, process, request_id):
        self.finish_calls.append((process, request_id))
        self.running = False
        return self.finish_output


class _FakeListSlot(_FakeActionSlot):
    pass



class _FakeFileManagerRunnerPage:
    def __init__(self):
        self.runner_task_title = "剪切粘贴"
        self.runner_task_id = 8
        self.clear_remote_clipboard_on_success = True
        self.remote_clipboard_paths = ["/home/robot/a"]
        self.remote_clipboard_mode = "cut"
        self.transfer_active = True
        self.pending_refresh_after_task = True
        self.status_label = _FakeLabel()
        self.finished_codes = []

    def _finish_transfer_progress(self, code):
        self.finished_codes.append(code)
        self.transfer_active = False


def test_file_manager_runner_finished_ignores_unrelated_task():
    page = _FakeFileManagerRunnerPage()

    FileManagerPage._runner_finished(page, 9, 0, "剪切粘贴")

    assert page.runner_task_title == "剪切粘贴"
    assert page.runner_task_id == 8
    assert page.clear_remote_clipboard_on_success is True
    assert page.remote_clipboard_paths == ["/home/robot/a"]
    assert page.remote_clipboard_mode == "cut"
    assert page.transfer_active is True
    assert page.pending_refresh_after_task is True
    assert page.finished_codes == []


def test_file_manager_runner_finished_handles_matching_task():
    page = _FakeFileManagerRunnerPage()
    page.pending_refresh_after_task = False

    FileManagerPage._runner_finished(page, 8, 0, "剪切粘贴")

    assert page.runner_task_title == ""
    assert page.runner_task_id == 0
    assert page.clear_remote_clipboard_on_success is False
    assert page.remote_clipboard_paths == []
    assert page.remote_clipboard_mode == ""
    assert page.transfer_active is False
    assert page.finished_codes == [0]


class _FakeFileManagerRunPage:
    def __init__(self, task_id=None, conflict=""):
        self.runner = _FakeRunner(conflict=conflict, task_id=task_id)
        self.searching = True
        self.pending_refresh_after_task = True
        self.runner_task_title = "旧任务"
        self.runner_task_id = 88
        self.pending_select_names = {"old-pending"}
        self.status_label = _FakeLabel()
        self.transfer_active = False
        self.transfer_title = ""
        self.transfer_label = _FakeLabel()
        self.transfer_progress = _FakeProgress()
        self.transfer_panel = _FakePanel()
        self.clear_remote_clipboard_on_success = True
        self.action_slot = _FakeActionSlot()
        self.action_callback = None
        self.cancel_action_btn = _FakePanel()
        self.preview_path = ""
        self.preview_dialog = None

    def profile(self):
        return None

    def _run_file_command(self, spec, refresh_after):
        return FileManagerPage._run_file_command(self, spec, refresh_after)


class _FakeNameDialog:
    def __init__(self, *args, **kwargs):
        pass

    def exec_(self):
        return file_manager_page.QDialog.Accepted

    def name(self):
        return "new.txt"


class _FakeUploadDialog:
    def __init__(self, *args, **kwargs):
        pass

    def exec_(self):
        return file_manager_page.QDialog.Accepted

    def paths(self):
        return ["/tmp/upload-a.txt", "/tmp/upload-b.txt"]


class _FakeRejectedUploadDialog(_FakeUploadDialog):
    def exec_(self):
        return file_manager_page.QDialog.Rejected


class _FakeFileManagerCreatePage(FileManagerPage, _FakeFileManagerRunPage):
    def __init__(self, task_id=None):
        _FakeFileManagerRunPage.__init__(self, task_id=task_id)
        self.current_path = "/home/robot"
        self.current_items = [_item("old.txt")]
        self.pending_select_names = set()

    def profile(self):
        return type(
            "Profile",
            (),
            {"home": "/home/robot", "password": "robot", "target": "robot@192.168.1.2", "host": "192.168.1.2"},
        )()


class _FakeFileManagerRefreshPage(FileManagerPage, _FakeFileManagerRunPage):
    def __init__(self, *, list_running=False, runner_running=False, action_running=False):
        _FakeFileManagerRunPage.__init__(self, task_id=None)
        self.page_active = True
        self.runner.running = runner_running
        self.action_slot = _FakeActionSlot(running=action_running)
        self.list_slot = _FakeListSlot(running=list_running)
        self.current_path = "/home/robot/log"
        self.path_updates = []
        self.last_successful_path = "/home/robot/log"
        self.last_error_message = ""
        self.auto_error_repeats = 0
        self.current_items = []
        self.current_signature = ""
        self.populated_items = []
        self.status_items = []

    def profile(self):
        return type(
            "Profile",
            (),
            {"home": "/home/robot", "password": "robot", "target": "robot@192.168.1.2", "host": "192.168.1.2"},
        )()

    def _set_path_edit(self, path):
        self.path_updates.append(path)

    def _read_list_output(self, process, request_id):
        return FileManagerPage._read_list_output(self, process, request_id)

    def _list_finished(self, process, request_id, exit_code, force, reason):
        return FileManagerPage._list_finished(self, process, request_id, exit_code, force, reason)

    def _signature(self, items):
        return "|".join(item.path for item in items)

    def _populate_table(self, items):
        self.populated_items.append(list(items))

    def _set_items_status(self, items):
        self.status_items.append(list(items))


def _list_output(current="/home/robot/log", items=None, error=""):
    payload = {
        "current": current,
        "error": error,
        "items": [
            {
                "name": item.name,
                "path": item.path,
                "kind": item.kind,
                "size": item.size,
                "mtime": item.mtime,
                "mode": item.mode,
                "owner": item.owner,
                "group": item.group,
            }
            for item in (items or [])
        ],
    }
    return "DOG_REMOTE_FILE_BEGIN\n" + json.dumps(payload) + "\nDOG_REMOTE_FILE_END\n"


def test_file_manager_make_file_returns_false_when_runner_rejects_start(monkeypatch):
    page = _FakeFileManagerCreatePage(task_id=None)
    monkeypatch.setattr(file_manager_page, "NameDialog", _FakeNameDialog)

    started = FileManagerPage.make_file(page)

    assert started is False
    assert page.pending_select_names == set()
    assert page.status_label.text == "任务未启动"
    assert len(page.runner.run_calls) == 1


def test_file_manager_upload_paths_returns_false_when_runner_rejects_start(monkeypatch, tmp_path):
    page = _FakeFileManagerCreatePage(task_id=None)
    local_file = tmp_path / "upload.txt"
    local_file.write_text("data", encoding="utf-8")

    started = FileManagerPage.upload_paths(page, [str(local_file)])

    assert started is False
    assert page.pending_select_names == set()
    assert page.status_label.text == "任务未启动"
    assert page.transfer_panel.shown is False
    assert len(page.runner.run_calls) == 1


def test_file_manager_refresh_directory_returns_start_result():
    inactive = _FakeFileManagerRefreshPage()
    inactive.page_active = False

    assert FileManagerPage.refresh_directory(inactive, force=True, reason="任务完成") is False
    assert inactive.list_slot.start_calls == []

    list_busy = _FakeFileManagerRefreshPage(list_running=True)

    assert FileManagerPage.refresh_directory(list_busy, force=True, reason="手动刷新") is False
    assert list_busy.list_slot.start_calls == []

    page = _FakeFileManagerRefreshPage()

    assert FileManagerPage.refresh_directory(page, force=True, reason="手动刷新") is True
    assert page.path_updates == ["/home/robot/log"]
    assert page.status_label.text == "手动刷新"
    assert page.list_slot.process.started is True
    assert len(page.list_slot.start_calls) == 1
    assert "/home/robot/log" in page.list_slot.start_calls[0]


def test_file_manager_activate_page_does_not_repeat_auto_refresh():
    page = _FakeFileManagerRefreshPage()
    page.page_active = False

    FileManagerPage.activate_page(page)

    assert page.page_active is True
    assert page.path_updates == ["/home/robot/log"]
    assert page.status_label.text == "打开页面"
    assert len(page.list_slot.start_calls) == 1

    FileManagerPage.activate_page(page)

    assert page.path_updates == ["/home/robot/log"]
    assert len(page.list_slot.start_calls) == 1


def test_file_manager_shutdown_marks_page_inactive_and_stops_processes():
    page = _FakeFileManagerRefreshPage(list_running=True, action_running=True)

    FileManagerPage.shutdown_processes(page)

    assert page.page_active is False
    assert page.list_slot.stop_calls == 1
    assert page.action_slot.stop_calls == 1
    assert page.action_callback is None
    assert page.cancel_action_btn.hidden is True


def test_file_manager_deactivate_stops_listing_without_cancelling_action():
    page = _FakeFileManagerRefreshPage(list_running=True, action_running=True)

    FileManagerPage.deactivate_page(page)

    assert page.page_active is False
    assert page.list_slot.stop_calls == 1
    assert page.action_slot.stop_calls == 0


def test_file_manager_pick_upload_files_returns_upload_result(monkeypatch):
    page = _FakeFileManagerCreatePage(task_id=None)
    upload_calls = []

    monkeypatch.setattr(file_manager_page, "UploadDialog", _FakeUploadDialog)
    monkeypatch.setattr(FileManagerPage, "upload_paths", lambda _self, paths: upload_calls.append(paths) or False)

    started = FileManagerPage.pick_upload_files(page)

    assert started is False
    assert upload_calls == [["/tmp/upload-a.txt", "/tmp/upload-b.txt"]]


def test_file_manager_pick_upload_files_returns_false_when_dialog_cancelled(monkeypatch):
    page = _FakeFileManagerCreatePage(task_id=None)
    upload_calls = []

    monkeypatch.setattr(file_manager_page, "UploadDialog", _FakeRejectedUploadDialog)
    monkeypatch.setattr(FileManagerPage, "upload_paths", lambda _self, paths: upload_calls.append(paths) or True)

    started = FileManagerPage.pick_upload_files(page)

    assert started is False
    assert upload_calls == []


def test_file_manager_run_file_command_clears_pending_when_runner_rejects_start():
    page = _FakeFileManagerRunPage(task_id=None)
    spec = CommandSpec("删除", "rm -rf /tmp/a", display_command="删除 /tmp/a")

    started = FileManagerPage._run_file_command(page, spec, refresh_after=True)

    assert started is False
    assert page.pending_refresh_after_task is False
    assert page.pending_select_names == set()
    assert page.runner_task_title == ""
    assert page.runner_task_id == 0
    assert page.status_label.text == "任务未启动"
    assert page.searching is True
    assert len(page.runner.run_calls) == 1


def test_file_manager_combined_command_does_not_show_transfer_when_runner_rejects_start():
    page = _FakeFileManagerRunPage(task_id=None)
    specs = [CommandSpec("下载", "rsync -P a b", concurrency="parallel")]

    started = FileManagerPage._run_combined_commands(page, specs, "下载 1 项", refresh_after=False)

    assert started is False
    assert page.pending_refresh_after_task is False
    assert page.pending_select_names == set()
    assert page.runner_task_title == ""
    assert page.runner_task_id == 0
    assert page.status_label.text == "任务未启动"
    assert page.transfer_active is False
    assert page.transfer_title == ""
    assert page.transfer_panel.shown is False
    assert len(page.runner.run_calls) == 1


def test_file_manager_capture_returns_false_when_busy_or_runner_conflict():
    spec = CommandSpec("预览", "cat /tmp/a", display_command="预览 /tmp/a")
    busy_page = _FakeFileManagerRunPage()
    busy_page.action_slot = _FakeActionSlot(running=True)

    assert FileManagerPage._run_capture(busy_page, spec, "预览读取中", lambda *_args: None) is False
    assert busy_page.action_slot.start_calls == []
    assert busy_page.runner.output_lines[-1].startswith("[警告] 文件管理 已有任务运行")

    conflict_page = _FakeFileManagerRunPage(conflict="已有公共任务运行")

    assert FileManagerPage._run_capture(conflict_page, spec, "预览读取中", lambda *_args: None) is False
    assert conflict_page.action_slot.start_calls == []
    assert conflict_page.runner.output_lines[-1] == "[警告] 已有公共任务运行\n"


def test_file_manager_capture_returns_true_when_process_started():
    page = _FakeFileManagerRunPage()
    spec = CommandSpec("预览", "cat /tmp/a", display_command="预览 /tmp/a")
    callback = lambda *_args: None

    started = FileManagerPage._run_capture(page, spec, "预览读取中", callback)

    assert started is True
    assert page.action_callback is callback
    assert page.action_slot.start_calls == ["cat /tmp/a"]
    assert page.action_slot.process.started is True
    assert page.status_label.text == "预览读取中"
    assert page.cancel_action_btn.shown is True
    assert page.runner.output_lines[-1] == "[信息] 文件管理 开始：预览 /tmp/a\n"


def test_file_manager_read_callbacks_return_slot_result():
    page = _FakeFileManagerRefreshPage()
    page.list_slot = _FakeListSlot(read_result=True)
    page.action_slot = _FakeActionSlot(read_result=False)

    assert FileManagerPage._read_list_output(page, page.list_slot.process, request_id=31) is True
    assert page.list_slot.read_calls == [(page.list_slot.process, 31)]

    assert FileManagerPage._read_action_output(page, page.action_slot.process, request_id=32) is False
    assert page.action_slot.read_calls == [(page.action_slot.process, 32)]


def test_file_manager_list_finished_returns_accept_result():
    stale = _FakeFileManagerRefreshPage()
    stale.list_slot = _FakeListSlot(output=None)

    assert FileManagerPage._list_finished(stale, stale.list_slot.process, request_id=35, exit_code=0, force=False, reason="") is False

    item = _item("a.txt")
    success = _FakeFileManagerRefreshPage()
    success.list_slot = _FakeListSlot(output=_list_output(current="/home/robot/log", items=[item]))

    assert FileManagerPage._list_finished(success, success.list_slot.process, request_id=36, exit_code=0, force=False, reason="手动刷新") is True
    assert success.current_path == "/home/robot/log"
    assert success.path_updates == ["/home/robot/log"]
    assert success.last_successful_path == "/home/robot/log"
    assert success.last_error_message == ""
    assert success.auto_error_repeats == 0
    assert success.current_items == [item]
    assert success.current_signature == item.path
    assert success.populated_items == [[item]]
    assert success.status_items == [[item]]

    failed = _FakeFileManagerRefreshPage()
    failed.list_slot = _FakeListSlot(output="ssh failed")

    assert FileManagerPage._list_finished(failed, failed.list_slot.process, request_id=37, exit_code=1, force=False, reason="手动刷新") is True
    assert failed.status_label.text == "读取失败"
    assert failed.current_items == []
    assert failed.current_signature == ""
    assert failed.populated_items == [[]]
    assert failed.runner.output_lines[-1].startswith("[警告] 文件 远端目录读取失败：")


def test_file_manager_action_finished_returns_accept_result():
    stale = _FakeFileManagerRunPage()
    stale.action_slot = _FakeActionSlot(output=None)
    stale.action_callback = lambda *_args: None

    assert FileManagerPage._action_finished(stale, stale.action_slot.process, request_id=33, exit_code=0) is False
    assert callable(stale.action_callback)
    assert stale.cancel_action_btn.hidden is False

    page = _FakeFileManagerRunPage()
    page.action_slot = _FakeActionSlot(output="captured")
    callback_calls = []
    page.action_callback = lambda output, code: callback_calls.append((output, code))

    assert FileManagerPage._action_finished(page, page.action_slot.process, request_id=34, exit_code=7) is True
    assert page.action_callback is None
    assert page.cancel_action_btn.hidden is True
    assert callback_calls == [("captured", 7)]


def test_file_manager_preview_selected_returns_preview_result():
    page = _FakeFileManagerRunPage()
    preview_calls = []

    page.selected_remote_items = lambda: [_item("a.txt")]
    page.preview_item = lambda item: preview_calls.append(item.name) or False

    assert FileManagerPage.preview_selected(page) is False
    assert preview_calls == ["a.txt"]


def test_file_manager_cancel_action_returns_whether_it_stopped_process():
    idle_page = _FakeFileManagerRunPage()
    idle_page.action_slot = _FakeActionSlot(running=False)

    assert FileManagerPage.cancel_action(idle_page) is False
    assert idle_page.action_slot.stop_calls == 0

    running_page = _FakeFileManagerRunPage()
    running_page.action_slot = _FakeActionSlot(running=True)
    running_page.action_callback = lambda *_args: None

    assert FileManagerPage.cancel_action(running_page) is True
    assert running_page.action_callback is None
    assert running_page.action_slot.stop_calls == 1
    assert running_page.status_label.text == "已停止"


def test_file_manager_paste_only_marks_cut_clipboard_clear_after_task_started(monkeypatch):
    page = _FakeFileManagerRunPage(task_id=None)
    page.remote_clipboard_paths = ["/home/robot/a"]
    page.remote_clipboard_mode = "cut"
    page.current_path = "/home/robot/target"

    monkeypatch.setattr(FileManagerPage, "profile", lambda _self: None)
    monkeypatch.setattr(
        file_manager,
        "paste_command",
        lambda *args, **kwargs: CommandSpec("剪切粘贴", "mv /home/robot/a /home/robot/target"),
    )

    started = FileManagerPage.paste_remote_clipboard(page)

    assert started is False
    assert page.clear_remote_clipboard_on_success is False
    assert page.remote_clipboard_paths == ["/home/robot/a"]
    assert page.remote_clipboard_mode == "cut"
    assert page.status_label.text == "任务未启动"
