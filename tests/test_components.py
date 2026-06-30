from PyQt5.QtCore import QCoreApplication, QProcess
from PyQt5.QtWidgets import QMessageBox

from dog_remote_tool.core.profiles import get_product
from dog_remote_tool.core.runner import ProcessRunner
from dog_remote_tool.core.shell import CommandSpec
from dog_remote_tool.modules.device_status import power
from dog_remote_tool.ui import device_bar_battery as device_bar_battery_ui
from dog_remote_tool.ui import command_confirm as command_confirm_ui
from dog_remote_tool.ui import command_page as command_page_ui
from dog_remote_tool.ui import device_bar_connection as device_bar_connection_ui
from dog_remote_tool.ui import device_bar_profile as device_bar_profile_ui
import dog_remote_tool.ui.components as components_ui
from dog_remote_tool.ui import log_panel as log_panel_ui
from dog_remote_tool.ui import product_selector as product_selector_ui
from dog_remote_tool.ui.components import (
    CommandPage,
    DeviceBar,
    LogHighlighter,
    LogPanel,
    ProductSelector,
    command_display_command,
    confirm_dangerous_action,
    confirm_command_spec,
    looks_accidental_stored_profile_value,
)
from helpers import FakeSignal as _FakeSignal, FakeRunner as _FakeRunner
from dog_remote_tool.ui.process_utils import ProcessSlot, append_limited_output


def _app():
    return QCoreApplication.instance() or QCoreApplication([])


def test_stored_profile_value_guard_detects_repeated_defaults():
    assert looks_accidental_stored_profile_value("user", "robot" * 8, "robot") is True
    assert looks_accidental_stored_profile_value("password", "firefly" * 4, "firefly") is True
    assert looks_accidental_stored_profile_value("host", "192.168.168.100" * 2, "192.168.168.100") is True


def test_stored_profile_value_guard_preserves_intentional_custom_values():
    assert looks_accidental_stored_profile_value("user", "robot", "robot") is False
    assert looks_accidental_stored_profile_value("user", "admin", "robot") is False
    assert looks_accidental_stored_profile_value("password", "secret", "1") is False


def test_product_selector_maps_surround_3588_to_body_controller_profile():
    assert ProductSelector.COMBINATIONS[("zg_surround", "rk3588")] == "zg_surround_3588"
    profile = get_product("zg_surround_3588")
    assert profile.label == "中狗环视版 3588"
    assert profile.host == "192.168.234.1"
    assert profile.user == "robot"
    assert profile.password == "bot"


def test_battery_indicator_stylesheet_uses_percent_fill_stop():
    style = device_bar_battery_ui.battery_indicator_stylesheet(40)

    assert "qlineargradient" in style
    assert "stop:0.400" in style
    assert "stop:0.401" in style
    assert "border-radius:8px" in style


def test_battery_indicator_stylesheet_handles_unknown_and_charging():
    unknown = device_bar_battery_ui.battery_indicator_stylesheet(None)
    charging = device_bar_battery_ui.battery_indicator_stylesheet(64, True)

    assert "stop:0.000" in unknown
    assert "#46566b" in unknown
    assert "stop:0.640" in charging
    assert "#075985" in charging


def test_battery_command_runs_parallel():
    spec = power.battery_command(get_product("zg_lidar_nx"))

    assert spec.concurrency == "parallel"
    assert spec.locks == ("device-battery",)
    assert "robot_remote.stdout" in spec.command
    assert "mcu_upgrade" not in spec.command


def test_device_bar_battery_refresh_interval_is_two_minutes():
    assert components_ui.BATTERY_REFRESH_INTERVAL_MS == 120_000


def test_xg_battery_command_keeps_shared_memory_fast_path():
    spec = power.battery_command(get_product("xg1_nx"))

    assert "/dev/shm/bms_shm" in spec.command
    assert "robot_remote.stdout" not in spec.command


def test_log_panel_normalizes_visible_log_prefixes():
    text = "$ 执行状态\n[INFO] 已连接\n[WARN] 网络较慢\n[ERROR] 读取失败\n[任务 2] [INFO] 并行输出\n"

    cleaned = LogPanel.clean_text(text)

    assert cleaned == "[命令] 执行状态\n[信息] 已连接\n[警告] 网络较慢\n[错误] 读取失败\n[任务 2] [信息] 并行输出\n"


def test_log_panel_inserts_missing_line_break_between_log_records():
    text = "[INFO] 读取状态[ERROR] SSH 认证失败[任务 2] [WARN] 自动重试"

    cleaned = LogPanel.clean_text(text)

    assert cleaned == "[信息] 读取状态\n[错误] SSH 认证失败\n[任务 2] [警告] 自动重试"


