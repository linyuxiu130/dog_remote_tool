import shlex
from pathlib import Path

from dog_remote_tool.core import paths as core_paths
from dog_remote_tool.core.parsers import parse_key_values
from dog_remote_tool.core.profiles import get_product
from dog_remote_tool.core.shell import CommandSpec, quote
from dog_remote_tool.modules.remote_access import frp
from dog_remote_tool.modules import remote_access
from dog_remote_tool.modules.remote_access import nx as remote_access_nx
from dog_remote_tool.modules.remote_access import resources as remote_access_resources
from dog_remote_tool.modules.remote_access import public as remote_access_public
from dog_remote_tool.modules.remote_access import wifi as remote_wifi
from dog_remote_tool.modules.remote_access.public import remote_access_resource_paths
from dog_remote_tool.ui.pages.remote_access import actions as remote_access_actions
from dog_remote_tool.ui.pages.remote_access import dialogs as remote_access_dialogs
from dog_remote_tool.ui.pages.remote_access import lifecycle as remote_access_lifecycle
from dog_remote_tool.ui.pages.remote_access import layout as remote_access_layout
from dog_remote_tool.ui.pages.remote_access.page import RemoteAccessPage
from dog_remote_tool.ui.pages.remote_access import public_status as remote_access_public_status
from dog_remote_tool.ui.pages.remote_access import wifi_status as remote_access_wifi_status
from helpers import FakeOutput as _FakeOutput, FakeSignal as _FakeSignal


def test_remote_access_app_root_reuses_core_paths():
    assert remote_access.app_root is core_paths.app_root
    assert frp.app_root is core_paths.app_root


def test_remote_access_resource_paths_reuse_core_resource_path(tmp_path, monkeypatch):
    monkeypatch.setenv("DOG_REMOTE_TOOL_ROOT", str(tmp_path))

    script, binary = remote_access_resource_paths()

    assert remote_access_public.REMOTE_ACCESS_RESOURCE_NAME == remote_access_resources.REMOTE_ACCESS_RESOURCE_NAME
    assert remote_access_public.REMOTE_ACCESS_SCRIPT_NAME == remote_access_resources.REMOTE_ACCESS_SCRIPT_NAME
    assert remote_access_public.REMOTE_ACCESS_BINARY_NAME == remote_access_resources.REMOTE_ACCESS_BINARY_NAME
    assert remote_access_public.REMOTE_SCRIPT_INSTALL_PATH.endswith(
        "/" + remote_access_resources.REMOTE_ACCESS_SCRIPT_NAME
    )
    assert remote_access_public.REMOTE_BINARY_INSTALL_PATH.endswith(
        "/" + remote_access_resources.REMOTE_ACCESS_BINARY_NAME
    )
    assert script == str(
        core_paths.resource_path(
            remote_access_resources.REMOTE_ACCESS_RESOURCE_NAME,
            remote_access_resources.REMOTE_ACCESS_SCRIPT_NAME,
        )
    )
    assert binary == str(
        core_paths.resource_path(
            remote_access_resources.REMOTE_ACCESS_RESOURCE_NAME,
            remote_access_resources.REMOTE_ACCESS_BINARY_NAME,
        )
    )
    assert remote_access_public.REMOTE_ACCESS_RESOURCE_DIR == remote_access.REMOTE_ACCESS_RESOURCE_DIR
    assert remote_access_public.REMOTE_ACCESS_RESOURCE_DIR.endswith("/resources/remote_access")
    assert not remote_access_public.REMOTE_ACCESS_RESOURCE_DIR.startswith("resources/")
    assert remote_access.REMOTE_ACCESS_RESOURCE_DIR.endswith("/resources/remote_access")
    assert not remote_access.REMOTE_ACCESS_RESOURCE_DIR.startswith("resources/")
    assert remote_access.NX_REMOTE_ACCESS_SCRIPT.endswith("/remote_access/start_remote_access.sh")


def test_frp_public_server_reuses_remote_access_public_constant():
    assert frp.PUBLIC_SERVER == remote_access_public.PUBLIC_SERVER


def test_remote_access_package_defaults_share_bundled_or_downloads_helper(tmp_path, monkeypatch):
    frp_zip = tmp_path / "custom_frp.zip"
    community_deb = tmp_path / "custom_community.deb"
    monkeypatch.setenv("DOG_REMOTE_TOOL_FRP_ZIP", str(frp_zip))
    monkeypatch.setenv("DOG_REMOTE_TOOL_COMMUNITY_NODE_DEB", str(community_deb))

    assert frp.default_frp_zip() == str(frp_zip)
    assert remote_access.default_community_node_deb() == str(community_deb)

    monkeypatch.delenv("DOG_REMOTE_TOOL_FRP_ZIP")
    monkeypatch.delenv("DOG_REMOTE_TOOL_COMMUNITY_NODE_DEB")
    monkeypatch.setenv("DOG_REMOTE_TOOL_ROOT", str(tmp_path))

    assert frp.default_frp_zip() == str(Path.home() / "Downloads" / remote_access_resources.FRP_ZIP_NAME)
    assert remote_access.default_community_node_deb() == str(
        Path.home() / "Downloads" / remote_access_resources.COMMUNITY_NODE_DEB_NAME
    )


def test_remote_wifi_status_parser_reuses_core_key_values():
    assert remote_wifi.parse_status_output is parse_key_values


