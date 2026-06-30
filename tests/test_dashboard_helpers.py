from PyQt5.QtWidgets import QMessageBox

from dog_remote_tool.core.shell import CommandSpec, quote
from dog_remote_tool.modules import device_status
from dog_remote_tool.modules.device_status import launch_labels as device_status_launch_labels
from dog_remote_tool.modules.device_status import models as device_status_models
from dog_remote_tool.modules.device_status import package_labels as device_status_package_labels
from dog_remote_tool.modules.device_status import parser as device_status_parser
from dog_remote_tool.modules.device_status import probe as device_status_probe
from dog_remote_tool.modules.device_status import status as device_status_status
from dog_remote_tool.ui.pages.dashboard import rows as dashboard_rows
from dog_remote_tool.ui.pages.dashboard import status as dashboard_status
from dog_remote_tool.ui.pages.dashboard.page import DashboardPage
from helpers import remote_bash_script as _remote_bash_script, remote_command as _remote_command, FakeSignal as _FakeSignal, FakeRunner as _FakeRunner


class _FakeProfile:
    key = "xg3588"
    platform = "RK3588"
    label = "小狗 3588"
    user = "robot"
    host = "192.168.1.2"
    password = "bot"
    target = "robot@192.168.1.2"


class _FakeDeviceBar:
    def current_profile(self):
        return _FakeProfile()


class _FakeZgLidarNxProfile:
    key = "zg_lidar_nx"
    platform = "Orin NX"



class _FakeLabel:
    def __init__(self, text=""):
        self.text = text
        self.tooltip = ""

    def setText(self, text):
        self.text = text

    def setToolTip(self, text):
        self.tooltip = text

    def toolTip(self):
        return self.tooltip



class _FakeProcess:
    def __init__(self):
        self.readyReadStandardOutput = _FakeSignal()
        self.finished = _FakeSignal()
        self.started = False

    def start(self):
        self.started = True


class _FakeStatusSlot:
    def __init__(self, running=False, output="", read_result=False):
        self.running = running
        self.start_calls = []
        self.stop_calls = 0
        self.finish_output = output
        self.finish_calls = []
        self.read_result = read_result
        self.read_calls = []
        self.process = _FakeProcess()

    def is_running(self):
        return self.running

    def stop(self):
        self.stop_calls += 1
        self.running = False

    def start_bash(self, command):
        self.start_calls.append(command)
        self.running = True
        return self.process, 11

    def start_spec(self, spec):
        return self.start_bash(spec.command)

    def finish(self, process, request_id):
        self.finish_calls.append((process, request_id))
        self.running = False
        return self.finish_output

    def read_available_output(self, process, request_id):
        self.read_calls.append((process, request_id))
        return self.read_result


class _FakeTimer:
    def __init__(self):
        self.started = 0
        self.stopped = 0

    def start(self):
        self.started += 1

    def stop(self):
        self.stopped += 1


class _FakeDashboardRunPage:
    def __init__(self, task_id=None):
        self.runner = _FakeRunner(task_id=task_id)
        self.device_bar = _FakeDeviceBar()
        self.launch_summary_label = _FakeLabel()


class _FakeDashboardStatusPage:
    def __init__(self, *, active=True, running=False):
        self.page_active = active
        self.status_slot = _FakeStatusSlot(running=running)
        self.device_bar = _FakeDeviceBar()

    def _read_status_output(self, process, request_id):
        pass

    def _status_finished(self, process, request_id, exit_code):
        pass


class _FakeDashboardLifecyclePage(_FakeDashboardStatusPage):
    def __init__(self, *, active=False, running=False):
        super().__init__(active=active, running=running)
        self.refresh_calls = 0

    def refresh_status(self):
        self.refresh_calls += 1

    def _stop_status_process(self):
        return DashboardPage._stop_status_process(self)

    def _stop_status_polling(self):
        return DashboardPage._stop_status_polling(self)