def test_log_panel_hides_mapping_machine_status_lines():
    text = (
        "[INFO] 建图状态：建图中（MappingRunning）\n"
        "ALG_MAPPING_STATUS=MappingRunning\n"
        "ALG_MAPPING_SOURCE=app\n"
        "[INFO] 建图已开始，请移动机器人采集环境。\n"
    )

    cleaned = LogPanel.clean_text(text)

    assert cleaned == "[信息] 建图状态：建图中\n[信息] 建图已开始，请移动机器人采集环境。\n"


def test_log_panel_hides_successful_app_ws_mapping_chatter():
    text = (
        "[INFO] 已发送开始建图: start_mapping data=1\n"
        "[INFO] 响应: func=start_mapping status=ok data=None error=None\n"
        "[INFO] 建图已开始，请移动机器人采集环境。\n"
        "[ERROR] 响应: func=stop_mapping status=error data=None error=busy\n"
    )

    cleaned = LogPanel.clean_text(text)

    assert cleaned == (
        "[信息] 建图已开始，请移动机器人采集环境。\n"
        "[错误] 响应: func=stop_mapping status=error data=None error=busy\n"
    )


def test_log_panel_hides_generic_machine_assignment_lines():
    text = (
        "[INFO] 导航状态已刷新\n"
        "NAV_STATE=2\n"
        "[任务 2] NAV_TASK_STATUS=1\n"
        "LOCALIZATION_READY=1\n"
        "MAP_PCD=/ota/alg_data/map/history_map/a/map.pcd\n"
        "[WARN] 地图未初始化\n"
    )

    cleaned = LogPanel.clean_text(text)

    assert cleaned == "[信息] 导航状态已刷新\n[警告] 地图未初始化\n"


def test_log_panel_technical_mode_keeps_machine_lines_and_redacts_secrets():
    text = (
        "$ sshpass -p secret ssh robot@192.168.1.2\n"
        "NAV_STATE=2\n"
        "S100_REMOTE_PASSWORD=wireless-secret\n"
        "[WARN] 地图未初始化\n"
    )

    cleaned = LogPanel.clean_text(text, mode="technical")

    assert "[命令] sshpass -p <已隐藏> ssh robot@192.168.1.2\n" in cleaned
    assert "NAV_STATE=2\n" in cleaned
    assert "S100_REMOTE_PASSWORD=<已隐藏>\n" in cleaned
    assert "secret" not in cleaned
    assert "wireless-secret" not in cleaned
    assert "[警告] 地图未初始化\n" in cleaned


def test_log_panel_user_mode_summarizes_rtsp_and_local_paths():
    text = (
        "[视频] RTSP 已连接(GStreamer low-latency): rtsp://192.168.234.1:8554/front\n"
        "[任务 1] [RTSP] 准备远端媒体服务: rtsp://192.168.234.1:8554/front\n"
        "[任务 1] [RTSP] 远端 127.0.0.1:8554 已响应\n"
        "[任务 1] [RTSP] 远端路径 /front: RTSP/1.0 200 OK\n"
        "[任务 1] [RTSP] 本地将直连播放: rtsp://192.168.234.1:8554/front\n"
        "[任务 1] 完成：准备 RTSP 视频: rtsp://192.168.234.1:8554/front\n"
        "[信息] 运行目录 /home/user/测试工具/dog_remote_tool/src/dog_remote_tool\n"
    )

    cleaned = LogPanel.clean_text(text)

    assert "[视频] 视频已连接。\n" in cleaned
    assert "正在准备视频服务" not in cleaned
    assert "[任务 1] 完成：准备视频\n" in cleaned
    assert "rtsp://" not in cleaned
    assert "GStreamer" not in cleaned
    assert "127.0.0.1:8554" not in cleaned
    assert "RTSP/1.0" not in cleaned
    assert "/home/user/测试工具/dog_remote_tool" not in cleaned
    assert "运行目录 工具目录" in cleaned


def test_log_panel_user_mode_summarizes_public_ssh_commands():
    text = (
        "[目标] 公网 SSH: robot@1.2.3.4:22022\n"
        "公网地址: robot@1.2.3.4\n"
        "公网端口: 22022\n"
        "连接命令: ssh robot@1.2.3.4 -p 22022\n"
        "交互命令: ssh robot@1.2.3.4 -p 22022\n"
    )

    cleaned = LogPanel.clean_text(text)

    assert "[目标] 正在测试公网连接。\n" in cleaned
    assert "公网连接信息已生成。\n" in cleaned
    assert "连接信息已生成。\n" in cleaned
    assert "ssh robot@" not in cleaned
    assert "robot@1.2.3.4" not in cleaned