def test_remote_wifi_public_endpoint_reuses_remote_access_public_constant():
    assert remote_wifi.PUBLIC_ACCESS_HOST == remote_access_public.PUBLIC_SERVER
    assert remote_wifi.PUBLIC_ACCESS_PORT == remote_access_public.PUBLIC_PORT_MANAGER_PORT


class _FakeLabel:
    def __init__(self):
        self.text = ""
        self.styles = []

    def setText(self, text):
        self.text = text

    def setStyleSheet(self, style):
        self.styles.append(style)


class _FakeButton:
    def __init__(self):
        self.enabled = None
        self._text = ""
        self.object_name = ""
        self.style_obj = type("Style", (), {"unpolished": 0, "polished": 0})()

        def unpolish(_button):
            self.style_obj.unpolished += 1

        def polish(_button):
            self.style_obj.polished += 1

        self.style_obj.unpolish = unpolish
        self.style_obj.polish = polish

    def setEnabled(self, enabled):
        self.enabled = enabled

    def setText(self, text):
        self._text = text

    def text(self):
        return self._text

    def setObjectName(self, name):
        self.object_name = name

    def objectName(self):
        return self.object_name

    def style(self):
        return self.style_obj


class _FakeLineEdit:
    def __init__(self, text=""):
        self._text = text

    def text(self):
        return self._text

    def setText(self, text):
        self._text = text


class _FakeCombo:
    def __init__(self):
        self.enabled = None
        self.items = []
        self.tooltips = {}
        self.current_index = -1

    def setEnabled(self, enabled):
        self.enabled = enabled

    def currentText(self):
        if 0 <= self.current_index < len(self.items):
            return self.items[self.current_index][0]
        return ""

    def currentData(self):
        if 0 <= self.current_index < len(self.items):
            return self.items[self.current_index][1]
        return None

    def clear(self):
        self.items = []
        self.tooltips = {}
        self.current_index = -1

    def addItem(self, text, data):
        self.items.append((text, data))
        if self.current_index < 0:
            self.current_index = 0

    def setItemData(self, index, value, _role):
        self.tooltips[index] = value

    def count(self):
        return len(self.items)

    def findText(self, text):
        for index, item in enumerate(self.items):
            if item[0] == text:
                return index
        return -1

    def setCurrentIndex(self, index):
        self.current_index = index



class _FakeProcess:
    def __init__(self):
        self.readyReadStandardOutput = _FakeSignal()
        self.finished = _FakeSignal()
        self.started = False

    def start(self):
        self.started = True


class _FakeSlot:
    def __init__(self, running=False, output="", read_text=""):
        self.running = running
        self.start_calls = []
        self.stop_calls = 0
        self.finish_output = output
        self.finish_calls = []
        self.read_text = read_text
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
        return self.process, 7

    def start_spec(self, spec, **_kwargs):
        return self.start_bash(spec.command)

    def finish(self, process, request_id):
        self.finish_calls.append((process, request_id))
        self.running = False
        return self.finish_output

    def read_available_text(self, process, request_id):
        self.read_calls.append((process, request_id))
        return self.read_text

    def read_available_output(self, process, request_id):
        self.read_available_text(process, request_id)


class _FakeTimer:
    def __init__(self):
        self.started = 0
        self.stopped = 0

    def start(self):
        self.started += 1

    def stop(self):
        self.stopped += 1


class _FakeAsyncRemoteAccessPage:
    def __init__(self, *, product="xg2_3588", page_active=True, shutdown=False):
        self.product = product
        self.page_active = page_active
        self.public_status_shutdown = shutdown
        self.wifi_scan_slot = _FakeSlot()
        self.wifi_connect_slot = _FakeSlot()
        self.wifi_status_slot = _FakeSlot()
        self.public_status_slot = _FakeSlot()
        self.public_ssid_slot = _FakeSlot()
        self.wifi_scan_btn = _FakeButton()
        self.wifi_connect_btn = _FakeButton()
        self.wifi_combo = _FakeCombo()
        self.wifi_status = _FakeLabel()
        self.runner = type("Runner", (), {"output": _FakeOutput(), "technical_output": _FakeOutput()})()
        self.refresh_controls_calls = 0
        self.refresh_public_status_calls = 0
        self.refresh_wifi_status_calls = 0
        self.refresh_public_ssid_calls = 0
        self.scan_wifi_calls = 0

    def profile(self):
        return get_product(self.product)

    def _refresh_wifi_controls(self):
        self.refresh_controls_calls += 1
        return False

    def _set_wifi_state(self, values):
        return RemoteAccessPage._set_wifi_state(self, values)

    def refresh_public_status(self):
        self.refresh_public_status_calls += 1
        return True

    def refresh_wifi_status(self):
        self.refresh_wifi_status_calls += 1
        return True

    def refresh_public_ssid(self):
        self.refresh_public_ssid_calls += 1
        return True

    def schedule_public_status_refresh(self, delay_ms):
        return RemoteAccessPage.schedule_public_status_refresh(self, delay_ms)

    def scan_wifi_networks(self):
        self.scan_wifi_calls += 1

    def _stop_async_processes(self, *, include_connect=False):
        return RemoteAccessPage._stop_async_processes(self, include_connect=include_connect)


class _FakeRemoteAccessActionPage:
    def __init__(self):
        self.public_state = "stopped"
        self.public_ssid = _FakeLineEdit("ZSXC")
        self.public_status = _FakeLabel()
        self.set_command_results = []

    def profile(self):
        return get_product("xg2_3588")

    def set_command(self, spec):
        self.set_command_results.append(spec)
        return False