class _FakeDashboardDevicePage:
    def __init__(self, *, active=False):
        self.page_active = active
        self.status_slot = _FakeStatusSlot()
        self.release_title_label = _FakeLabel("旧平台版本")
        self.device_release_label = _FakeLabel("旧版本")
        self.package_summary_label = _FakeLabel("旧小包")
        self.launch_summary_label = _FakeLabel("旧运行")
        self.package_rows_calls = []
        self.launch_rows_calls = []
        self.refresh_calls = 0

    def _stop_status_process(self):
        self.status_slot.stop()

    def _release_title(self, profile):
        return DashboardPage._release_title(self, profile)

    def _set_package_rows(self, rows):
        self.package_rows_calls.append(list(rows))

    def _set_launch_rows(self, rows):
        self.launch_rows_calls.append(list(rows))

    def refresh_status(self):
        self.refresh_calls += 1


class _FakeDashboardFinishedPage(_FakeDashboardDevicePage):
    def __init__(self, *, output=""):
        super().__init__(active=False)
        self.status_slot = _FakeStatusSlot(output=output)
        self.device_bar = _FakeDeviceBar()


class _FakeLayoutWidget:
    def __init__(self):
        self.parent = object()
        self.deleted = 0

    def setParent(self, parent):
        self.parent = parent

    def deleteLater(self):
        self.deleted += 1


class _FakeLayoutItem:
    def __init__(self, widget):
        self._widget = widget

    def widget(self):
        return self._widget


class _FakeLayout:
    def __init__(self, widgets=None):
        self.items = [_FakeLayoutItem(widget) for widget in list(widgets or [])]

    def count(self):
        return len(self.items)

    def takeAt(self, index):
        return self.items.pop(index)


class _FakeQtLabel:
    def __init__(self, text=""):
        self._text = text
        self.object_name = ""
        self.tooltip = ""
        self.parent = object()
        self.deleted = 0

    def text(self):
        return self._text

    def setText(self, text):
        self._text = text

    def setObjectName(self, name):
        self.object_name = name

    def setMinimumWidth(self, _width):
        pass

    def setMaximumWidth(self, _width):
        pass

    def setAlignment(self, _alignment):
        pass

    def setWordWrap(self, _enabled):
        pass

    def setTextInteractionFlags(self, _flags):
        pass

    def setToolTip(self, tooltip):
        self.tooltip = tooltip

    def setStyleSheet(self, _style):
        pass

    def toolTip(self):
        return self.tooltip

    def setParent(self, parent):
        self.parent = parent

    def deleteLater(self):
        self.deleted += 1


class _FakeGridLayout(_FakeLayout):
    def __init__(self):
        super().__init__([])
        self.positions = {}
        self.stretches = []
        self.minimum_widths = []

    def addWidget(self, widget, row, column, *_span):
        item = _FakeLayoutItem(widget)
        self.items.append(item)
        self.positions[(row, column)] = item

    def takeAt(self, index):
        item = self.items.pop(index)
        self.positions = {position: current for position, current in self.positions.items() if current is not item}
        return item

    def itemAtPosition(self, row, column):
        return self.positions.get((row, column))

    def rowCount(self):
        if not self.positions:
            return 0
        return max(row for row, _column in self.positions) + 1

    def setColumnStretch(self, column, stretch):
        self.stretches.append((column, stretch))

    def setColumnMinimumWidth(self, column, width):
        self.minimum_widths.append((column, width))


class _FakeActionWidget(_FakeLayoutWidget):
    def __init__(self):
        super().__init__()
        self.minimum_width = 0

    def setMinimumWidth(self, width):
        self.minimum_width = width


class _FakeHBoxLayout:
    def __init__(self, parent=None):
        self.parent = parent
        self.widgets = []
        self.stretches = 0

    def setContentsMargins(self, *_margins):
        pass

    def setSpacing(self, _spacing):
        pass

    def addWidget(self, widget):
        self.widgets.append(widget)

    def addStretch(self, stretch):
        self.stretches += stretch


class _FakeButton(_FakeQtLabel):
    def __init__(self, text=""):
        super().__init__(text)
        self.enabled = True
        self.fixed_width = 0
        self.clicked = _FakeSignal()

    def setEnabled(self, enabled):
        self.enabled = enabled

    def setFixedWidth(self, width):
        self.fixed_width = width