def test_log_panel_technical_mode_keeps_rtsp_and_local_path_details():
    text = (
        "[视频] RTSP 已连接(GStreamer low-latency): rtsp://192.168.234.1:8554/front\n"
        "[任务 1] [RTSP] 远端路径 /front: RTSP/1.0 200 OK\n"
        "[信息] 运行目录 /home/user/测试工具/dog_remote_tool/src/dog_remote_tool\n"
    )

    cleaned = LogPanel.clean_text(text, mode="technical")

    assert "rtsp://192.168.234.1:8554/front" in cleaned
    assert "GStreamer low-latency" in cleaned
    assert "RTSP/1.0 200 OK" in cleaned
    assert "/home/user/测试工具/dog_remote_tool/src/dog_remote_tool" in cleaned


def test_log_highlighter_classifies_new_user_log_labels():
    assert LogHighlighter.classify_line("[命令] 读取状态") == "command"
    assert LogHighlighter.classify_line("[信息] 读取完成") == "info"
    assert LogHighlighter.classify_line("[警告] 网络较慢") == "warn"
    assert LogHighlighter.classify_line("[错误] 读取失败") == "error"
    assert LogHighlighter.classify_line("[任务 3] 完成：读取状态") == "success"
    assert LogHighlighter.classify_line("[任务 3] [错误] 读取失败") == "error"
    assert LogHighlighter.classify_line("[2026-06-02 12:34:56] [信息] 读取完成") == "info"


def test_log_panel_adds_timestamp_to_visible_log_lines():
    stamped, next_line = LogPanel.timestamp_text(
        "\n[信息] 已连接\n[警告] 网络较慢",
        "2026-06-02 12:34:56",
    )

    assert stamped == "\n[2026-06-02 12:34:56] [信息] 已连接\n[2026-06-02 12:34:56] [警告] 网络较慢"
    assert next_line is False



class _FakeCommandPage:
    def __init__(self, task_id=None, autorun_enabled=True):
        self.current_spec = CommandSpec("状态检查", "true")
        self.runner = _FakeRunner(task_id=task_id)
        self.autorun_enabled = autorun_enabled

    def display_command_for_log(self):
        return "执行：状态检查"

    def run_current(self):
        return CommandPage.run_current(self)


class _FakeButton:
    def __init__(self):
        self.enabled = None
        self.text = ""
        self.tooltip = ""

    def setEnabled(self, enabled):
        self.enabled = enabled

    def setText(self, text):
        self.text = text

    def setToolTip(self, tooltip):
        self.tooltip = tooltip


class _FakeStopRunner:
    def __init__(self, *, running=False, stop_locked=False):
        self.running = running
        self.stop_locked = stop_locked

    def is_running(self):
        return self.running


class _FakeStopButtonPage:
    def __init__(self, *, running=False, stop_locked=False):
        self.runner = _FakeStopRunner(running=running, stop_locked=stop_locked)
        self.stop_btn = _FakeButton()


class _FakeReadSlot:
    def __init__(self, result):
        self.result = result
        self.calls = []
        self.process = object()

    def read_available_output(self, process, request_id):
        self.calls.append((process, request_id))
        return self.result


class _FakeFinishSlot:
    def __init__(self, output):
        self.output = output
        self.calls = []
        self.process = object()

    def finish(self, process, request_id):
        self.calls.append((process, request_id))
        return self.output



class _FakeStartedProcess:
    def __init__(self):
        self.readyReadStandardOutput = _FakeSignal()
        self.finished = _FakeSignal()
        self.started = 0

    def start(self):
        self.started += 1


class _FakeStartSlot:
    def __init__(self):
        self.request_id = 41
        self.running = False
        self.start_calls = []
        self.processes = []

    def is_running(self):
        return self.running

    def start_bash(self, command):
        self.start_calls.append(command)
        process = _FakeStartedProcess()
        self.processes.append(process)
        return process, self.request_id

    def start_spec(self, spec, **_kwargs):
        return self.start_bash(spec.command)


class _FakeLabel:
    def __init__(self):
        self.text = ""
        self.styles = []
        self.tooltip = ""

    def setText(self, text):
        self.text = text

    def setStyleSheet(self, style):
        self.styles.append(style)

    def setToolTip(self, tooltip):
        self.tooltip = tooltip


class _FakeEmitSignal:
    def __init__(self):
        self.values = []

    def emit(self, value):
        self.values.append(value)