class _FakeRemoteAccessCommandPage(RemoteAccessPage):
    def __init__(self, started):
        self.started = started
        self.remote_command_status = _FakeLabel()
        self.commands = []

    def set_command(self, spec):
        self.commands.append(spec)
        return self.started


class _FakeRemoteAccessChoosePage:
    def __init__(self):
        self.zip_path = _FakeLineEdit()
        self.community_deb_path = _FakeLineEdit()


class _FakeWifiStatePage:
    def __init__(self):
        self.wifi_status = _FakeLabel()


class _FakePublicStatePage:
    def __init__(self):
        self.public_state = ""
        self.public_status = _FakeLabel()
        self.public_button = _FakeButton()

    def _set_public_state(self, state, port, version="unknown", launch_state="unknown"):
        return RemoteAccessPage._set_public_state(self, state, port, version, launch_state)


class _FakeWifiControlsPage:
    def __init__(self, product):
        self.product = product
        self.wifi_scan_btn = _FakeButton()
        self.wifi_connect_btn = _FakeButton()
        self.wifi_combo = _FakeButton()
        self.wifi_status = _FakeLabel()

    def profile(self):
        return get_product(self.product)


def test_public_access_action_marks_not_started_when_runner_rejects_start(monkeypatch):
    page = _FakeRemoteAccessActionPage()

    monkeypatch.setattr(
        remote_access,
        "public_access_action_command",
        lambda profile, ssid, action: CommandSpec("打开公网连接", f"remote_access {action}"),
    )

    started = RemoteAccessPage.run_public_access_action(page)

    assert started is False
    assert page.public_state == "stopped"
    assert len(page.set_command_results) == 1
    assert page.public_status.text == "公网状态：任务未启动"
    assert page.public_status.styles[-1] == "color:#8a5a00; font-weight:700;"


def test_remote_access_command_marks_not_started_when_runner_rejects_start():
    page = _FakeRemoteAccessCommandPage(False)
    spec = CommandSpec("FRP 状态", "frpc status")

    started = RemoteAccessPage.run_remote_access_command(page, spec)

    assert started is False
    assert page.commands == [spec]
    assert page.remote_command_status.text == "FRP 状态：任务未启动，当前有任务运行，请稍后再试。"
    assert page.remote_command_status.styles[-1] == "color:#8a5a00; font-weight:700;"


def test_remote_access_replace_script_quotes_missing_local_script_message(monkeypatch):
    local_script = "/tmp/dog remote/a'start.sh"
    monkeypatch.setattr(remote_access, "default_remote_access_script_path", lambda: local_script)

    spec = remote_access.replace_remote_access_script_command(get_product("xg2_3588"))

    assert quote(f"[失败] 工具内置脚本不存在：{local_script}") in spec.command
    assert "printf '[失败] 工具内置脚本不存在：" not in spec.command
    assert spec.command.index("192.168.234.0/24") < spec.command.index(" scp ")
    assert "sudo_run install -d -m 0755" in spec.command
    assert "sudo_run cp \"$DST\" \"$backup\"" in spec.command
    assert "command -v sudo" not in spec.command


def test_remote_access_command_updates_status_when_runner_starts():
    page = _FakeRemoteAccessCommandPage(True)
    spec = CommandSpec("检查外网", "check internet")

    started = RemoteAccessPage.run_remote_access_command(page, spec)

    assert started is True
    assert page.commands == [spec]
    assert page.remote_command_status.text == "检查外网：已启动"
    assert page.remote_command_status.styles[-1] == "color:#607085; font-weight:700;"


def test_remote_access_file_choosers_return_selection_result(monkeypatch):
    page = _FakeRemoteAccessChoosePage()
    monkeypatch.setattr("dog_remote_tool.ui.pages.remote_access.page.QFileDialog.getOpenFileName", lambda *args, **kwargs: ("", ""))

    assert RemoteAccessPage.choose_zip(page) is False
    assert page.zip_path.text() == ""

    monkeypatch.setattr("dog_remote_tool.ui.pages.remote_access.page.QFileDialog.getOpenFileName", lambda *args, **kwargs: ("/tmp/frp.zip", ""))

    assert RemoteAccessPage.choose_zip(page) is True
    assert page.zip_path.text() == "/tmp/frp.zip"

    monkeypatch.setattr("dog_remote_tool.ui.pages.remote_access.page.QFileDialog.getOpenFileName", lambda *args, **kwargs: ("/tmp/community.deb", ""))

    assert RemoteAccessPage.choose_community_deb(page) is True
    assert page.community_deb_path.text() == "/tmp/community.deb"


def test_remote_access_wifi_scan_returns_start_result():
    inactive = _FakeAsyncRemoteAccessPage(page_active=False)

    assert RemoteAccessPage.scan_wifi_networks(inactive) is False
    assert inactive.wifi_scan_slot.start_calls == []

    unsupported = _FakeAsyncRemoteAccessPage(product="xg2_s100")

    assert RemoteAccessPage.scan_wifi_networks(unsupported) is False
    assert unsupported.refresh_controls_calls == 1
    assert unsupported.wifi_scan_slot.start_calls == []

    busy = _FakeAsyncRemoteAccessPage()
    busy.wifi_scan_slot = _FakeSlot(running=True)

    assert RemoteAccessPage.scan_wifi_networks(busy) is False
    assert busy.wifi_scan_slot.start_calls == []

    page = _FakeAsyncRemoteAccessPage()

    assert RemoteAccessPage.scan_wifi_networks(page) is True
    assert page.wifi_scan_btn.enabled is False
    assert page.wifi_status.text == "WiFi状态：扫描中..."
    assert len(page.wifi_scan_slot.start_calls) == 1
    assert page.wifi_scan_slot.process.started is True


