from pathlib import Path

from dog_remote_tool.ui import main_window
from dog_remote_tool.ui import main_window_layout
from dog_remote_tool.ui import main_window_logs
from dog_remote_tool.ui import main_window_pages
from dog_remote_tool.ui import main_window_profiles
from dog_remote_tool.ui import main_window_restart
from dog_remote_tool.ui.main_window import MainWindow
from dog_remote_tool.ui.components import ProductSelector
from dog_remote_tool.ui.page_registry import PageSpec
from dog_remote_tool.core.profiles import PRODUCTS


class _SavedPageSettings:
    def __init__(self, values):
        self.values = values

    def value(self, key, default=None, type=None):
        value = self.values.get(key, default)
        return type(value) if type is not None and value is not None else value


class _SavedPageNavItem:
    def __init__(self, text):
        self._text = text

    def text(self):
        return self._text


class _SavedPageNav:
    def __init__(self, titles):
        self.items = [_SavedPageNavItem(title) for title in titles]

    def count(self):
        return len(self.items)

    def item(self, index):
        return self.items[index]


def test_mapping_finish_save_does_not_block_tool_restart_prompt():
    window = MainWindow.__new__(MainWindow)
    window._active_task_titles = lambda: ["结束并保存建图"]

    assert window._restart_blocking_task_titles() == []


def test_removed_legacy_saved_page_falls_back_to_dashboard():
    window = MainWindow.__new__(MainWindow)
    removed_page_title = "终" + "端"
    window.settings = _SavedPageSettings(
        {
            "main_window/current_page_title": removed_page_title,
            "main_window/current_page_index": 7,
        }
    )
    window.nav = _SavedPageNav(["总览", "录包", "遥控", "建图", "导航", "文件管理", "远程访问", "OTA", "诊断"])

    assert MainWindow._saved_page_index(window) == 0


def test_fullscreen_log_labels_use_detail_log_not_advanced_log():
    source = Path(main_window_logs.__file__).read_text(encoding="utf-8")

    assert "详细日志" in source
    assert "高级" + "日志" not in source


def test_restart_tool_uses_apprun_when_source_launcher_is_missing(tmp_path, monkeypatch):
    calls = []
    warnings = []

    class _Button:
        def setEnabled(self, value):
            self.enabled = value

        def setText(self, value):
            self.text = value

    window = MainWindow.__new__(MainWindow)
    window.app_root = tmp_path
    window.restart_tool_btn = _Button()
    window._confirm_restart_when_busy = lambda: True
    window._append_log = lambda message: calls.append(("log", message))
    window.close = lambda: calls.append(("close", None))
    (tmp_path / "AppRun").write_text("#!/usr/bin/env bash\n", encoding="utf-8")

    monkeypatch.setattr(main_window_restart.os, "getpid", lambda: 12345)
    monkeypatch.setattr(main_window_restart.QProcess, "startDetached", lambda program, args: calls.append((program, args)) or True)
    monkeypatch.setattr(main_window_restart.QTimer, "singleShot", lambda _ms, callback: calls.append(("timer", callback)))
    monkeypatch.setattr(main_window_restart.QMessageBox, "warning", lambda *args: warnings.append(args))

    MainWindow.restart_tool(window)

    assert warnings == []
    assert calls[0][0] == "bash"
    assert "exec " + str(tmp_path / "AppRun") in calls[0][1][1]
    assert "启动.sh" not in calls[0][1][1]
    assert window.restart_tool_btn.enabled is False
    assert window.restart_tool_btn.text == "重启中..."


def test_other_active_tasks_still_block_tool_restart_prompt():
    window = MainWindow.__new__(MainWindow)
    window._active_task_titles = lambda: ["结束并保存建图", "删除地图"]

    assert window._restart_blocking_task_titles() == ["删除地图"]