class _FakeDeviceBarReadPage:
    def __init__(self):
        self.connection_slot = _FakeReadSlot(True)
        self.battery_slot = _FakeReadSlot(False)


class _FakeDeviceBarFinishPage:
    def __init__(self, *, connection_output="", battery_output=""):
        self.connection_slot = _FakeFinishSlot(connection_output)
        self.battery_slot = _FakeFinishSlot(battery_output)
        self.status = _FakeLabel()
        self.battery = _FakeLabel()
        self.connection_changed = _FakeEmitSignal()
        self.battery_retry_count = 2
        self.battery_cache = {}
        self.battery_last_percent = None
        self.battery_last_charging = False
        self.battery_styles = []
        self.battery_shown = []
        self.battery_retries = []

    def current_profile(self):
        return get_product("xg2_s100")

    def _set_battery_style(self, percent, charging=False):
        self.battery_styles.append((percent, charging))

    def _battery_cache_key(self, profile):
        return DeviceBar._battery_cache_key(self, profile)

    def _should_skip_battery_probe(self, profile):
        return DeviceBar._should_skip_battery_probe(self, profile)

    def _show_battery(self, percent, charging=False):
        self.battery_last_percent = percent
        self.battery_last_charging = charging
        self.battery_shown.append((percent, charging))

    def _retry_battery_read(self, request_id):
        self.battery_retries.append(request_id)


class _FakeDeviceBarConnectionProbePage:
    def __init__(self):
        self.connection_slot = _FakeStartSlot()
        self.status = _FakeLabel()
        self.connection_changed = _FakeEmitSignal()
        self.last_auto_connection_probe = 0.0
        self.last_auto_connection_target = ""

    def current_profile(self):
        return get_product("xg2_s100")


class _FakeDeviceBarBatteryRefreshPage:
    def __init__(self):
        self.battery_slot = _FakeStartSlot()
        self.battery = _FakeLabel()
        self.battery_retry_count = 3
        self.last_battery_probe = 0.0
        self.last_battery_probe_target = ""

    def current_profile(self):
        return get_product("xg2_s100")

    def _battery_cache_key(self, profile):
        return DeviceBar._battery_cache_key(self, profile)

    def _should_skip_battery_probe(self, profile):
        return DeviceBar._should_skip_battery_probe(self, profile)


def test_command_page_run_current_reports_runner_start_success():
    page = _FakeCommandPage(task_id=7)

    assert CommandPage.run_current(page) is True
    assert len(page.runner.run_calls) == 1


def test_command_page_run_current_reports_runner_start_rejected():
    page = _FakeCommandPage(task_id=None)

    assert CommandPage.run_current(page) is False
    assert len(page.runner.run_calls) == 1


def test_command_page_set_command_returns_autorun_result():
    page = _FakeCommandPage(task_id=7)

    result = CommandPage.set_command(page, CommandSpec("新命令", "printf ok"))

    assert result is True
    assert page.current_spec.title == "新命令"
    assert len(page.runner.run_calls) == 1


def test_command_page_set_command_defers_when_autorun_disabled():
    page = _FakeCommandPage(task_id=7, autorun_enabled=False)

    result = CommandPage.set_command(page, CommandSpec("新命令", "printf ok"))

    assert result is None
    assert page.current_spec.title == "新命令"
    assert page.runner.run_calls == []


def test_command_page_refresh_stop_button_updates_button_state_text_and_tooltip():
    locked = _FakeStopButtonPage(running=True, stop_locked=True)

    CommandPage.refresh_stop_button(locked)

    assert locked.stop_btn.enabled is False
    assert locked.stop_btn.text == "刷机中，停止锁定"
    assert "远端刷写阶段" in locked.stop_btn.tooltip

    running = _FakeStopButtonPage(running=True)

    CommandPage.refresh_stop_button(running)

    assert running.stop_btn.enabled is True
    assert running.stop_btn.text == "停止任务"
    assert "停止当前本地执行任务" in running.stop_btn.tooltip

    idle = _FakeStopButtonPage()

    CommandPage.refresh_stop_button(idle)

    assert idle.stop_btn.enabled is False
    assert idle.stop_btn.text == "无运行任务"
    assert idle.stop_btn.tooltip == "当前没有正在运行的任务。"


def test_command_display_command_prefers_spec_display_text():
    assert command_display_command(CommandSpec("状态检查", "true")) == "执行：状态检查"
    assert command_display_command(CommandSpec("状态检查", "true", display_command="执行：自定义")) == "执行：自定义"


def test_confirm_command_spec_skips_prompt_for_safe_command(monkeypatch):
    monkeypatch.setattr(QMessageBox, "question", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("safe command should not prompt")))

    assert confirm_command_spec(None, CommandSpec("状态检查", "true")) is True