def test_remote_access_wifi_scan_callbacks_return_accept_result():
    read_page = _FakeAsyncRemoteAccessPage()
    read_page.wifi_scan_slot = _FakeSlot(read_text="SSID=ZSXC\tSIGNAL=-40\n")

    assert RemoteAccessPage._read_wifi_scan_output(read_page, read_page.wifi_scan_slot.process, request_id=21) is True
    assert read_page.wifi_scan_slot.read_calls == [(read_page.wifi_scan_slot.process, 21)]

    read_page.wifi_scan_slot.read_text = ""

    assert RemoteAccessPage._read_wifi_scan_output(read_page, read_page.wifi_scan_slot.process, request_id=22) is False

    stale = _FakeAsyncRemoteAccessPage()
    stale.wifi_scan_slot = _FakeSlot(output=None)

    assert RemoteAccessPage._wifi_scan_finished(stale, stale.wifi_scan_slot.process, request_id=23, exit_code=0) is False

    failed = _FakeAsyncRemoteAccessPage()
    failed.wifi_scan_slot = _FakeSlot(output="scan failed")

    assert RemoteAccessPage._wifi_scan_finished(failed, failed.wifi_scan_slot.process, request_id=24, exit_code=1) is True
    assert failed.wifi_scan_btn.enabled is True
    assert failed.wifi_status.text == "WiFi状态：扫描失败：scan failed"
    assert failed.wifi_status.styles[-1] == "color:#c84444; font-weight:700;"

    success = _FakeAsyncRemoteAccessPage()
    success.wifi_combo.addItem("OLD", "OLD")
    success.wifi_scan_slot = _FakeSlot(output="SSID=ZSXC\tSIGNAL=-40\nSSID=Lab\tSIGNAL=-70\n")

    assert RemoteAccessPage._wifi_scan_finished(success, success.wifi_scan_slot.process, request_id=25, exit_code=0) is True
    assert success.wifi_combo.items == [("ZSXC", "ZSXC"), ("Lab", "Lab")]
    assert success.wifi_combo.tooltips == {0: "信号 -40 dBm", 1: "信号 -70 dBm"}
    assert success.wifi_status.text == "WiFi状态：已发现 2 个网络"

    empty = _FakeAsyncRemoteAccessPage()
    empty.wifi_scan_slot = _FakeSlot(output="")

    assert RemoteAccessPage._wifi_scan_finished(empty, empty.wifi_scan_slot.process, request_id=26, exit_code=0) is True
    assert empty.wifi_combo.items == []
    assert empty.wifi_status.text == "WiFi状态：未发现网络"
    assert empty.wifi_status.styles[-1] == "color:#8a5a00; font-weight:700;"


def test_remote_access_wifi_connect_returns_start_result():
    busy = _FakeAsyncRemoteAccessPage()
    busy.wifi_connect_slot = _FakeSlot(running=True)

    assert RemoteAccessPage.connect_wifi(busy, "ZSXC", "pw") is False
    assert busy.wifi_connect_slot.start_calls == []

    page = _FakeAsyncRemoteAccessPage()

    assert RemoteAccessPage.connect_wifi(page, "ZSXC", "pw") is True
    assert page.wifi_connect_btn.enabled is False
    assert page.wifi_status.text == "WiFi状态：正在连接 ZSXC"
    assert page.runner.output.lines[0] == f"[信息] 远程访问 开始连接 3588 WiFi：ZSXC via {remote_wifi.DEFAULT_WIFI_IFACE}\n"
    assert len(page.wifi_connect_slot.start_calls) == 1
    assert page.wifi_connect_slot.process.started is True


def test_remote_access_wifi_state_returns_ui_change_result():
    page = _FakeWifiStatePage()

    assert RemoteAccessPage._set_wifi_state(page, {"STATE": "disconnected"}) is True
    assert page.wifi_status.text == "WiFi状态：未连接"
    assert page.wifi_status.styles[-1] == "color:#8a5a00; font-weight:700;"

    assert RemoteAccessPage._set_wifi_state(page, {"STATE": "disconnected"}) is False

    connected = {"STATE": "connected", "SSID": "ZSXC", "IP": "192.168.0.2", "PUBLIC_TCP": "ok"}

    assert RemoteAccessPage._set_wifi_state(page, connected) is True
    assert page.wifi_status.text == "WiFi状态：已连接 ZSXC / 192.168.0.2，公网可达"
    assert page.wifi_status.styles[-1] == "color:#167c3f; font-weight:700;"

    assert RemoteAccessPage._set_wifi_state(page, connected) is False

    pending = {"STATE": "connected", "SSID": "ZSXC", "IP": "192.168.0.2", "PUBLIC_TCP": "fail"}

    assert RemoteAccessPage._set_wifi_state(page, pending) is True
    assert page.wifi_status.text == "WiFi状态：已连接 ZSXC / 192.168.0.2，公网待确认"