class _FakeDeviceBar:
    selector = ProductSelector

    def __init__(self, profile=None):
        self.profile = profile
        self.connection_tests = 0
        self.battery_refreshes = 0
        self.charging_hint_clears = 0
        self.charging_hint_marks = 0
        self.switched_keys = []
        self.disabled_platform_keys = set()

    def test_connection(self, manual=True):
        self.connection_tests += 1

    def refresh_battery(self, **kwargs):
        self.battery_refreshes += 1
        self.last_battery_refresh_kwargs = kwargs

    def clear_battery_charging_hint(self):
        self.charging_hint_clears += 1
        return True

    def mark_battery_charging_hint(self):
        self.charging_hint_marks += 1
        return True

    def current_profile(self):
        return self.profile

    def switch_profile_key(self, key):
        self.switched_keys.append(key)
        self.profile = PRODUCTS[key]
        return True

    def set_disabled_platform_keys(self, platform_keys):
        self.disabled_platform_keys = set(platform_keys)


class _FakeNav:
    def __init__(self, row):
        self.row = row

    def currentRow(self):
        return self.row


class _FakeStack:
    def __init__(self, count):
        self._count = count

    def count(self):
        return self._count


class _FakeSettings:
    def __init__(self):
        self.values = {}

    def setValue(self, key, value):
        self.values[key] = value


class _FakePage:
    def __init__(self):
        self.deactivated_to = None
        self.activated = 0

    def deactivate_page(self, next_page_title=""):
        self.deactivated_to = next_page_title

    def activate_page(self):
        self.activated += 1


class _LegacyFakePage:
    def __init__(self):
        self.deactivated = 0

    def deactivate_page(self):
        self.deactivated += 1


class _FakeControlPage(_FakePage):
    def __init__(self, running=True):
        super().__init__()
        self.running = running

    def keyboard_stream_running(self):
        return self.running

    def deactivate_page(self, next_page_title=""):
        super().deactivate_page(next_page_title=next_page_title)
        self.running = False


def test_page_changed_passes_next_page_title_to_deactivate():
    old_page = _FakePage()
    new_page = _FakePage()
    window = MainWindow.__new__(MainWindow)
    window._active_page_index = 0
    window._loaded_pages = {0: old_page, 1: new_page}
    window.page_specs = [PageSpec("遥控", lambda: None), PageSpec("建图", lambda: None)]
    window.stack = _FakeStack(2)
    window.settings = _FakeSettings()

    MainWindow._page_changed(window, 1)

    assert old_page.deactivated_to == "建图"
    assert new_page.activated == 1
    assert window.settings.values["main_window/current_page_title"] == "建图"


def test_page_changed_stops_control_remote_when_leaving_bag_for_other_page():
    control_page = _FakeControlPage(running=True)
    bag_page = _FakePage()
    file_page = _FakePage()
    window = MainWindow.__new__(MainWindow)
    window._active_page_index = 1
    window._loaded_pages = {0: control_page, 1: bag_page, 2: file_page}
    window.page_specs = [
        PageSpec("遥控", lambda: None),
        PageSpec("录包", lambda: None),
        PageSpec("文件管理", lambda: None),
    ]
    window.stack = _FakeStack(3)
    window.settings = _FakeSettings()

    MainWindow._page_changed(window, 2)

    assert bag_page.deactivated_to == "文件管理"
    assert control_page.deactivated_to == "文件管理"
    assert control_page.running is False
    assert file_page.activated == 1


def test_page_changed_keeps_control_remote_between_control_and_bag():
    control_page = _FakeControlPage(running=True)
    bag_page = _FakePage()
    window = MainWindow.__new__(MainWindow)
    window._active_page_index = 1
    window._loaded_pages = {0: control_page, 1: bag_page}
    window.page_specs = [
        PageSpec("遥控", lambda: None),
        PageSpec("录包", lambda: None),
    ]
    window.stack = _FakeStack(2)
    window.settings = _FakeSettings()

    MainWindow._page_changed(window, 0)

    assert control_page.deactivated_to is None
    assert control_page.running is True
    assert control_page.activated == 1


def test_page_changed_keeps_control_remote_between_bag_and_mapping():
    control_page = _FakeControlPage(running=True)
    bag_page = _FakePage()
    mapping_page = _FakePage()
    window = MainWindow.__new__(MainWindow)
    window._active_page_index = 1
    window._loaded_pages = {0: control_page, 1: bag_page, 2: mapping_page}
    window.page_specs = [
        PageSpec("遥控", lambda: None),
        PageSpec("录包", lambda: None),
        PageSpec("建图", lambda: None),
    ]
    window.stack = _FakeStack(3)
    window.settings = _FakeSettings()

    MainWindow._page_changed(window, 2)

    assert bag_page.deactivated_to == "建图"
    assert control_page.deactivated_to is None
    assert control_page.running is True
    assert mapping_page.activated == 1