def test_confirm_command_spec_prompts_for_dangerous_command(monkeypatch):
    calls = []

    def fake_question(*args, **kwargs):
        calls.append((args, kwargs))
        return QMessageBox.No

    monkeypatch.setattr(QMessageBox, "question", fake_question)

    assert confirm_command_spec(None, CommandSpec("停止导航", "true", dangerous=True, description="停止当前任务")) is False
    assert len(calls) == 1
    assert "停止导航" in calls[0][0][2]
    assert "停止当前任务" in calls[0][0][2]


def test_confirm_dangerous_action_uses_cancel_as_default(monkeypatch):
    calls = []

    def fake_question(*args, **kwargs):
        calls.append((args, kwargs))
        return QMessageBox.Cancel

    monkeypatch.setattr(QMessageBox, "question", fake_question)

    assert confirm_dangerous_action(None, "确认删除地图", "该操作不可恢复。") is False
    assert calls[0][0][1] == "确认删除地图"
    assert "该操作不可恢复" in calls[0][0][2]
    assert calls[0][0][3] == QMessageBox.Yes | QMessageBox.Cancel
    assert calls[0][0][4] == QMessageBox.Cancel


def test_device_bar_read_callbacks_return_slot_result():
    page = _FakeDeviceBarReadPage()

    assert DeviceBar._read_connection_output(page, page.connection_slot.process, request_id=21) is True
    assert page.connection_slot.calls == [(page.connection_slot.process, 21)]

    assert DeviceBar._read_battery_output(page, page.battery_slot.process, request_id=22) is False
    assert page.battery_slot.calls == [(page.battery_slot.process, 22)]


def test_device_bar_refresh_battery_throttles_duplicate_auto_probes(monkeypatch):
    clock = {"now": 100.0}
    monkeypatch.setattr(device_bar_battery_ui.time, "monotonic", lambda: clock["now"])
    page = _FakeDeviceBarBatteryRefreshPage()

    DeviceBar.refresh_battery(page)

    assert len(page.battery_slot.start_calls) == 1
    assert page.battery_retry_count == 0
    assert page.battery_slot.processes[-1].started == 1

    clock["now"] += 3.0

    DeviceBar.refresh_battery(page)

    assert len(page.battery_slot.start_calls) == 1

    DeviceBar.refresh_battery(page, request_id=page.battery_slot.request_id, force=True)

    assert len(page.battery_slot.start_calls) == 2

    clock["now"] += components_ui.BATTERY_AUTO_PROBE_MIN_INTERVAL_SECONDS

    DeviceBar.refresh_battery(page)

    assert len(page.battery_slot.start_calls) == 3


def test_device_bar_connection_finished_returns_accept_result():
    stale = _FakeDeviceBarFinishPage(connection_output=None)

    assert DeviceBar._connection_finished(stale, stale.connection_slot.process, request_id=23, exit_code=0) is False

    online = _FakeDeviceBarFinishPage(connection_output="ONLINE\n")

    assert DeviceBar._connection_finished(online, online.connection_slot.process, request_id=24, exit_code=0) is True
    assert online.status.text == "已连接"
    assert online.status.tooltip == ""
    assert online.status.styles[-1] == "color:#167c3f; font-weight:700;"
    assert online.connection_changed.values == [True]

    offline = _FakeDeviceBarFinishPage(connection_output="ssh failed\n")

    assert DeviceBar._connection_finished(offline, offline.connection_slot.process, request_id=25, exit_code=1) is True
    assert offline.status.text == "未连接"
    assert offline.status.tooltip == "连接失败，请检查设备网络或登录信息。"
    assert offline.status.styles[-1] == "color:#8a5a00; font-weight:700;"
    assert offline.connection_changed.values == [False]

    auto_offline = _FakeDeviceBarFinishPage(connection_output="ssh failed\n")

    assert (
        DeviceBar._connection_finished(
            auto_offline, auto_offline.connection_slot.process, request_id=26, exit_code=1, manual=False
        )
        is True
    )
    assert auto_offline.status.text == "未验证"
    assert auto_offline.status.tooltip == "自动连接验证失败；功能区仍会直接尝试远端命令。"
    assert auto_offline.status.styles[-1] == "color:#8a5a00; font-weight:700;"
    assert auto_offline.connection_changed.values == []


def test_device_bar_auto_connection_probe_does_not_broadcast_disconnect():
    page = _FakeDeviceBarConnectionProbePage()

    DeviceBar.test_connection(page, manual=False)

    assert page.status.text == "验证中"
    assert page.connection_changed.values == []
    assert page.connection_slot.processes[-1].started == 1