def test_remote_access_public_state_returns_ui_change_result():
    page = _FakePublicStatePage()

    assert RemoteAccessPage._set_public_state(page, "running", "60022", version="new", launch_state="running") is True
    assert page.public_state == "running"
    assert page.public_status.text == "公网状态：已打开 60022（新版本，launch:running）"
    assert page.public_status.styles[-1] == "color:#167c3f; font-weight:700;"
    assert page.public_button.text() == "关闭公网连接"
    assert page.public_button.objectName() == "Danger"
    assert page.public_button.style_obj.unpolished == 1
    assert page.public_button.style_obj.polished == 1

    assert RemoteAccessPage._set_public_state(page, "running", "60022", version="new", launch_state="running") is False
    assert page.public_button.style_obj.unpolished == 1
    assert page.public_button.style_obj.polished == 1

    assert RemoteAccessPage._set_public_state(page, "stopped", "", version="old") is True
    assert page.public_status.text == "公网状态：未打开（旧版本）"
    assert page.public_button.text() == "打开公网连接"
    assert page.public_button.objectName() == "Primary"

    assert RemoteAccessPage._set_public_state(page, "errored", "", version="unknown", launch_state="failed") is True
    assert page.public_status.text == "公网状态：异常（版本未知，launch:failed）"
    assert page.public_status.styles[-1] == "color:#c84444; font-weight:700;"

    assert RemoteAccessPage._set_public_state(page, "unknown", "") is True
    assert page.public_status.text == "公网状态：未知"
    assert page.public_status.styles[-1] == "color:#607085; font-weight:700;"


def test_remote_access_wifi_controls_return_change_result():
    supported = _FakeWifiControlsPage("xg2_3588")

    assert RemoteAccessPage._refresh_wifi_controls(supported) is True
    assert supported.wifi_scan_btn.enabled is True
    assert supported.wifi_connect_btn.enabled is True
    assert supported.wifi_combo.enabled is True

    assert RemoteAccessPage._refresh_wifi_controls(supported) is False

    unsupported = _FakeWifiControlsPage("xg2_s100")

    assert RemoteAccessPage._refresh_wifi_controls(unsupported) is True
    assert unsupported.wifi_scan_btn.enabled is False
    assert unsupported.wifi_connect_btn.enabled is False
    assert unsupported.wifi_combo.enabled is False
    assert unsupported.wifi_status.text == "WiFi状态：请选择 RK3588 目标"
    assert unsupported.wifi_status.styles[-1] == "color:#607085; font-weight:700;"

    assert RemoteAccessPage._refresh_wifi_controls(unsupported) is False


def test_remote_access_profile_changed_returns_change_result():
    inactive = _FakeAsyncRemoteAccessPage(page_active=False)

    assert RemoteAccessPage._profile_changed(inactive, inactive.profile()) is False
    assert inactive.refresh_controls_calls == 1
    assert inactive.refresh_public_ssid_calls == 0
    assert inactive.refresh_public_status_calls == 0
    assert inactive.refresh_wifi_status_calls == 0
    assert inactive.wifi_connect_slot.stop_calls == 1

    active = _FakeAsyncRemoteAccessPage(page_active=True)

    assert RemoteAccessPage._profile_changed(active, active.profile()) is True
    assert active.refresh_controls_calls == 1
    assert active.refresh_public_ssid_calls == 1
    assert active.refresh_public_status_calls == 1
    assert active.refresh_wifi_status_calls == 1


def test_remote_access_public_probe_finished_returns_accept_result():
    read_page = _FakeAsyncRemoteAccessPage()
    read_page.public_ssid_slot = _FakeSlot(read_text="SSID=ZSXC\n")
    read_page.public_status_slot = _FakeSlot(read_text="STATE=running\n")

    assert RemoteAccessPage._read_public_ssid(read_page, read_page.public_ssid_slot.process, request_id=27) is True
    assert RemoteAccessPage._read_public_status(read_page, read_page.public_status_slot.process, request_id=28) is True

    read_page.public_ssid_slot.read_text = ""
    read_page.public_status_slot.read_text = ""

    assert RemoteAccessPage._read_public_ssid(read_page, read_page.public_ssid_slot.process, request_id=29) is False
    assert RemoteAccessPage._read_public_status(read_page, read_page.public_status_slot.process, request_id=30) is False

    shutdown_read = _FakeAsyncRemoteAccessPage(shutdown=True)
    shutdown_read.public_ssid_slot = _FakeSlot(read_text="SSID=ZSXC\n")
    shutdown_read.public_status_slot = _FakeSlot(read_text="STATE=running\n")

    assert RemoteAccessPage._read_public_ssid(shutdown_read, shutdown_read.public_ssid_slot.process, request_id=31) is False
    assert RemoteAccessPage._read_public_status(shutdown_read, shutdown_read.public_status_slot.process, request_id=32) is False
    assert shutdown_read.public_ssid_slot.read_calls == []
    assert shutdown_read.public_status_slot.read_calls == []

    stale = _FakeAsyncRemoteAccessPage()
    stale.public_ssid_slot = _FakeSlot(output=None)

    assert RemoteAccessPage._public_ssid_finished(stale, stale.public_ssid_slot.process, request_id=3, exit_code=0) is False
    assert stale.public_ssid_slot.finish_calls == [(stale.public_ssid_slot.process, 3)]

    ssid_page = _FakeAsyncRemoteAccessPage()
    ssid_page.public_ssid = _FakeLineEdit("OLD")
    ssid_page.public_ssid_slot = _FakeSlot(output="SSID=ZSXC\n")

    assert RemoteAccessPage._public_ssid_finished(ssid_page, ssid_page.public_ssid_slot.process, request_id=4, exit_code=0) is True
    assert ssid_page.public_ssid.text() == "ZSXC"

    assert RemoteAccessPage._public_ssid_finished(ssid_page, ssid_page.public_ssid_slot.process, request_id=5, exit_code=0) is False

    shutdown = _FakeAsyncRemoteAccessPage(shutdown=True)
    shutdown.public_status_slot = _FakeSlot(output="STATE=running\nPORT=60022\nVERSION=new\n")

    assert RemoteAccessPage._public_status_finished(shutdown, shutdown.public_status_slot.process, request_id=6, exit_code=0) is False
    assert shutdown.public_status_slot.finish_calls == [(shutdown.public_status_slot.process, 6)]

    failed = _FakePublicStatePage()
    failed.public_status_shutdown = False
    failed.public_status_slot = _FakeSlot(output="ssh failed")

    assert RemoteAccessPage._public_status_finished(failed, failed.public_status_slot.process, request_id=7, exit_code=1) is True
    assert failed.public_state == "unknown"
    assert failed.public_status.text == "公网状态：未知"

    status_page = _FakePublicStatePage()
    status_page.public_status_shutdown = False
    status_page.public_status_slot = _FakeSlot(output="STATE=running\nPORT=60022\nVERSION=new\nLAUNCH_STATE=running\n")

    assert RemoteAccessPage._public_status_finished(status_page, status_page.public_status_slot.process, request_id=8, exit_code=0) is True
    assert status_page.public_status.text == "公网状态：已打开 60022（新版本，launch:running）"