class _FakeDashboardPackageRowsPage:
    def __init__(self):
        self.package_rows = _FakeGridLayout()

    def _clear_layout(self, layout):
        return DashboardPage._clear_layout(self, layout)

    def _package_rows_state(self):
        return DashboardPage._package_rows_state(self)


class _FakeDashboardLaunchRowsPage:
    def __init__(self):
        self.launch_rows = _FakeGridLayout()
        self.actions = []

    def _clear_layout(self, layout):
        return DashboardPage._clear_layout(self, layout)

    def _launch_status_text(self, status):
        return DashboardPage._launch_status_text(self, status)

    def _launch_rows_state(self):
        return DashboardPage._launch_rows_state(self)

    def run_launch_action(self, name, action):
        self.actions.append((name, action))


def test_dashboard_launch_action_marks_not_started_when_runner_rejects_start(monkeypatch):
    page = _FakeDashboardRunPage()

    monkeypatch.setattr(
        device_status,
        "launch_action_command",
        lambda profile, name, action: CommandSpec("robot-launch start nav", "robot-launch start nav"),
    )

    started = DashboardPage.run_launch_action(page, "nav", "start")

    assert started is False
    assert len(page.runner.run_calls) == 1
    assert page.launch_summary_label.text == "任务未启动"
    assert page.launch_summary_label.tooltip == "服务操作未启动，当前有任务运行，请稍后再试。"


def test_dashboard_launch_action_quotes_service_name_in_status_messages():
    profile = _FakeProfile()
    name = "nav'svc"

    spec = device_status.launch_action_command(profile, name, "start")
    script = _remote_bash_script(spec, profile.target)

    assert f"robot-launch start {quote(name)}" in script
    assert quote(f"[INFO] 开启 robot-launch 进程: {name}") in script
    assert f"printf '\\n[robot-launch egg %s] %s\\n' \"$EGG_INDEX\" {quote(name)}" in script
    assert f"printf '\\n[WARN] 未在 robot-launch list 中找到 %s，无法自动查询 egg 详情。\\n' {quote(name)}" in script
    assert "echo '[INFO] 开启 robot-launch 进程:" not in script
    assert f"[robot-launch egg %s] {name}" not in script


def test_dashboard_launch_action_confirms_dangerous_command_cancelled(monkeypatch):
    page = _FakeDashboardRunPage(task_id=7)
    monkeypatch.setattr(
        device_status,
        "launch_action_command",
        lambda profile, name, action: CommandSpec("robot-launch stop nav", "robot-launch stop nav", dangerous=True),
    )
    monkeypatch.setattr(QMessageBox, "question", lambda *args, **kwargs: QMessageBox.No)

    started = DashboardPage.run_launch_action(page, "nav", "stop")

    assert started is False
    assert page.runner.run_calls == []


def test_dashboard_launch_action_runs_dangerous_command_after_confirm(monkeypatch):
    page = _FakeDashboardRunPage(task_id=7)
    monkeypatch.setattr(
        device_status,
        "launch_action_command",
        lambda profile, name, action: CommandSpec("robot-launch restart nav", "robot-launch restart nav", dangerous=True),
    )
    monkeypatch.setattr(QMessageBox, "question", lambda *args, **kwargs: QMessageBox.Yes)

    started = DashboardPage.run_launch_action(page, "nav", "restart")

    assert started is True
    assert len(page.runner.run_calls) == 1


def test_dashboard_refresh_status_returns_start_result():
    inactive = _FakeDashboardStatusPage(active=False)

    assert DashboardPage.refresh_status(inactive) is False
    assert inactive.status_slot.start_calls == []

    busy = _FakeDashboardStatusPage(running=True)

    assert DashboardPage.refresh_status(busy) is False
    assert busy.status_slot.start_calls == []

    page = _FakeDashboardStatusPage()

    assert DashboardPage.refresh_status(page) is True
    assert page.status_slot.process.started is True
    assert len(page.status_slot.start_calls) == 1
    assert "robot@192.168.1.2" in page.status_slot.start_calls[0]