def test_device_bar_battery_finished_returns_accept_result():
    stale = _FakeDeviceBarFinishPage(battery_output=None)

    assert DeviceBar._battery_finished(stale, stale.battery_slot.process, request_id=26, exit_code=0) is False

    failed = _FakeDeviceBarFinishPage(battery_output="ssh failed\n")

    assert DeviceBar._battery_finished(failed, failed.battery_slot.process, request_id=27, exit_code=1) is True
    assert failed.battery.text == "电量失败"
    assert failed.battery_styles == [(None, False)]

    retry = _FakeDeviceBarFinishPage(battery_output="DOG_REMOTE_BATTERY=UNKNOWN\n")

    assert DeviceBar._battery_finished(retry, retry.battery_slot.process, request_id=28, exit_code=0) is True
    assert retry.battery_retries == [28]

    success = _FakeDeviceBarFinishPage(battery_output="DOG_REMOTE_BATTERY=87\n")

    assert DeviceBar._battery_finished(success, success.battery_slot.process, request_id=29, exit_code=0) is True
    assert success.battery_retry_count == 0
    assert success.battery_cache == {"robot@192.168.234.1": 87}
    assert success.battery_shown == [(87, False)]

    charging = _FakeDeviceBarFinishPage(battery_output="DOG_REMOTE_BATTERY=64\nDOG_REMOTE_CHARGING=1\n")

    assert DeviceBar._battery_finished(charging, charging.battery_slot.process, request_id=30, exit_code=0) is True
    assert charging.battery_retry_count == 0
    assert charging.battery_cache == {"robot@192.168.234.1": 64}
    assert charging.battery_shown == [(64, True)]


def test_battery_status_parser_keeps_legacy_percent_parser():
    output = "DOG_REMOTE_BATTERY=87\nDOG_REMOTE_CHARGING=1\n"

    assert power.parse_battery_status_output(output) == power.BatteryStatus(87, True)
    assert power.parse_battery_output(output) == 87
    assert power.parse_battery_status_output("DOG_REMOTE_BATTERY=UNKNOWN\n") is None


def test_device_bar_can_clear_stale_charging_hint():
    page = _FakeDeviceBarFinishPage()
    page.battery_last_percent = 64
    page.battery_last_charging = True

    assert DeviceBar.clear_battery_charging_hint(page) is True
    assert page.battery_shown == [(64, False)]

    assert DeviceBar.clear_battery_charging_hint(page) is False


def test_device_bar_can_clear_charging_hint_without_percent():
    page = _FakeDeviceBarFinishPage()
    page.battery_last_percent = None
    page.battery_last_charging = True

    assert DeviceBar.clear_battery_charging_hint(page) is True
    assert page.battery_last_charging is False
    assert page.battery.text == "电量 --"
    assert page.battery_styles == [(None, False)]

    assert DeviceBar.clear_battery_charging_hint(page) is False


def test_device_bar_show_battery_updates_text_tooltip_and_style():
    page = _FakeDeviceBarFinishPage()

    DeviceBar._show_battery(page, 64, True)

    assert page.battery.text == "充电中 64%"
    assert page.battery.tooltip == "远端报告正在充电"
    assert page.battery_styles == [(64, True)]

    DeviceBar._show_battery(page, 64, False)

    assert page.battery.text == "电量 64%"
    assert page.battery.tooltip == ""
    assert page.battery_styles[-1] == (64, False)


def test_append_limited_output_keeps_recent_tail():
    chunks = ["abc", "def"]

    append_limited_output(chunks, "ghijkl", limit=5)

    assert "".join(chunks) == "hijkl"


def test_process_slot_invalidate_clears_output_and_advances_request():
    slot = ProcessSlot()
    slot.output_chunks = ["old"]

    request_id = slot.invalidate()

    assert request_id == 1
    assert slot.request_id == 1
    assert slot.output_chunks == []


def test_process_slot_stop_invalidates_current_work_without_process():
    slot = ProcessSlot()
    slot.output_chunks = ["old"]
    slot.request_id = 4

    stopped = slot.stop()

    assert stopped is False
    assert slot.request_id == 5
    assert slot.process is None
    assert slot.output_chunks == []


def test_process_slot_stop_returns_true_for_running_process():
    _app()
    slot = ProcessSlot(stop_timeout_ms=100)
    process, _request_id = slot.start_bash("sleep 5", login_shell=False)
    process.start()
    assert process.waitForStarted(1000)

    stopped = slot.stop()

    assert stopped is True
    assert process.state() == QProcess.NotRunning
    assert slot.process is None