def test_page_changed_keeps_legacy_deactivate_signature_supported():
    old_page = _LegacyFakePage()
    window = MainWindow.__new__(MainWindow)
    window._active_page_index = 0
    window._loaded_pages = {0: old_page}
    window.page_specs = [PageSpec("遥控", lambda: None), PageSpec("建图", lambda: None)]
    window.stack = _FakeStack(2)
    window.settings = _FakeSettings()

    MainWindow._page_changed(window, 1)

    assert old_page.deactivated == 1


def test_runner_finished_does_not_schedule_connection_probe_when_closing(monkeypatch):
    scheduled = []
    monkeypatch.setattr(main_window.QTimer, "singleShot", lambda delay, callback: scheduled.append((delay, callback)))
    window = MainWindow.__new__(MainWindow)
    window._closing = True
    window.device_bar = _FakeDeviceBar()

    MainWindow._runner_finished(window, 0)

    assert scheduled == []
    assert window.device_bar.connection_tests == 0


def test_runner_finished_does_not_schedule_connection_probe(monkeypatch):
    scheduled = []
    monkeypatch.setattr(main_window.QTimer, "singleShot", lambda delay, callback: scheduled.append((delay, callback)))
    window = MainWindow.__new__(MainWindow)
    window._closing = False
    window.device_bar = _FakeDeviceBar()

    MainWindow._runner_finished(window, 0)

    assert scheduled == []
    assert window.device_bar.connection_tests == 0


def test_arc_undock_finish_clears_battery_hint_and_refreshes(monkeypatch):
    scheduled = []
    monkeypatch.setattr(main_window.QTimer, "singleShot", lambda delay, callback: scheduled.append((delay, callback)))
    window = MainWindow.__new__(MainWindow)
    window._closing = False
    window.device_bar = _FakeDeviceBar()

    MainWindow._runner_task_finished_detail(window, 3, 0, "执行：ARC 出桩")

    assert window.device_bar.charging_hint_clears == 1
    assert [delay for delay, _callback in scheduled] == [300, 3000, 8000]
    for _delay, callback in scheduled:
        callback()
    assert window.device_bar.battery_refreshes == 3
    assert window.device_bar.last_battery_refresh_kwargs == {"force": True}


def test_arc_recharge_finish_forces_repeated_battery_refresh(monkeypatch):
    scheduled = []
    monkeypatch.setattr(main_window.QTimer, "singleShot", lambda delay, callback: scheduled.append((delay, callback)))
    window = MainWindow.__new__(MainWindow)
    window._closing = False
    window.device_bar = _FakeDeviceBar()

    MainWindow._runner_task_finished_detail(window, 5, 0, "执行：ARC 回充")

    assert window.device_bar.charging_hint_clears == 0
    assert window.device_bar.charging_hint_marks == 1
    assert [delay for delay, _callback in scheduled] == [300, 3000, 8000]
    for _delay, callback in scheduled:
        callback()
    assert window.device_bar.battery_refreshes == 3
    assert window.device_bar.last_battery_refresh_kwargs == {"force": True}


def test_arc_mapped_recharge_finish_marks_charging_hint(monkeypatch):
    scheduled = []
    monkeypatch.setattr(main_window.QTimer, "singleShot", lambda delay, callback: scheduled.append((delay, callback)))
    window = MainWindow.__new__(MainWindow)
    window._closing = False
    window.device_bar = _FakeDeviceBar()

    MainWindow._runner_task_finished_detail(window, 6, 0, "执行：ARC 有图回充")

    assert window.device_bar.charging_hint_marks == 1
    assert [delay for delay, _callback in scheduled] == [300, 3000, 8000]