def test_dashboard_read_status_output_returns_slot_result():
    page = _FakeDashboardStatusPage()
    page.status_slot = _FakeStatusSlot(read_result=True)

    assert DashboardPage._read_status_output(page, page.status_slot.process, request_id=13) is True
    assert page.status_slot.read_calls == [(page.status_slot.process, 13)]

    page.status_slot.read_result = False

    assert DashboardPage._read_status_output(page, page.status_slot.process, request_id=14) is False


def test_dashboard_probe_command_prefers_release_yaml_version_field():
    command = device_status.probe_command(_FakeProfile()).command

    assert "/opt/release/version.yaml" in command
    assert "release_version=$(awk" in command
    assert "grep -v" in command
    assert "/version\\.yaml$" in command
    assert "basename \"$release_file\" .yaml" in command


def test_dashboard_probe_package_filter_includes_nvjpeg_packages():
    command = device_status.probe_command(_FakeProfile()).command

    assert "libnvjpeg" in command


def test_dashboard_parse_probe_output_uses_marked_sections():
    output = "\n".join(
        [
            "noise before",
            "HOSTNAME=dog01",
            "RELEASE=v1.2.3",
            "PACKAGES_BEGIN",
            "nav\t1.0",
            "core\t2.0",
            "nav\t1.1",
            "PACKAGES_END",
            "LAUNCH_BEGIN",
            "1 │ 123 │ nav │ running │ - │ 00:10",
            "LAUNCH_END",
            "noise after",
        ]
    )

    status = device_status.parse_probe_output(output)

    assert status.hostname == "dog01"
    assert status.release_version == "v1.2.3"
    assert status.packages == (
        device_status.PackageInfo("core", "2.0"),
        device_status.PackageInfo("nav", "1.1"),
    )
    assert status.raw_launch == "1 │ 123 │ nav │ running │ - │ 00:10"
    assert status.launch_items == (
        device_status.LaunchItem(index="1", name="nav", status="running", pid="123", uptime="00:10"),
    )


def test_dashboard_status_finished_returns_accept_result(monkeypatch):
    output = "\x1b[32mDOG_REMOTE_STATUS_BEGIN\x1b[0m\nHOSTNAME=dog01\nRELEASE=v1.2.3\nPACKAGES_BEGIN\npkg\t1.0\nPACKAGES_END\nLAUNCH_BEGIN\nLAUNCH_END\nDOG_REMOTE_STATUS_END\n"
    monkeypatch.setattr(
        device_status,
        "core_package_items",
        lambda packages, profile: [("核心", "pkg", "1.0"), ("导航", "nav", "未发现")],
    )
    monkeypatch.setattr(device_status, "launch_summary", lambda items, raw_launch: "robot-launch 无输出")
    stale = _FakeDashboardFinishedPage(output=None)

    assert DashboardPage._status_finished(stale, stale.status_slot.process, request_id=9, exit_code=0) is False
    assert stale.device_release_label.text == "旧版本"
    assert stale.status_slot.finish_calls == [(stale.status_slot.process, 9)]

    success = _FakeDashboardFinishedPage(output=output)

    assert DashboardPage._status_finished(success, success.status_slot.process, request_id=11, exit_code=0) is True
    assert success.release_title_label.text == "RK3588版本"
    assert success.device_release_label.text == "v1.2.3"
    assert success.device_release_label.tooltip == "RK3588版本: v1.2.3\n主机名: dog01"
    assert success.package_summary_label.text == "已发现 1/2 项"
    assert success.launch_summary_label.text == "robot-launch 无输出"
    assert success.package_rows_calls == [[("核心", "pkg", "1.0"), ("导航", "nav", "未发现")]]
    assert success.launch_rows_calls == [[]]

    failed = _FakeDashboardFinishedPage(output="ssh failed")

    assert DashboardPage._status_finished(failed, failed.status_slot.process, request_id=12, exit_code=1) is True
    assert failed.device_release_label.text == "读取失败"
    assert failed.package_summary_label.text == "读取失败"
    assert failed.launch_summary_label.text == "读取失败"
    assert failed.package_rows_calls == [[]]
    assert failed.launch_rows_calls == [[]]