def test_process_slot_stop_async_invalidates_without_waiting_for_exit():
    _app()
    slot = ProcessSlot(stop_timeout_ms=100)
    process, _request_id = slot.start_bash("sleep 5", login_shell=False)
    process.start()
    assert process.waitForStarted(1000)

    stopped = slot.stop_async()

    assert stopped is True
    assert slot.process is None
    assert slot.request_id == 2
    if process.state() != QProcess.NotRunning:
        process.kill()
        process.waitForFinished(1000)


def test_process_slot_start_bash_can_use_non_login_shell():
    slot = ProcessSlot()

    process, request_id = slot.start_bash("echo ok", login_shell=False)

    assert request_id == 1
    assert process.program() == "bash"
    assert process.arguments() == ["-c", "echo ok"]


def test_process_slot_start_spec_respects_owner_runner_conflicts():
    class FakeRunner:
        def __init__(self):
            self.messages = []

        def conflict_reason(self, spec):
            assert spec.title == "读取状态"
            return "当前已有任务运行，请先停止或等待结束。"

        @property
        def output(self):
            class Output:
                def __init__(self, messages):
                    self.messages = messages

                def emit(self, text):
                    self.messages.append(text)

            return Output(self.messages)

    class Owner:
        def __init__(self):
            self.runner = FakeRunner()

    owner = Owner()
    slot = ProcessSlot(owner)

    process, request_id = slot.start_spec(CommandSpec("读取状态", "echo ok"))

    assert process is None
    assert request_id == 0
    assert slot.process is None
    assert owner.runner.messages == ["[WARN] 当前已有任务运行，请先停止或等待结束。\n"]


def test_process_slot_start_spec_can_silence_background_conflict_warning():
    class FakeRunner:
        def __init__(self):
            self.messages = []

        def conflict_reason(self, _spec):
            return "当前独占任务正在运行：执行 OTA 升级"

        @property
        def output(self):
            class Output:
                def __init__(self, messages):
                    self.messages = messages

                def emit(self, text):
                    self.messages.append(text)

            return Output(self.messages)

    class Owner:
        def __init__(self):
            self.runner = FakeRunner()

    owner = Owner()
    slot = ProcessSlot(owner)

    process, request_id = slot.start_spec(CommandSpec("读取电量", "echo ok"), quiet_conflict=True)

    assert process is None
    assert request_id == 0
    assert owner.runner.messages == []


def test_process_slot_start_spec_uses_command_spec_metadata_when_allowed():
    class FakeRunner:
        def conflict_reason(self, spec):
            assert spec.concurrency == "parallel"
            assert spec.locks == ("status",)
            return ""

    class Owner:
        runner = FakeRunner()

    slot = ProcessSlot(Owner())

    process, request_id = slot.start_spec(CommandSpec("读取状态", "echo ok", concurrency="parallel", locks=("status",)), login_shell=False)

    assert request_id == 1
    assert process is slot.process
    assert process.arguments() == ["-c", "echo ok"]


def test_process_slot_start_spec_reserves_and_releases_runner_lock():
    _app()

    class Owner:
        def __init__(self):
            self.runner = ProcessRunner()

    owner = Owner()
    metrics = []
    owner.runner.technical_output.connect(metrics.append)
    slot = ProcessSlot(owner)
    spec = CommandSpec(
        "后台状态流",
        "printf ok # ControlMaster=auto",
        concurrency="parallel",
        locks=("status-stream",),
    )

    process, request_id = slot.start_spec(spec, login_shell=False)

    assert process is slot.process
    assert owner.runner.conflict_reason(concurrency="exclusive") == "当前已有任务运行：后台状态流，请先停止或等待结束。"
    process.start()
    assert process.waitForFinished(2000)
    assert slot.finish(process, request_id) == "ok"
    assert owner.runner.conflict_reason(concurrency="exclusive") == ""
    assert any(
        "[METRIC] 后台状态流 first_output" in item
        and "ssh_control=on" in item
        and "ssh_control_count=1" in item
        and "ssh_proxy=off" in item
        for item in metrics
    )
    assert any("[METRIC] 后台状态流 finished" in item and "elapsed_ms=" in item for item in metrics)


def test_process_slot_can_skip_runner_reservation_for_passive_reads():
    _app()

    class Owner:
        def __init__(self):
            self.runner = ProcessRunner()

    owner = Owner()
    slot = ProcessSlot(owner, reserve_runner=False)
    spec = CommandSpec("读取电量", "printf ok", concurrency="parallel", locks=("device-battery",))

    process, request_id = slot.start_spec(spec, login_shell=False)

    assert process is slot.process
    assert owner.runner.conflict_reason(concurrency="exclusive") == ""
    process.start()
    assert process.waitForFinished(2000)
    assert slot.finish(process, request_id) == "ok"