def test_non_arc_task_finish_does_not_refresh_battery(monkeypatch):
    scheduled = []
    monkeypatch.setattr(main_window.QTimer, "singleShot", lambda delay, callback: scheduled.append((delay, callback)))
    window = MainWindow.__new__(MainWindow)
    window._closing = False
    window.device_bar = _FakeDeviceBar()

    MainWindow._runner_task_finished_detail(window, 4, 0, "执行：读取状态")

    assert scheduled == []
    assert window.device_bar.charging_hint_clears == 0
    assert window.device_bar.battery_refreshes == 0


def test_video_prepare_finish_does_not_show_success_toast(monkeypatch):
    scheduled = []
    toasts = []
    monkeypatch.setattr(main_window.QTimer, "singleShot", lambda delay, callback: scheduled.append((delay, callback)))
    window = MainWindow.__new__(MainWindow)
    window._closing = False
    window.device_bar = _FakeDeviceBar()
    window._show_task_toast = lambda *args, **kwargs: toasts.append((args, kwargs))

    MainWindow._runner_task_finished_detail(window, 8, 0, "准备视频")

    assert toasts == []
    assert scheduled == []


def test_mapping_save_interrupted_finish_shows_success_toast(monkeypatch):
    scheduled = []
    toasts = []
    monkeypatch.setattr(main_window.QTimer, "singleShot", lambda delay, callback: scheduled.append((delay, callback)))
    window = MainWindow.__new__(MainWindow)
    window._closing = False
    window.device_bar = _FakeDeviceBar()
    window._show_task_toast = lambda *args, **kwargs: toasts.append((args, kwargs))

    MainWindow._runner_task_finished_detail(window, 9, 143, "结束并保存建图")

    assert toasts == [(("保存完成", "建图保存已提交，正在刷新状态和历史地图。", "success"), {})]
    assert scheduled == []


def test_video_prepare_start_does_not_show_running_toast():
    toasts = []
    window = MainWindow.__new__(MainWindow)
    window._closing = False
    window._show_task_toast = lambda *args, **kwargs: toasts.append((args, kwargs))

    MainWindow._runner_task_started(window, 8, "准备视频")

    assert toasts == []


def test_capability_page_switches_xg_l1_3588_to_xg_l1_nx():
    window = MainWindow.__new__(MainWindow)
    window.device_bar = _FakeDeviceBar(PRODUCTS["xg3588"])
    window._append_log = lambda text: None
    window.page_specs = [PageSpec("建图", lambda: None, "mapping")]

    changed = MainWindow._ensure_page_profile(window, 0)

    assert changed is True
    assert window.device_bar.switched_keys == ["xg1_nx"]


def test_capability_page_switches_xg_l2_3588_to_s100():
    window = MainWindow.__new__(MainWindow)
    window.device_bar = _FakeDeviceBar(PRODUCTS["xg2_3588"])
    window._append_log = lambda text: None
    window.page_specs = [PageSpec("路网", lambda: None, "navigation")]

    changed = MainWindow._ensure_page_profile(window, 0)

    assert changed is True
    assert window.device_bar.switched_keys == ["xg2_s100"]


def test_capability_page_keeps_supported_profile():
    window = MainWindow.__new__(MainWindow)
    window.device_bar = _FakeDeviceBar(PRODUCTS["zg_lidar_nx"])
    window._append_log = lambda text: None
    window.page_specs = [PageSpec("导航", lambda: None, "navigation")]

    changed = MainWindow._ensure_page_profile(window, 0)

    assert changed is False
    assert window.device_bar.switched_keys == []


def test_capability_page_greys_unsupported_rk3588_platform():
    window = MainWindow.__new__(MainWindow)
    window.device_bar = _FakeDeviceBar(PRODUCTS["xg1_nx"])
    window.page_specs = [PageSpec("建图", lambda: None, "mapping")]

    MainWindow._apply_page_platform_restrictions(window, 0)

    assert window.device_bar.disabled_platform_keys == {"rk3588"}


def test_normal_page_restores_rk3588_platform():
    window = MainWindow.__new__(MainWindow)
    window.device_bar = _FakeDeviceBar(PRODUCTS["xg1_nx"])
    window.device_bar.disabled_platform_keys = {"rk3588"}
    window.page_specs = [PageSpec("总览", lambda: None)]

    MainWindow._apply_page_platform_restrictions(window, 0)

    assert window.device_bar.disabled_platform_keys == set()