def test_nx_package_summary_accepts_robot_sensors_driver_package():
    rows = device_status.core_package_items(
        (
            device_status.PackageInfo("navigation", "0.7.2"),
            device_status.PackageInfo("robot-sensors", "0.0.2"),
            device_status.PackageInfo("robot-deb", "0.1.3-1"),
            device_status.PackageInfo("robots_dog_msgs", "0.8.6-r1"),
            device_status.PackageInfo("zsibot_common", "0.6.1"),
            device_status.PackageInfo("libnvjpeg-12-6", "12.3.3.54-1"),
            device_status.PackageInfo("libnvjpeg-dev-12-6", "12.3.3.54-1"),
        ),
        _FakeZgLidarNxProfile(),
    )

    assert ("传感器驱动", "robot-sensors", "0.0.2") in rows
    assert ("系统工具", "robot-deb", "0.1.3-1") in rows
    assert ("通信消息", "robots_dog_msgs", "0.8.6-r1") in rows
    assert ("公共库", "zsibot_common", "0.6.1") in rows
    assert ("NVJPEG 运行库", "libnvjpeg-12-6", "12.3.3.54-1") in rows
    assert ("NVJPEG 开发库", "libnvjpeg-dev-12-6", "12.3.3.54-1") in rows


def test_dashboard_set_current_device_returns_ui_change_result(monkeypatch):
    single_shots = []

    def fake_single_shot(delay, callback):
        single_shots.append(delay)
        callback()

    monkeypatch.setattr("dog_remote_tool.ui.pages.dashboard.page.QTimer.singleShot", fake_single_shot)

    page = _FakeDashboardDevicePage(active=True)
    profile = _FakeProfile()

    assert DashboardPage._set_current_device(page, profile) is True
    assert page.status_slot.stop_calls == 1
    assert page.release_title_label.text == "RK3588版本"
    assert page.device_release_label.text == ""
    assert page.device_release_label.tooltip == ""
    assert page.package_summary_label.text == "读取中"
    assert page.launch_summary_label.text == "读取中"
    assert page.package_rows_calls == [[]]
    assert page.launch_rows_calls == [[]]
    assert single_shots == [150]
    assert page.refresh_calls == 1

    assert DashboardPage._set_current_device(page, profile) is False
    assert page.status_slot.stop_calls == 2
    assert page.package_rows_calls == [[], []]
    assert page.launch_rows_calls == [[], []]
    assert single_shots == [150, 150]
    assert page.refresh_calls == 2

    nx_profile = _FakeZgLidarNxProfile()
    assert DashboardPage._set_current_device(page, nx_profile) is True
    assert page.release_title_label.text == "Orin NX版本"


def test_dashboard_clear_layout_returns_change_result():
    empty = _FakeLayout()

    assert DashboardPage._clear_layout(None, empty) is False
    assert empty.count() == 0

    first = _FakeLayoutWidget()
    second = _FakeLayoutWidget()
    layout = _FakeLayout([first, second])

    assert DashboardPage._clear_layout(None, layout) is True
    assert layout.count() == 0
    assert first.parent is None
    assert second.parent is None
    assert first.deleted == 1
    assert second.deleted == 1


def test_dashboard_package_rows_return_content_change_result(monkeypatch):
    monkeypatch.setattr("dog_remote_tool.ui.pages.dashboard.page.QLabel", _FakeQtLabel)
    page = _FakeDashboardPackageRowsPage()

    assert DashboardPage._set_package_rows(page, []) is False
    assert page._package_rows_state() == []

    assert DashboardPage._set_package_rows(page, []) is False

    rows = [("核心", "pkg", "1.0"), ("导航", "nav", "未发现")]

    assert DashboardPage._set_package_rows(page, rows) is True
    assert page._package_rows_state() == rows
    assert page.package_rows.minimum_widths[-3:] == [(0, 112), (1, 290), (2, 200)]

    assert DashboardPage._set_package_rows(page, rows) is False

    long_version = "v" * 40

    assert DashboardPage._set_package_rows(page, [("核心", "pkg", long_version)]) is True
    assert page._package_rows_state() == [("核心", "pkg", long_version)]