def test_process_slot_metric_reports_jump_proxy_reuse():
    _app()

    class Owner:
        def __init__(self):
            self.runner = ProcessRunner()

    owner = Owner()
    metrics = []
    owner.runner.technical_output.connect(metrics.append)
    slot = ProcessSlot(owner)
    spec = CommandSpec(
        "连接检测",
        "printf ok # ControlMaster=auto ProxyCommand='ssh -o ControlMaster=auto jump'",
        concurrency="parallel",
    )

    process, request_id = slot.start_spec(spec, login_shell=False)
    process.start()
    assert process.waitForFinished(2000)
    assert slot.finish(process, request_id) == "ok"

    assert any(
        "[METRIC] 连接检测 finished" in item
        and "ssh_control_count=2" in item
        and "ssh_proxy=on" in item
        for item in metrics
    )


def test_process_slot_long_bash_command_uses_stdin_script():
    _app()
    slot = ProcessSlot()
    command = "#" + ("x" * 70000) + "\nprintf ok"

    process, request_id = slot.start_bash(command, login_shell=False)

    assert process.arguments() == ["-s"]
    process.start()
    assert process.waitForFinished(2000)
    assert slot.finish(process, request_id) == "ok"


def test_process_slot_start_bash_stops_existing_running_process():
    _app()
    slot = ProcessSlot(stop_timeout_ms=100)
    first, first_request = slot.start_bash("sleep 5", login_shell=False)
    first.start()
    assert first.waitForStarted(1000)
    try:
        second, second_request = slot.start_bash("printf second", login_shell=False)

        assert first.state() == QProcess.NotRunning
        assert slot.process is second
        assert second_request > first_request
        assert slot.output_chunks == []
    finally:
        slot.stop()


def test_process_slot_start_bash_replaces_stale_not_running_process():
    _app()
    slot = ProcessSlot()
    stale, first_request = slot.start_bash("printf stale", login_shell=False)
    slot.output_chunks = ["stale-output"]

    replacement, second_request = slot.start_bash("printf replacement", login_shell=False)

    assert stale.state() == QProcess.NotRunning
    assert slot.process is replacement
    assert second_request > first_request
    assert slot.output_chunks == []


def test_process_slot_read_available_text_returns_increment_and_buffers_it():
    _app()
    slot = ProcessSlot()
    process, request_id = slot.start_bash("printf first; sleep 0.1; printf second", login_shell=False)
    process.start()
    assert process.waitForStarted(1000)
    try:
        assert process.waitForReadyRead(1000)

        text = slot.read_available_text(process, request_id)
        assert text == "first"
        assert slot.output_chunks == ["first"]

        assert process.waitForFinished(1000)
        output = slot.finish(process, request_id)
        assert output == "firstsecond"
        assert slot.process is None
        assert slot.output_chunks == []
    finally:
        slot.stop()


def test_process_slot_read_available_output_returns_buffer_result():
    _app()
    slot = ProcessSlot()
    process, request_id = slot.start_bash("printf buffered", login_shell=False)
    process.start()
    assert process.waitForStarted(1000)
    try:
        assert process.waitForReadyRead(1000)

        assert slot.read_available_output(process, request_id) is True
        assert slot.output_chunks == ["buffered"]

        assert slot.read_available_output(process, request_id - 1) is False
    finally:
        slot.stop()


def test_process_slot_rejects_stale_output_and_clears_current_process():
    _app()
    slot = ProcessSlot()
    process, request_id = slot.start_bash("printf stale", login_shell=False)
    stale_request_id = request_id - 1
    process.start()
    assert process.waitForStarted(1000)
    try:
        assert process.waitForFinished(1000)

        assert slot.read_available_text(process, stale_request_id) == ""
        assert slot.output_chunks == []
        assert slot.finish(process, stale_request_id) is None
        assert slot.process is None
        assert slot.output_chunks == []
    finally:
        slot.stop()


def test_log_panel_wraps_long_physical_lines_for_block_limit():
    text = LogPanel.wrap_long_lines("abcdef", max_chars=2)

    assert text == "ab\ncd\nef"


def test_log_panel_clean_text_normalizes_carriage_return_progress():
    text = LogPanel.clean_text("10%\r20%\r\n\x1b[31mdone\x1b[0m\n")

    assert text == "10%\n20%\ndone\n"