def test_remote_access_wifi_io_callbacks_return_accept_result(monkeypatch):
    page = _FakeAsyncRemoteAccessPage()
    page.wifi_connect_slot = _FakeSlot(read_text="connecting\n")

    assert RemoteAccessPage._read_wifi_connect_output(page, page.wifi_connect_slot.process, request_id=9) is True
    assert page.runner.output.lines[-1] == "connecting\n"
    assert page.wifi_connect_slot.read_calls == [(page.wifi_connect_slot.process, 9)]

    page.wifi_connect_slot.read_text = ""

    assert RemoteAccessPage._read_wifi_connect_output(page, page.wifi_connect_slot.process, request_id=10) is False

    stale = _FakeAsyncRemoteAccessPage()
    stale.wifi_connect_slot = _FakeSlot(output=None)

    assert RemoteAccessPage._wifi_connect_finished(stale, stale.wifi_connect_slot.process, request_id=11, exit_code=0) is False

    single_shots = []

    def fake_single_shot(delay, callback):
        single_shots.append(delay)
        callback()

    monkeypatch.setattr("dog_remote_tool.ui.pages.remote_access.page.QTimer.singleShot", fake_single_shot)

    success = _FakeAsyncRemoteAccessPage()
    success.wifi_connect_slot = _FakeSlot(
        output="STATE=connected\nSSID=ZSXC\nIP=192.168.0.2\nPUBLIC_TCP=ok\n",
        read_text="connected\n",
    )

    assert RemoteAccessPage._wifi_connect_finished(success, success.wifi_connect_slot.process, request_id=12, exit_code=0) is True
    assert success.wifi_connect_btn.enabled is True
    assert success.wifi_status.text == "WiFi状态：已连接 ZSXC / 192.168.0.2，公网可达"
    assert success.runner.output.lines[-1] == "[完成] 远程访问 3588 WiFi 已连接\n"
    assert single_shots == [800]
    assert success.refresh_public_status_calls == 1

    inactive_success = _FakeAsyncRemoteAccessPage(page_active=False)
    inactive_success.wifi_connect_slot = _FakeSlot(output="STATE=connected\nSSID=ZSXC\nIP=192.168.0.2\nPUBLIC_TCP=ok\n")

    assert RemoteAccessPage._wifi_connect_finished(inactive_success, inactive_success.wifi_connect_slot.process, request_id=14, exit_code=0) is True
    assert single_shots == [800]
    assert inactive_success.refresh_public_status_calls == 0

    failed = _FakeAsyncRemoteAccessPage()
    failed.wifi_connect_slot = _FakeSlot(output="STATE=disconnected\n")

    assert RemoteAccessPage._wifi_connect_finished(failed, failed.wifi_connect_slot.process, request_id=13, exit_code=1) is True
    assert failed.wifi_status.text == "WiFi状态：连接失败"
    assert failed.wifi_status.styles[-1] == "color:#c84444; font-weight:700;"
    assert failed.runner.output.lines[-1] == "[失败] 远程访问 3588 WiFi 连接失败\n"
    assert failed.runner.technical_output.lines[-1] == "[失败] 远程访问 3588 WiFi 连接失败，返回码 1\n"

    status_read = _FakeAsyncRemoteAccessPage()
    status_read.wifi_status_slot = _FakeSlot(read_text="STATE=connected\n")

    assert RemoteAccessPage._read_wifi_status_output(status_read, status_read.wifi_status_slot.process, request_id=14) is True

    status_read.wifi_status_slot.read_text = ""

    assert RemoteAccessPage._read_wifi_status_output(status_read, status_read.wifi_status_slot.process, request_id=15) is False

    status_stale = _FakeAsyncRemoteAccessPage()
    status_stale.wifi_status_slot = _FakeSlot(output=None)

    assert RemoteAccessPage._wifi_status_finished(status_stale, status_stale.wifi_status_slot.process, request_id=16, exit_code=0) is False

    status_failed = _FakeAsyncRemoteAccessPage()
    status_failed.wifi_status_slot = _FakeSlot(output="ssh failed")

    assert RemoteAccessPage._wifi_status_finished(status_failed, status_failed.wifi_status_slot.process, request_id=17, exit_code=1) is True
    assert status_failed.wifi_status.text == "WiFi状态：检测失败"
    assert RemoteAccessPage._wifi_status_finished(status_failed, status_failed.wifi_status_slot.process, request_id=18, exit_code=1) is False

    status_success = _FakeAsyncRemoteAccessPage()
    status_success.wifi_status_slot = _FakeSlot(output="STATE=connected\nSSID=ZSXC\nIP=192.168.0.2\nPUBLIC_TCP=fail\n")

    assert RemoteAccessPage._wifi_status_finished(status_success, status_success.wifi_status_slot.process, request_id=19, exit_code=0) is True
    assert status_success.wifi_status.text == "WiFi状态：已连接 ZSXC / 192.168.0.2，公网待确认"
    assert RemoteAccessPage._wifi_status_finished(status_success, status_success.wifi_status_slot.process, request_id=20, exit_code=0) is False