def test_dashboard_launch_rows_return_content_change_result(monkeypatch):
    monkeypatch.setattr("dog_remote_tool.ui.pages.dashboard.page.QLabel", _FakeQtLabel)
    monkeypatch.setattr("dog_remote_tool.ui.pages.dashboard.page.QWidget", _FakeActionWidget)
    monkeypatch.setattr("dog_remote_tool.ui.pages.dashboard.page.QHBoxLayout", _FakeHBoxLayout)
    monkeypatch.setattr("dog_remote_tool.ui.pages.dashboard.page.QPushButton", _FakeButton)
    monkeypatch.setattr(device_status, "launch_note_label", lambda name: {"nav": "导航"}.get(name, "服务"))
    monkeypatch.setattr(device_status, "launch_note_detail", lambda name: f"{name} detail")
    page = _FakeDashboardLaunchRowsPage()

    assert DashboardPage._set_launch_rows(page, []) is False
    assert page._launch_rows_state() == []

    assert DashboardPage._set_launch_rows(page, []) is False

    rows = [
        device_status.LaunchItem("1", "nav", "running", pid="123", uptime="00:01"),
        device_status.LaunchItem("2", "slam", "stopped", pid="", uptime=""),
    ]

    assert DashboardPage._set_launch_rows(page, rows) is True
    assert page._launch_rows_state() == [
        ("1", "nav", "导航", "运行", "00:01"),
        ("2", "slam", "服务", "停止", "-"),
    ]
    assert page.launch_rows.minimum_widths[-5:] == [(1, 320), (2, 104), (3, 54), (4, 46), (5, 188)]

    assert DashboardPage._set_launch_rows(page, rows) is False

    changed_rows = [device_status.LaunchItem("1", "nav", "failed", pid="123", uptime="00:02")]

    assert DashboardPage._set_launch_rows(page, changed_rows) is True
    assert page._launch_rows_state() == [("1", "nav", "导航", "failed", "00:02")]


def test_dashboard_stop_status_process_returns_running_result():
    idle = _FakeDashboardStatusPage(running=False)

    assert DashboardPage._stop_status_process(idle) is False
    assert idle.status_slot.stop_calls == 1

    running = _FakeDashboardStatusPage(running=True)

    assert DashboardPage._stop_status_process(running) is True
    assert running.status_slot.running is False
    assert running.status_slot.stop_calls == 1


def test_dashboard_page_lifecycle_returns_change_result(monkeypatch):
    single_shots = []

    def fake_single_shot(delay, callback):
        single_shots.append(delay)
        callback()

    monkeypatch.setattr("dog_remote_tool.ui.pages.dashboard.page.QTimer.singleShot", fake_single_shot)

    inactive = _FakeDashboardLifecyclePage(active=False)

    assert DashboardPage.activate_page(inactive) is True
    assert inactive.page_active is True
    assert single_shots == [150]
    assert inactive.refresh_calls == 1

    assert DashboardPage.activate_page(inactive) is False
    assert single_shots == [150]
    assert inactive.refresh_calls == 1

    helper = _FakeDashboardLifecyclePage(active=True, running=True)

    assert DashboardPage._stop_status_polling(helper) is True
    assert helper.page_active is False
    assert helper.status_slot.running is False
    assert helper.status_slot.stop_calls == 1

    active = _FakeDashboardLifecyclePage(active=True, running=False)

    assert DashboardPage.deactivate_page(active) is True
    assert active.page_active is False
    assert active.status_slot.stop_calls == 1

    idle = _FakeDashboardLifecyclePage(active=False, running=False)

    assert DashboardPage.deactivate_page(idle) is False
    assert idle.status_slot.stop_calls == 1

    running = _FakeDashboardLifecyclePage(active=False, running=True)

    assert DashboardPage.shutdown_processes(running) is True
    assert running.page_active is False
    assert running.status_slot.running is False