def test_remote_access_async_lifecycle_returns_change_result(monkeypatch):
    single_shots = []

    def fake_single_shot(delay, callback):
        single_shots.append(delay)
        callback()

    monkeypatch.setattr("dog_remote_tool.ui.pages.remote_access.page.QTimer.singleShot", fake_single_shot)

    page = _FakeAsyncRemoteAccessPage(page_active=False)

    assert RemoteAccessPage.activate_page(page) is True
    assert page.page_active is True
    assert single_shots == [300, 450, 600]
    assert page.refresh_public_status_calls == 1
    assert page.refresh_wifi_status_calls == 1
    assert page.refresh_public_ssid_calls == 1
    assert page.scan_wifi_calls == 0

    assert RemoteAccessPage.activate_page(page) is False
    assert single_shots == [300, 450, 600]

    active = _FakeAsyncRemoteAccessPage(page_active=True)

    assert RemoteAccessPage.deactivate_page(active) is True
    assert active.page_active is False
    assert active.public_status_slot.stop_calls == 1
    assert active.wifi_connect_slot.stop_calls == 0

    idle = _FakeAsyncRemoteAccessPage(page_active=False)

    assert RemoteAccessPage.deactivate_page(idle) is False

    running = _FakeAsyncRemoteAccessPage(page_active=False)
    running.wifi_connect_slot = _FakeSlot(running=True)

    assert RemoteAccessPage.shutdown_processes(running) is True
    assert running.public_status_shutdown is True
    assert running.wifi_connect_slot.stop_calls == 1


def test_remote_access_refresh_probes_return_start_result():
    inactive = _FakeAsyncRemoteAccessPage(page_active=False)

    assert RemoteAccessPage.refresh_public_status(inactive) is False
    assert inactive.public_status_slot.start_calls == []

    shutdown = _FakeAsyncRemoteAccessPage(shutdown=True)

    assert RemoteAccessPage.refresh_public_ssid(shutdown) is False
    assert shutdown.public_ssid_slot.start_calls == []

    busy = _FakeAsyncRemoteAccessPage()
    busy.public_status_slot = _FakeSlot(running=True)

    assert RemoteAccessPage.refresh_public_status(busy) is False
    assert busy.public_status_slot.start_calls == []

    public_page = _FakeAsyncRemoteAccessPage()
    ssid_page = _FakeAsyncRemoteAccessPage()
    wifi_page = _FakeAsyncRemoteAccessPage()

    assert RemoteAccessPage.refresh_public_status(public_page) is True
    assert public_page.public_status_slot.process.started is True
    assert len(public_page.public_status_slot.start_calls) == 1
    assert RemoteAccessPage.refresh_public_ssid(ssid_page) is True
    assert ssid_page.public_ssid_slot.process.started is True
    assert len(ssid_page.public_ssid_slot.start_calls) == 1
    assert RemoteAccessPage.refresh_wifi_status(wifi_page) is True
    assert wifi_page.wifi_status_slot.process.started is True
    assert len(wifi_page.wifi_status_slot.start_calls) == 1


def test_internet_check_targets_public_server_ports(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path))

    spec = remote_access.internet_check_command(get_product("xg2_3588"))
    command = spec.command

    assert "47.102.113.200 7501" in command
    assert "47.102.113.200 7000" in command
    assert "公网服务器端口可达，可启动 remote_access/FRP" in command
    assert "DNS 解析 fail（remote_access 使用公网 IP，不影响启动）" in command
    assert "IP 可达但域名失败，优先检查 DNS" not in command
    assert spec.concurrency == "exclusive"


def test_public_access_start_allows_dns_failure_when_public_server_is_reachable(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path))

    command = remote_access.public_access_action_command(get_product("xg2_3588"), action="open").command

    assert "47.102.113.200 7501" in command
    assert "/opt/robot/nx-launch/script/start_remote_access.sh" in command
    assert "/usr/local/bin/remote_access" in command
    assert "请先点击“同步脚本和程序”" in command
    assert "iwgetid -r wlan0" in command
    assert "启动] remote_access，不带 --ssid" in command
    assert "--ssid" in command
    assert "STREAM_ID_ARG" in command
    assert "[版本]" not in command
    assert "DNS 失败，但 remote_access 使用公网 IP，可继续启动" in command


def test_public_access_start_quotes_missing_remote_install_messages(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path))
    script_path = "/opt/robot/nx-launch/script/a'start.sh"
    binary_path = "/usr/local/bin/a'remote_access"
    monkeypatch.setattr(
        "dog_remote_tool.modules.remote_access.public._remote_install_paths",
        lambda profile: (script_path, binary_path),
    )

    profile = get_product("xg2_3588")
    command = remote_access.public_access_action_command(profile, action="open").command
    args = shlex.split(command)
    remote_command = args[args.index(profile.target) + 1]

    assert quote(f"[失败] 启动脚本未同步：{script_path}\n请先点击“同步脚本和程序”。") in remote_command
    assert quote(f"[失败] remote_access 程序未同步：{binary_path}\n请先点击“同步脚本和程序”。") in remote_command
    assert "printf '[失败] 启动脚本未同步：" not in remote_command
    assert "printf '[失败] remote_access 程序未同步：" not in remote_command
    assert "公网连接已打开" in command
    assert "IP 可达但 DNS 失败，请先修复 DNS" not in command
    assert "scp " not in command
    assert "上传到临时目录" not in command
    assert "/home/robot/start_remote_access.sh" not in command
    assert "/home/robot/remote_access " not in command
    assert "pgrep -af 'remote_access|frpc'" not in command


def test_public_ssh_test_runs_external_login_and_reports_result(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path))

    spec = frp.external_ssh_command(get_product("xg2_3588"))
    command = spec.command

    assert spec.title == "公网 SSH 连通测试"
    assert "公网 SSH 测试通过" in command
    assert "ONLINE" in command
    assert "robot@47.102.113.200" in command
    assert "-o ConnectTimeout=8" in command
    assert "未读取到公网端口 remotePort" in command


def test_sync_remote_access_files_uses_requested_install_paths(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path))

    spec = remote_access.sync_remote_access_files_command(get_product("xg2_3588"))

    assert spec.title == "同步脚本和程序"
    assert "/opt/robot/nx-launch/script/start_remote_access.sh" in spec.command
    assert "/usr/local/bin/remote_access" in spec.command
    assert "sudo_run install -d -m 0755" in spec.command
    assert "sudo_run install -m \"$mode\"" in spec.command
    assert "SUDO_PASS=${DOG_REMOTE_SUDO_PASS" not in spec.command
    assert "$SUDO_PASS" not in spec.command
    assert "command -v sudo" not in spec.command
    assert spec.command.index("192.168.234.0/24") < spec.command.index(" scp ")
    assert spec.dangerous is True


def test_deploy_nx_remote_access_script_reuses_remote_script_path_constant(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path))

    spec = remote_access.deploy_nx_remote_access_script_command(get_product("xg2_3588"), "/tmp/start_remote_access.sh")

    assert remote_access.NX_REMOTE_SCRIPT_PATH in spec.command
    assert "sudo_run install -m 0755" in spec.command
    assert "command -v sudo" not in spec.command
    assert "sha256sum " + quote(remote_access.NX_REMOTE_SCRIPT_PATH) in spec.command
    assert spec.dangerous is True


def test_install_community_node_uses_selected_deb_filename(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path))
    profile = get_product("xg2_3588")
    local_deb = "/tmp/custom community.deb"

    spec = remote_access.install_community_node_command(profile, local_deb)
    args = shlex.split(spec.command)
    remote_command = args[args.index(profile.target) + 1]

    assert local_deb in spec.command
    assert f"sudo dpkg -i {quote(profile.home + '/custom community.deb')}" in remote_command
    assert remote_access.PUBLIC_SERVER.replace(".", "\\.") in remote_command
    assert "~/community-node_0.0.4-arm64_nx_remote_control.deb" not in remote_command
    assert spec.dangerous is True


def test_frp_deploy_upload_uses_route_repair_for_wired_targets(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path))

    spec = frp.deploy_command(get_product("xg2_3588"), "/tmp/frp.zip")

    assert spec.title == "部署 FRP"
    assert spec.command.index("192.168.234.0/24") < spec.command.index(" rsync -a ")
    assert spec.dangerous is True


def test_sync_remote_access_files_quotes_missing_resource_messages(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path))
    local_script = "/tmp/dog remote/a'start.sh"
    local_binary = "/tmp/dog remote/a'remote_access"
    monkeypatch.setattr(
        "dog_remote_tool.modules.remote_access.public.remote_access_resource_paths",
        lambda: (local_script, local_binary),
    )

    spec = remote_access.sync_remote_access_files_command(get_product("xg2_3588"))

    assert quote(f"[失败] 工具内置脚本不存在：{local_script}") in spec.command
    assert quote(f"[失败] 工具内置程序不存在：{local_binary}") in spec.command
    assert "printf '[失败] 工具内置脚本不存在：" not in spec.command
    assert "printf '[失败] 工具内置程序不存在：" not in spec.command


def test_public_ssid_probe_reads_3588_hotspot_name(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path))

    command = remote_access.public_ssid_probe_command(get_product("xg2_3588"))

    assert "/userdata/bak/system/hostapd.conf" in command
    assert "iwgetid -r wlan0" in command
    assert "SSID=%s" in command


def test_bundled_start_script_can_read_3588_wlan0_ssid():
    script, _binary = remote_access_resource_paths()
    text = open(script, encoding="utf-8").read()

    assert "iwgetid -r wlan0" in text
    assert "iw dev wlan0 info" in text
    assert "awk -F'=' '/^ssid=/" in text


def test_status_command_uses_exact_process_matching(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path))

    spec = remote_access.status_command(get_product("xg2_3588"))

    assert "ps -ef | grep -E 'remote_access|frpc'" not in spec.command
    assert "pgrep -x remote_access" in spec.command
    assert "未发现 remote_access/frpc 进程" in spec.command
    assert spec.concurrency == "exclusive"
