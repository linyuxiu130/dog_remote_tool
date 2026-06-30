import io
import importlib
import json
import os
import shlex
import shutil
import subprocess
import tarfile
import zipfile
from pathlib import Path
from types import SimpleNamespace

from PyQt5.QtWidgets import QMessageBox

from dog_remote_tool.core.shell import CommandSpec
from dog_remote_tool.core.profiles import get_product
from dog_remote_tool.modules import ota
from dog_remote_tool.modules.ota import backend as ota_backend
from dog_remote_tool.modules.ota import backend_runner as ota_backend_runner
from dog_remote_tool.modules.ota import commands as ota_commands
from dog_remote_tool.modules.ota import flash as ota_flash
from dog_remote_tool.modules.ota import flash_extract as ota_flash_extract
from dog_remote_tool.modules.ota import flash_package as ota_flash_package
from dog_remote_tool.modules.ota import flash_s100_dfu as ota_flash_s100_dfu
from dog_remote_tool.modules.ota import flash_s100_entry as ota_flash_s100_entry
from dog_remote_tool.modules.ota import flash_s100_fastboot as ota_flash_s100_fastboot
from dog_remote_tool.modules.ota import flash_s100_monitor as ota_flash_s100_monitor
from dog_remote_tool.modules.ota import flash_s100_package_check as ota_flash_s100_package_check
from dog_remote_tool.modules.ota import flash_s100_remote as ota_flash_s100_remote
from dog_remote_tool.modules.ota import flash_tooling as ota_flash_tooling
from dog_remote_tool.modules.ota import flash_types as ota_flash_types
from dog_remote_tool.modules.ota import flash_upgrade_scripts as ota_flash_upgrade_scripts
from dog_remote_tool.modules.ota import local_validation as ota_local_validation
from dog_remote_tool.modules.ota import manifest as ota_manifest
from dog_remote_tool.modules.ota import package_display as ota_package_display
from dog_remote_tool.modules.ota import package_locator as ota_package_locator
from dog_remote_tool.modules.ota import package_mcu as ota_package_mcu
from dog_remote_tool.modules.ota import package_utils as ota_package_utils
from dog_remote_tool.modules.ota import package_versions as ota_package_versions
from dog_remote_tool.modules.ota import remote_checks as ota_remote_checks
from dog_remote_tool.modules.ota import remote_execution as ota_remote_execution
from dog_remote_tool.modules.ota import remote_mcu_checks as ota_remote_mcu_checks
from dog_remote_tool.modules.ota import remote_nx as ota_remote_nx
from dog_remote_tool.modules.ota import remote_precheck_scripts as ota_remote_precheck_scripts
from dog_remote_tool.modules.ota import remote_rk as ota_remote_rk
from dog_remote_tool.modules.ota import remote_shell as ota_remote_shell
from dog_remote_tool.ui.pages.ota import actions as ota_actions
from dog_remote_tool.ui.pages.ota import device_info as ota_device_info
from dog_remote_tool.ui.pages.ota import layout as ota_layout
from dog_remote_tool.ui.pages.ota.page import PACKAGE_DIALOG_FILTER, OtaPage, parse_flash_progress
from helpers import FakeSignal as _FakeSignal, FakeRunner as _FakeRunner


ota_ui_targets = importlib.import_module("dog_remote_tool.modules.ota.ui_targets")



class _FakeOtaRunPage:
    def __init__(self):
        self.current_spec = CommandSpec("OTA 预检", "true", dangerous=False)
        self.runner = _FakeRunner(task_id=None)

    def display_command_for_log(self):
        return self.current_spec.title


class _FakeOtaActionPage:
    def __init__(self, *, validate=True, run_result=True):
        self.validate_result = validate
        self.run_result = run_result
        self.current_spec = None
        self.run_calls = 0

    def validate_package_for_target(self):
        return self.validate_result

    def upgrade_spec(self):
        return CommandSpec("执行 OTA 升级", "upgrade", dangerous=True)

    def precheck_spec(self):
        return CommandSpec("OTA 预检", "precheck", dangerous=True)

    def entry_monitor_spec(self):
        return CommandSpec("S100 刷写入口观察", "entry-monitor")

    def run_current(self):
        self.run_calls += 1
        return self.run_result


class _FakeOtaChoosePage:
    def __init__(self):
        self.package = _FakeText()
        self.info_updates = 0

    def update_info_label(self):
        self.info_updates += 1


class _FakeOtaStopButton:
    def __init__(self):
        self.enabled = None
        self._text = ""
        self.tooltip = ""

    def setEnabled(self, enabled):
        self.enabled = enabled

    def text(self):
        return self._text

    def setText(self, text):
        self._text = text

    def setToolTip(self, tooltip):
        self.tooltip = tooltip

    def toolTip(self):
        return self.tooltip


class _FakeOtaStopRunner:
    def __init__(self, *, running=False, stop_locked=False):
        self.running = running
        self.stop_locked = stop_locked

    def is_running(self):
        return self.running


class _FakeOtaStopPage:
    def __init__(self, *, running=False, stop_locked=False):
        self.runner = _FakeOtaStopRunner(running=running, stop_locked=stop_locked)
        self.stop_task_btn = _FakeOtaStopButton()


class _FakeText:
    def __init__(self, text=""):
        self._text = text

    def text(self):
        return self._text

    def setText(self, text):
        self._text = text


def _write_test_deb(path, package="navigation", version="0.7.2", architecture="arm64"):
    control = f"Package: {package}\nVersion: {version}\nArchitecture: {architecture}\n".encode("utf-8")
    control_buf = io.BytesIO()
    with tarfile.open(fileobj=control_buf, mode="w:gz") as tf:
        info = tarfile.TarInfo("control")
        info.size = len(control)
        tf.addfile(info, io.BytesIO(control))
    control_tar = control_buf.getvalue()

    def ar_member(name, payload):
        header = (
            f"{name:<16}"
            f"{0:<12}"
            f"{0:<6}"
            f"{0:<6}"
            f"{0o100644:<8}"
            f"{len(payload):<10}"
            "`\n"
        ).encode("ascii")
        padding = b"\n" if len(payload) % 2 else b""
        return header + payload + padding

    path.write_bytes(
        b"!<arch>\n"
        + ar_member("debian-binary", b"2.0\n")
        + ar_member("control.tar.gz", control_tar)
        + ar_member("data.tar.gz", b"")
    )


def _write_zgnx_zip_package(path, tmp_path):
    payload = tmp_path / "ota_package.tar"
    payload.write_bytes(b"nx-payload")
    inner = tmp_path / "nx_ota_hermes_m_v0.1.3.tar.gz"
    with tarfile.open(inner, "w:gz") as tf:
        tf.add(payload, arcname="ota_package.tar")
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr(
            "package_info.json",
            json.dumps(
                {
                    "system": {"image_regex": "image/.*\\.tar\\.gz$"},
                    "modules": [
                        {
                            "name": "rtk_mcu",
                            "package_regex": "firmware/rtk.*?\\.bin$",
                            "tool_regex": "tool/mcu_upgrade.*$",
                        }
                    ],
                }
            ),
        )
        zf.write(inner, "image/nx_ota_hermes_m_v0.1.3.tar.gz")
        zf.writestr("firmware/rtk_mcu_3150fd4_v2.2.3_zg.bin", b"fw")
        zf.writestr("tool/mcu_upgrade", b"tool")



class _FakeVisibleWidget:
    def __init__(self):
        self.visible = None
        self._text = ""

    def setVisible(self, visible):
        self.visible = visible

    def setText(self, text):
        self._text = text

    def text(self):
        return self._text


class _FakeCheckBox:
    def __init__(self, checked=True):
        self.checked = checked
        self.visible = None
        self.enabled = None

    def isChecked(self):
        return self.checked

    def setVisible(self, visible):
        self.visible = visible

    def setEnabled(self, enabled):
        self.enabled = enabled


def test_ota_page_log_title_uses_display_command():
    page = OtaPage.__new__(OtaPage)
    page.current_spec = CommandSpec(
        "线刷预检",
        "set -euo pipefail\n" + "echo hidden\n" * 20,
        display_command="执行：线刷预检（小狗二代 S100）",
    )

    assert page.display_command_for_log() == "执行：线刷预检（小狗二代 S100）"


def test_ota_page_log_title_defaults_to_spec_title():
    page = OtaPage.__new__(OtaPage)
    page.current_spec = CommandSpec("执行 OTA 升级", "python3 -m dog_remote_tool.modules.ota.backend run -p bot")

    assert page.display_command_for_log() == "执行 OTA 升级"


def test_ota_rsync_progress_is_rewritten_for_user_log():
    line = "  1,234,567  42%   8.50MB/s    0:00:10 (xfr#1, to-chk=0/1)\r"

    assert ota_backend_runner._format_rsync_progress_line(line) == "[INFO] [upload] 上传进度: 42% 8.50MB/s\n"


def test_ota_rsync_progress_suppresses_file_list_noise():
    assert ota_backend_runner._format_rsync_progress_line("sending incremental file list\n") == ""
    assert ota_backend_runner._format_rsync_progress_line("robots_dog_msgs_0.9.0_aarch64_humble_Linux.deb\n") == ""
    assert ota_backend_runner._format_rsync_progress_line("              0   0%    0.00kB/s    0:00:00\r") == ""


def test_ota_rsync_stream_dedupes_same_percent(capsys, monkeypatch):
    class FakeProcess:
        stdin = None
        stdout = iter(
            [
                "sending incremental file list\n",
                "robots_dog_msgs_0.9.0_aarch64_humble_Linux.deb\n",
                "      4,509,696 100%   34.71MB/s    0:00:00\r",
                "      4,509,696 100%   22.71MB/s    0:00:00\r",
            ]
        )

        def wait(self):
            return 0

    monkeypatch.setattr(ota_backend_runner.subprocess, "Popen", lambda *_args, **_kwargs: FakeProcess())

    ota_backend_runner.run_stream(["rsync", "src", "dst"])

    output = capsys.readouterr().out
    assert output.count("上传进度: 100%") == 1
    assert "sending incremental file list" not in output
    assert "robots_dog_msgs_0.9.0_aarch64_humble_Linux.deb" not in output


def test_upload_small_package_does_not_repeat_local_package_summary(tmp_path, monkeypatch):
    package = tmp_path / "robots_dog_msgs_0.9.0_aarch64_humble_Linux.deb"
    _write_test_deb(package, package="robots_dog_msgs", version="0.9.0")
    target = ota_backend.TARGETS["zgnx"]
    messages = []

    monkeypatch.setattr(ota_backend, "log", messages.append)
    monkeypatch.setattr(ota_backend, "create_remote_dir", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(ota_backend, "remote_supports_rsync", lambda _target: False)
    monkeypatch.setattr(
        ota_backend,
        "upload_file",
        lambda _target, src, remote_dir, *, remote_has_rsync=None: f"{remote_dir}/{src.name}",
    )

    ota_backend.upload_small_package(target, package, "/home/robot/ota")

    assert not any(message.startswith("[local] 小包路径:") for message in messages)


def test_ota_human_bytes_keeps_binary_units_and_precision():
    assert ota_package_utils.human_bytes(512) == "512 B"
    assert ota_package_utils.human_bytes(1536) == "1.50 KiB"


def test_ota_package_release_name_strips_archive_suffixes():
    assert ota_package_utils.package_release_name(Path("606002963WCB.tar.gz")) == "606002963WCB"
    assert ota_package_utils.package_release_name(Path("606002963WCB.zip")) == "606002963WCB"
    assert ota_package_utils.package_release_name(Path("606002963WCB.tgz")) == "606002963WCB"
    assert ota_package_utils.package_release_name(Path("606002963WCB.img")) == "606002963WCB"


def test_ota_flash_progress_parser_accepts_xburn_and_sparse_lines():
    assert parse_flash_progress("[PROGRESS] Board 1 burn progress 53.8%") == 53.8
    assert parse_flash_progress("Sending sparse '0x0' 50/109 (114684 KB) OKAY") == 26.0 + (50 / 109) * 59.0
    assert parse_flash_progress("Writing '0x0' OKAY") is None


def test_ota_page_dangerous_flash_uses_single_confirm(monkeypatch):
    page = OtaPage.__new__(OtaPage)
    page.current_spec = CommandSpec("执行线刷", "echo flash", dangerous=True)
    page.package = _FakeText("/tmp/zg_s100_v0.0.1.tar.gz")
    page.runner = _FakeRunner(task_id=7)
    page.current_ota_target = lambda: ota.target_for_profile(get_product("xg2_s100"))
    page.display_command_for_log = lambda: "执行：线刷升级（小狗二代 S100）"
    questions = []

    def fake_question(*args):
        questions.append(args)
        return QMessageBox.Yes

    monkeypatch.setattr(QMessageBox, "question", fake_question)

    assert OtaPage.run_current(page) is True
    assert len(questions) == 1
    assert len(page.runner.run_calls) == 1


class _FakeProcess:
    def __init__(self):
        self.readyReadStandardOutput = _FakeSignal()
        self.finished = _FakeSignal()
        self.started = False

    def start(self):
        self.started = True


class _FakeSlot:
    def __init__(self, running=False, output="", read_result=False):
        self.running = running
        self.start_calls = []
        self.finish_output = output
        self.finish_calls = []
        self.read_result = read_result
        self.read_calls = []
        self.stop_calls = 0
        self.process = _FakeProcess()

    def is_running(self):
        return self.running

    def start_bash(self, command):
        self.running = True
        self.start_calls.append(command)
        return self.process, 7

    def start_spec(self, spec):
        return self.start_bash(spec.command)

    def read_available_output(self, process, request_id):
        self.read_calls.append((process, request_id))
        return self.read_result

    def finish(self, process, request_id):
        self.finish_calls.append((process, request_id))
        self.running = False
        return self.finish_output

    def stop(self):
        self.stop_calls += 1
        self.running = False


class _FakeOtaTarget:
    def __init__(self, family="rk3588", *, is_flash=False):
        self.key = family
        self.family = family
        self.label = "fake ota"
        self.user = "robot"
        self.host = "192.168.1.10"
        self.password = "bot"
        self.remote_dir = "~/ota"
        self.is_flash = is_flash
        self.accepted_package_types = ()


class _FakeOtaDeviceInfoPage:
    _default_target = object()

    def __init__(self, *, active=True, target=_default_target, running=False):
        self.page_active = active
        self.target = _FakeOtaTarget() if target is self._default_target else target
        self.device_info_slot = _FakeSlot(running)
        self.device_info_is_mcu_read = False
        self.mcu_reading = False
        self.device_info_messages = []
        self.summary_messages = []
        self.mcu_updates = 0
        self.device_info_updates = []
        self.refresh_calls = 0

    def current_ota_target(self):
        return self.target

    def device_info_spec(self):
        return CommandSpec("读取设备信息", "device-info")

    def mcu_maintenance_info_spec(self):
        return CommandSpec("读取 MCU 版本", "mcu-info")

    def _set_device_info_message(self, message):
        self.device_info_messages.append(message)

    def _set_summary_message(self, message):
        self.summary_messages.append(message)

    def update_mcu_table(self, *args):
        self.mcu_updates += 1

    def update_device_info(self, output, *, update_summary=True):
        self.device_info_updates.append((output, update_summary))

    def read_device_info_output(self, process, request_id):
        return OtaPage.read_device_info_output(self, process, request_id)

    def device_info_finished(self, process, request_id, exit_code):
        return OtaPage.device_info_finished(self, process, request_id, exit_code)

    def refresh_device_info(self, *, mcu_maintenance=False):
        self.refresh_calls += 1
        return OtaPage.refresh_device_info(self, mcu_maintenance=mcu_maintenance)

    def _stop_device_info_process(self):
        return OtaPage._stop_device_info_process(self)

    def _deactivate_device_info_polling(self):
        return OtaPage._deactivate_device_info_polling(self)


def test_ota_run_current_warns_when_runner_rejects_start(monkeypatch):
    page = _FakeOtaRunPage()
    warnings = []

    monkeypatch.setattr(QMessageBox, "warning", lambda *args: warnings.append(args))

    started = OtaPage.run_current(page)

    assert started is False
    assert len(page.runner.run_calls) == 1
    assert len(warnings) == 1
    assert warnings[0][1] == "任务未启动"


def test_ota_action_methods_return_run_current_result():
    upgrade_page = _FakeOtaActionPage(run_result=False)
    precheck_page = _FakeOtaActionPage(run_result=True)

    assert OtaPage.run_upgrade(upgrade_page) is False
    assert upgrade_page.current_spec.title == "执行 OTA 升级"
    assert upgrade_page.run_calls == 1

    assert OtaPage.run_precheck(precheck_page) is True
    assert precheck_page.current_spec.title == "OTA 预检"
    assert precheck_page.run_calls == 1


def test_ota_refresh_page_stop_button_updates_button_state_text_and_tooltip():
    locked = _FakeOtaStopPage(running=True, stop_locked=True)

    OtaPage.refresh_page_stop_button(locked)

    assert locked.stop_task_btn.enabled is False
    assert locked.stop_task_btn.text() == "刷机锁定"
    assert locked.stop_task_btn.toolTip() == "已进入正式刷写阶段，本地停止已锁定。"

    running = _FakeOtaStopPage(running=True)

    OtaPage.refresh_page_stop_button(running)

    assert running.stop_task_btn.enabled is True
    assert running.stop_task_btn.text() == "停止任务"
    assert running.stop_task_btn.toolTip() == "停止当前本地执行任务；进入正式刷写阶段后会锁定。"

    idle = _FakeOtaStopPage()

    OtaPage.refresh_page_stop_button(idle)

    assert idle.stop_task_btn.enabled is False
    assert idle.stop_task_btn.text() == "无运行任务"
    assert idle.stop_task_btn.toolTip() == "当前没有正在运行的任务。"


def test_ota_entry_monitor_does_not_require_package_validation():
    page = _FakeOtaActionPage(validate=False, run_result=True)
    page.current_ota_target = lambda: _FakeOtaTarget("s100_flash", is_flash=True)

    assert OtaPage.run_entry_monitor(page) is True
    assert page.current_spec.title == "S100 刷写入口观察"
    assert page.run_calls == 1


def test_ota_action_methods_return_false_when_package_validation_fails():
    page = _FakeOtaActionPage(validate=False)

    assert OtaPage.run_upgrade(page) is False
    assert page.current_spec is None
    assert page.run_calls == 0

    assert OtaPage.run_precheck(page) is False
    assert page.current_spec is None
    assert page.run_calls == 0


def test_ota_choose_package_returns_selection_result():
    page = _FakeOtaChoosePage()
    page._choose_package_path = lambda: ""

    assert OtaPage.choose_package(page) is False
    assert page.package.text() == ""
    assert page.info_updates == 0

    page._choose_package_path = lambda: "/tmp/ota.zip"

    assert OtaPage.choose_package(page) is True
    assert page.package.text() == "/tmp/ota.zip"
    assert page.info_updates == 1


def test_ota_package_dialog_filter_includes_small_packages():
    assert "*.deb" in PACKAGE_DIALOG_FILTER
    assert "*.whl" in PACKAGE_DIALOG_FILTER


def test_large_3588_archive_selection_does_not_parse_mcu_versions(tmp_path, monkeypatch):
    package = tmp_path / "606003065CCA.tar.gz"
    with package.open("wb") as stream:
        stream.truncate(513 * 1024 * 1024)

    class FakeMcuPage(ota_device_info.OtaDeviceInfoMixin):
        def __init__(self):
            self.mcu_info_grid = object()
            self.package = _FakeText(str(package))
            self.current_mcu_values = {}
            self.mcu_reading = False
            self.rows = []

        def current_ota_target(self):
            target = _FakeOtaTarget("rk3588")
            target.key = "xg_l1_point_3588"
            return target

        def _nx_mcu_option_visible(self, _target):
            return False

        def _set_mcu_rows(self, rows):
            self.rows = rows

    def fail_deep_parse(*_args, **_kwargs):
        raise AssertionError("large package selection must not parse MCU versions")

    monkeypatch.setattr(ota_package_display, "package_mcu_target_versions", fail_deep_parse)
    monkeypatch.setattr(ota, "package_mcu_target_versions", fail_deep_parse)

    page = FakeMcuPage()
    page.update_mcu_table()

    assert page.rows
    assert {row[2] for row in page.rows} == {"预检时校验"}


def test_ota_choose_deploy_dir_returns_selection_result():
    page = _FakeOtaChoosePage()
    page._choose_deploy_dir_path = lambda: ""

    assert OtaPage.choose_deploy_dir(page) is False
    assert page.package.text() == ""
    assert page.info_updates == 0

    page._choose_deploy_dir_path = lambda: "/tmp/deploy"

    assert OtaPage.choose_deploy_dir(page) is True
    assert page.package.text() == "/tmp/deploy"
    assert page.info_updates == 1


def test_ota_mcu_visibility_only_for_3588_ota_targets():
    page = OtaPage.__new__(OtaPage)
    page.mcu_read_btn = _FakeVisibleWidget()
    page.mcu_section = _FakeVisibleWidget()
    page.device_info_hint = _FakeVisibleWidget()
    page.target = _FakeOtaTarget(family="rk3588", is_flash=False)
    page.current_ota_target = lambda: page.target

    assert OtaPage._update_mcu_visibility(page) is True
    assert page.mcu_read_btn.visible is True
    assert page.mcu_section.visible is True
    assert "MCU 当前版本需要手动读取" in page.device_info_hint.text()

    page.target = _FakeOtaTarget(family="s100_flash", is_flash=True)

    assert OtaPage._update_mcu_visibility(page) is False
    assert page.mcu_read_btn.visible is False
    assert page.mcu_section.visible is False
    assert "不需要 MCU 版本对比" in page.device_info_hint.text()

    page.target = _FakeOtaTarget(family="nx", is_flash=False)

    assert OtaPage._update_mcu_visibility(page) is False
    assert page.mcu_read_btn.visible is False
    assert page.mcu_section.visible is False


def test_ota_refresh_device_info_returns_start_result():
    inactive = _FakeOtaDeviceInfoPage(active=False)

    assert OtaPage.refresh_device_info(inactive) is False
    assert inactive.device_info_slot.start_calls == []

    unsupported = _FakeOtaDeviceInfoPage(target=None)

    assert OtaPage.refresh_device_info(unsupported) is False
    assert unsupported.device_info_messages == ["当前设备不支持 OTA/线刷"]

    busy = _FakeOtaDeviceInfoPage(running=True)

    assert OtaPage.refresh_device_info(busy) is False
    assert busy.device_info_slot.start_calls == []

    page = _FakeOtaDeviceInfoPage()

    assert OtaPage.refresh_device_info(page) is True
    assert page.device_info_is_mcu_read is False
    assert page.summary_messages == ["读取中..."]
    assert page.device_info_slot.start_calls == ["device-info"]
    assert page.device_info_slot.process.started is True


def test_ota_device_info_callbacks_return_accept_result():
    read_page = _FakeOtaDeviceInfoPage()
    read_page.device_info_slot = _FakeSlot(read_result=True)

    assert OtaPage.read_device_info_output(read_page, read_page.device_info_slot.process, request_id=8) is True
    assert read_page.device_info_slot.read_calls == [(read_page.device_info_slot.process, 8)]

    read_page.device_info_slot.read_result = False

    assert OtaPage.read_device_info_output(read_page, read_page.device_info_slot.process, request_id=9) is False

    stale = _FakeOtaDeviceInfoPage()
    stale.device_info_slot = _FakeSlot(output=None)

    assert OtaPage.device_info_finished(stale, stale.device_info_slot.process, request_id=10, exit_code=0) is False

    success = _FakeOtaDeviceInfoPage()
    success.device_info_slot = _FakeSlot(output="device-info")

    assert OtaPage.device_info_finished(success, success.device_info_slot.process, request_id=11, exit_code=0) is True
    assert success.device_info_is_mcu_read is False
    assert success.device_info_updates == [("device-info", True)]

    failed = _FakeOtaDeviceInfoPage()
    failed.device_info_slot = _FakeSlot(output="ssh failed")

    assert OtaPage.device_info_finished(failed, failed.device_info_slot.process, request_id=12, exit_code=1) is True
    assert failed.summary_messages == ["读取失败"]

    mcu_failed = _FakeOtaDeviceInfoPage()
    mcu_failed.device_info_is_mcu_read = True
    mcu_failed.mcu_reading = True
    mcu_failed.device_info_slot = _FakeSlot(output="mcu failed")

    assert OtaPage.device_info_finished(mcu_failed, mcu_failed.device_info_slot.process, request_id=13, exit_code=1) is True
    assert mcu_failed.device_info_is_mcu_read is False
    assert mcu_failed.mcu_reading is False
    assert mcu_failed.mcu_updates == 1


def test_ota_lifecycle_stops_device_info_polling():
    page = _FakeOtaDeviceInfoPage(active=True, running=True)
    page.device_info_is_mcu_read = True
    page.mcu_reading = True

    OtaPage.deactivate_page(page)

    assert page.page_active is False
    assert page.device_info_slot.running is False
    assert page.device_info_slot.stop_calls == 1
    assert page.device_info_is_mcu_read is False
    assert page.mcu_reading is False

    page.page_active = True
    page.device_info_is_mcu_read = True
    page.mcu_reading = True

    OtaPage.shutdown_processes(page)

    assert page.page_active is False
    assert page.device_info_slot.stop_calls == 2
    assert page.device_info_is_mcu_read is False
    assert page.mcu_reading is False


def test_ota_activate_page_does_not_repeat_device_info_probe(monkeypatch):
    single_shots = []

    def fake_single_shot(delay, callback):
        single_shots.append(delay)
        callback()

    monkeypatch.setattr("dog_remote_tool.ui.pages.ota.page.QTimer.singleShot", fake_single_shot)
    page = _FakeOtaDeviceInfoPage(active=False)

    OtaPage.activate_page(page)

    assert page.page_active is True
    assert single_shots == [200]
    assert page.refresh_calls == 1
    assert len(page.device_info_slot.start_calls) == 1

    OtaPage.activate_page(page)

    assert single_shots == [200]
    assert page.refresh_calls == 1
    assert len(page.device_info_slot.start_calls) == 1


def test_ota_mcu_maintenance_read_returns_start_result(monkeypatch):
    questions = []
    monkeypatch.setattr(QMessageBox, "question", lambda *args: questions.append(args) or QMessageBox.Yes)
    warnings = []
    monkeypatch.setattr(QMessageBox, "warning", lambda *args: warnings.append(args))
    infos = []
    monkeypatch.setattr(QMessageBox, "information", lambda *args: infos.append(args))

    unsupported = _FakeOtaDeviceInfoPage(target=_FakeOtaTarget(family="nx"))

    assert OtaPage.run_mcu_maintenance_read(unsupported) is False
    assert warnings and warnings[0][1] == "当前设备不支持"
    assert unsupported.device_info_slot.start_calls == []

    busy = _FakeOtaDeviceInfoPage(running=True)

    assert OtaPage.run_mcu_maintenance_read(busy) is False
    assert infos and infos[0][1] == "正在读取"
    assert busy.device_info_slot.start_calls == []

    monkeypatch.setattr(QMessageBox, "question", lambda *args: QMessageBox.Cancel)
    cancelled = _FakeOtaDeviceInfoPage()

    assert OtaPage.run_mcu_maintenance_read(cancelled) is False
    assert cancelled.device_info_slot.start_calls == []

    monkeypatch.setattr(QMessageBox, "question", lambda *args: QMessageBox.Yes)
    page = _FakeOtaDeviceInfoPage()

    assert OtaPage.run_mcu_maintenance_read(page) is True
    assert page.device_info_is_mcu_read is True
    assert page.mcu_reading is True
    assert page.mcu_updates == 1
    assert page.device_info_slot.start_calls == ["mcu-info"]
    assert page.device_info_slot.process.started is True


def test_rk3588_zip_package_is_detected(tmp_path):
    package = tmp_path / "zg_rk3588_ota_v0.2.4.zip"
    with zipfile.ZipFile(package, "w") as zf:
        zf.writestr(
            "package_info.json",
            json.dumps(
                {
                    "system": {"image_regex": "image/.*\\.img$"},
                    "modules": [
                        {
                            "name": "power_control",
                            "package_regex": "firmware/power.*\\.bin$",
                            "tool_regex": "tool/mcu_upgrade_tool.*$",
                        }
                    ],
                }
            ),
        )
        zf.writestr("image/zg_rk3588_v0.2.4.img", b"RKFW" + b"\0" * 16)
        zf.writestr("firmware/power_zg_v1.0.3.bin", b"fw")
        zf.writestr("tool/mcu_upgrade_tool", b"tool")

    assert ota_backend.package_family(package) == "rk3588"
    assert ota_backend.inspect_rk3588_package(package) == ("image/zg_rk3588_v0.2.4.img", 20)
    assert ota.package_type(str(package)) == "rk3588"
    assert ota.package_version(str(package)) == "v0.2.4"
    manifest = ota_backend.package_manifest(package)
    assert manifest.runnable_module_count == 1
    assert ota.package_summary(str(package)).endswith("1 个固件模块均带工具")


def test_deb_file_is_identified_as_debian_package_not_nx_ota(tmp_path):
    package = tmp_path / "robot-runtime-nx-0.2.7-arm64.deb"
    _write_test_deb(package, package="robot-runtime-nx", version="0.2.7", architecture="arm64")

    assert ota.package_type_hint(str(package)) == "deb_package"
    assert ota.package_type(str(package)) == "deb_package"
    assert ("Package", "robot-runtime-nx") in ota.package_detail_rows(str(package))
    assert "Debian 小包：robot-runtime-nx 0.2.7" in ota.package_light_summary(str(package))


def test_deb_summary_does_not_read_entire_package(tmp_path, monkeypatch):
    package = tmp_path / "navigation_0.7.2_arm64.deb"
    _write_test_deb(package, package="navigation", version="0.7.2", architecture="arm64")

    def fail_read_bytes(self):
        if self == package:
            raise AssertionError("deb summary must stream control metadata instead of reading the whole package")
        return original_read_bytes(self)

    original_read_bytes = Path.read_bytes
    monkeypatch.setattr(Path, "read_bytes", fail_read_bytes)

    assert "Debian 小包：navigation 0.7.2" in ota.package_light_summary(str(package))


def test_whl_file_is_identified_as_python_package(tmp_path):
    package = tmp_path / "pyserial-3.5-py2.py3-none-any.whl"
    package.write_bytes(b"wheel")

    assert ota.package_type_hint(str(package)) == "whl_package"
    assert ota.package_type(str(package)) == "whl_package"
    assert ("Package", "pyserial") in ota.package_detail_rows(str(package))
    assert ("Version", "3.5") in ota.package_detail_rows(str(package))
    assert "Python wheel 小包：pyserial 3.5" in ota.package_light_summary(str(package))


def test_deploy_dir_lists_deb_package_versions(tmp_path):
    deploy = tmp_path / "Hermes_M_v0.1.0"
    deploy.mkdir()
    (deploy / "deploy.sh").write_text("#!/bin/bash\nsudo dpkg -i *.deb\n", encoding="utf-8")
    _write_test_deb(deploy / "navigation_0.7.2_arm64.deb", package="navigation", version="0.7.2", architecture="arm64")
    _write_test_deb(
        deploy / "robots_dog_msgs_0.8.6_aarch64_humble_Linux.deb",
        package="robots_dog_msgs",
        version="0.8.6",
        architecture="arm64",
    )

    assert ota.package_type_hint(str(deploy)) == "deb_deploy"
    assert ota.package_type(str(deploy)) == "deb_deploy"
    rows = ota.package_detail_rows(str(deploy))

    assert ("包类型", "小包部署目录") in rows
    assert ("小包数量", "2 个") in rows
    assert ("小包 · navigation", "0.7.2 (arm64)") in rows
    assert ("小包 · robots_dog_msgs", "0.8.6 (arm64)") in rows
    assert "小包部署目录：2 个 deb" in ota.package_light_summary(str(deploy))


def test_small_package_archive_is_identified_after_ota_checks(tmp_path):
    package = tmp_path / "Hermes_M_v0.1.0_deploy.zip"
    with zipfile.ZipFile(package, "w") as zf:
        zf.writestr("Hermes_M_v0.1.0/deploy.sh", "dpkg -i *.deb\n")
        zf.writestr("Hermes_M_v0.1.0/navigation_0.7.2_arm64.deb", b"deb")
        zf.writestr("Hermes_M_v0.1.0/pyserial-3.5-py2.py3-none-any.whl", b"wheel")

    assert ota.package_type(str(package)) == "small_deploy_archive"
    assert ota.package_type_hint(str(package)) == "small_deploy_archive"
    rows = ota.package_detail_rows(str(package))

    assert ("包类型", "小包压缩包") in rows
    assert ("小包数量", "2 个") in rows
    assert ("内容", "1 个 deb / 1 个 whl") in rows
    assert "小包压缩包：1 个 deb / 1 个 whl" in ota.package_light_summary(str(package))


def test_rk3588_ota_archive_with_deb_member_is_not_small_package(tmp_path):
    package = tmp_path / "zg_rk3588_ota_v0.2.4.zip"
    with zipfile.ZipFile(package, "w") as zf:
        zf.writestr(
            "package_info.json",
            json.dumps({"system": {"image_regex": "image/.*\\.img$"}, "modules": []}),
        )
        zf.writestr("image/zg_rk3588_v0.2.4.img", b"RKFW" + b"\0" * 16)
        zf.writestr("extras/navigation_0.7.2_arm64.deb", b"deb")

    assert ota.package_type(str(package)) == "rk3588"
    assert ota.package_type_hint(str(package)) == "rk3588"
    assert "小包压缩包" not in ota.package_light_summary(str(package))
    assert ("包类型", "3588 包") in ota.package_detail_rows(str(package))


def test_large_unknown_archive_hint_does_not_deep_scan(tmp_path, monkeypatch):
    package = tmp_path / "905003065CDA.tar.gz"
    with package.open("wb") as stream:
        stream.truncate(513 * 1024 * 1024)

    def fail_deep_scan(*_args, **_kwargs):
        raise AssertionError("large archive selection must stay lightweight")

    monkeypatch.setattr(ota_package_display.deb_deploy, "is_small_package_archive", fail_deep_scan)
    monkeypatch.setattr(ota_package_display, "package_manifest", fail_deep_scan)

    assert ota.package_type_hint(str(package)) == ""
    assert ("包类型", "待校验") in ota.package_selection_detail_rows(str(package))
    assert "结构：待升级前完整校验" in ota.package_light_summary(str(package))


def test_validate_package_accepts_deploy_dir_for_remote_ota_target(tmp_path):
    deploy = tmp_path / "Hermes_M_v0.1.0"
    deploy.mkdir()
    (deploy / "deploy.sh").write_text("#!/bin/bash\nsudo dpkg -i *.deb\n", encoding="utf-8")
    _write_test_deb(deploy / "navigation_0.7.2_arm64.deb", package="navigation", version="0.7.2")
    page = OtaPage.__new__(OtaPage)
    page.package = _FakeText(str(deploy))
    page.current_ota_target = lambda: _FakeOtaTarget("nx")

    assert OtaPage.validate_package_for_target(page) is True


def test_validate_package_accepts_small_package_archive_for_remote_ota_target(tmp_path):
    package = tmp_path / "Hermes_M_v0.1.0_deploy.zip"
    with zipfile.ZipFile(package, "w") as zf:
        zf.writestr("Hermes_M_v0.1.0/navigation_0.7.2_arm64.deb", b"deb")
    page = OtaPage.__new__(OtaPage)
    page.package = _FakeText(str(package))
    page.current_ota_target = lambda: _FakeOtaTarget("rk3588")

    assert OtaPage.validate_package_for_target(page) is True


def test_validate_package_rejects_deploy_dir_for_flash_target(tmp_path, monkeypatch):
    deploy = tmp_path / "Hermes_M_v0.1.0"
    deploy.mkdir()
    _write_test_deb(deploy / "navigation_0.7.2_arm64.deb", package="navigation", version="0.7.2")
    page = OtaPage.__new__(OtaPage)
    page.package = _FakeText(str(deploy))
    page.current_ota_target = lambda: _FakeOtaTarget("s100_flash", is_flash=True)
    warnings = []

    monkeypatch.setattr(QMessageBox, "warning", lambda *args: warnings.append(args))

    assert OtaPage.validate_package_for_target(page) is False
    assert warnings[0][1] == "升级包格式不支持"


def test_validate_package_rejects_small_package_archive_for_flash_target(tmp_path, monkeypatch):
    package = tmp_path / "Hermes_M_v0.1.0_deploy.zip"
    with zipfile.ZipFile(package, "w") as zf:
        zf.writestr("Hermes_M_v0.1.0/navigation_0.7.2_arm64.deb", b"deb")
    page = OtaPage.__new__(OtaPage)
    page.package = _FakeText(str(package))
    page.current_ota_target = lambda: _FakeOtaTarget("s100_flash", is_flash=True)
    warnings = []

    monkeypatch.setattr(QMessageBox, "warning", lambda *args: warnings.append(args))

    assert OtaPage.validate_package_for_target(page) is False
    assert warnings[0][1] == "线刷包不匹配"


def test_rk3588_motion_detection_does_not_depend_on_zip_order(tmp_path):
    package = tmp_path / "xg_rk3588_ota_v0.2.4.zip"
    with zipfile.ZipFile(package, "w") as zf:
        zf.writestr("image/xg_rk3588_v0.2.4.img", b"RKFW" + b"\0" * 16)
        zf.writestr("config/motion.yaml", "motion-control: robot_xgw_profile\n")

    assert ota.package_motion_type(str(package)) == "wheel"


def test_xg3588_motion_detection_uses_package_prefix_for_point_and_wheel(tmp_path):
    point_package = tmp_path / "606003065CCA.tar.gz"
    point_payload = tmp_path / "point"
    point_payload.mkdir()
    (point_payload / "AIO-3588SJD4_Ubuntu_260609.img").write_bytes(b"RKFW" + b"\0" * 16)
    (point_payload / "606003065CCA.yaml").write_text(
        'motion-control:\n  type: "deb"\n  source: "motion-control_0.6.0_arm64.deb"\n',
        encoding="utf-8",
    )
    with tarfile.open(point_package, "w:gz") as tf:
        tf.add(point_payload, arcname="606003065CCA")

    wheel_package = tmp_path / "626003065CCA.tar.gz"
    wheel_payload = tmp_path / "wheel"
    wheel_payload.mkdir()
    (wheel_payload / "AIO-3588SJD4_Ubuntu_260609.img").write_bytes(b"RKFW" + b"\0" * 16)
    (wheel_payload / "626003065CCA.yaml").write_text(
        'motion-control:\n  type: "deb"\n  source: "motion-control_0.6.0_arm64.deb"\n',
        encoding="utf-8",
    )
    with tarfile.open(wheel_package, "w:gz") as tf:
        tf.add(wheel_payload, arcname="626003065CCA")

    assert ota.package_motion_type(str(point_package)) == "point"
    assert ota.package_motion_type(str(wheel_package)) == "wheel"


def test_xg3588_local_validation_rejects_point_wheel_mismatch(tmp_path, monkeypatch):
    package = tmp_path / "626003065CCA.tar.gz"
    payload = tmp_path / "pkg"
    payload.mkdir()
    (payload / "AIO-3588SJD4_Ubuntu_260609.img").write_bytes(b"RKFW" + b"\0" * 16)
    (payload / "626003065CCA.yaml").write_text("", encoding="utf-8")
    with tarfile.open(package, "w:gz") as tf:
        tf.add(payload, arcname="626003065CCA")

    target = _FakeOtaTarget("rk3588")
    target.key = "xg_l1_point_3588"
    errors = []
    monkeypatch.setattr(ota_backend_runner, "log", lambda _message: None)

    def fake_die(message):
        errors.append(message)
        raise RuntimeError(message)

    monkeypatch.setattr(ota_backend_runner, "die", fake_die)

    try:
        ota_local_validation.validate_local_inputs(target, package, None)
    except RuntimeError:
        pass

    assert errors
    assert "目标 点足 / 包内 轮足" in errors[0]


def test_zg3588_full_zip_is_complete_and_runnable_with_factory_mapping(tmp_path):
    package = tmp_path / "zg_rk3588_ota_v0.2.4.zip"
    modules = [
        ("imu", "firmware/imu_board_release_v15.bin", "tool/mcu_upgrade_tool"),
        ("actuator_joint", "firmware/motorcontrol_SMGRB_P85MAXS_ZYV4.bin", "tool/actuator_upgrade_tool"),
        ("actuator_wheel", "firmware/motorcontrol_SMGRB_W190S_ZYV4.bin", "tool/actuator_upgrade_tool"),
        ("uart2can", "firmware/uart2canfd_v1.0.2.bin", "tool/uart2can_upgrade_tool"),
        ("hot_swap", "firmware/hot_swap_board_v0.2.0.bin", "tool/mcu_upgrade_tool"),
        ("power_control", "firmware/power_zg_v1.0.3.bin", "tool/mcu_upgrade_tool"),
        ("battery", "firmware/I0930B_APP_1026930B_v1026.bin", "tool/mcu_upgrade_tool"),
    ]
    with zipfile.ZipFile(package, "w") as zf:
        zf.writestr("image/zg_rk3588_v0.2.4.img", b"RKFW" + b"\0" * 16)
        zf.writestr("tool/mcu_upgrade_tool", b"tool")
        zf.writestr("tool/actuator_upgrade_tool", b"tool")
        zf.writestr("tool/uart2can_upgrade_tool", b"tool")
        zf.writestr(
            "package_info.json",
            json.dumps(
                {
                    "system": {"image_regex": "image/.*\\.img$"},
                    "modules": [
                        {
                            "name": name,
                            "package_regex": firmware.replace(".", "\\.").replace("ZYV4", ".*?"),
                            "tool_regex": tool.replace(".", "\\.") + ".*$",
                        }
                        for name, firmware, tool in modules
                    ],
                }
            ),
        )
        for _, firmware, _ in modules:
            zf.writestr(firmware, b"fw")

    manifest = ota_backend.package_manifest(package)
    coverage = ota_backend.rk3588_firmware_coverage(package, manifest)

    assert len(manifest.modules) == 7
    assert manifest.runnable_module_count == 7
    assert ota_backend.is_zg3588_full_zip_manifest(manifest)
    assert "中狗 3588 全量固件齐全" in ota.package_summary(str(package))
    assert len(coverage.supported) == 7
    assert not coverage.unsupported
    assert "中狗 3588 ZIP 包已包含系统镜像、7 个固件模块和随包工具" in coverage.note
    assert "ZsmFactory v0.2.2 反编译流程已确认" in coverage.note
    assert "battery[1]" in coverage.note
    assert "battery[2]" in coverage.note


def test_zg3588_remote_script_matches_factory_battery_flow():
    script = ota_backend.rk_remote_script()

    assert "for battery_id in 1 2" in script
    assert "fuser -k /dev/ttyCH9344USB6" in script
    assert '"$battery" -b "$battery_id"' in script


def test_small_deploy_commands_route_to_backend():
    precheck = ota.small_precheck_command("zg3588", "192.168.234.1", "robot", "bot", "/userdata/upgrade", "/tmp/pkg.whl")
    deploy = ota.small_deploy_command("zg3588", "192.168.234.1", "robot", "bot", "/userdata/upgrade", "/tmp/pkg.whl")

    assert "small-precheck" in precheck.command
    assert precheck.title == "小包部署预检"
    assert "small-deploy" in deploy.command
    assert deploy.title == "执行小包部署"
    assert deploy.dangerous


def test_small_deploy_remote_script_matches_factory_deb_whl_flow():
    script = ota_backend.small_deploy_remote_script()

    assert "dpkg -i --force-all" in script
    assert "python3 -m pip install --upgrade --no-index --find-links" in script
    assert "systemctl stop robot-launch.service" in script
    assert "systemctl restart robot-launch.service" in script


def test_small_archive_extract_script_uses_stdlib_and_flattens_packages():
    script = ota_backend.small_archive_extract_script()

    assert "zipfile.ZipFile" in script
    assert "tarfile.open" in script
    assert "posixpath.basename" in script
    assert 'lower.endswith(".deb") or lower.endswith(".whl")' in script


def test_resolve_small_package_accepts_small_package_archive(tmp_path):
    package = tmp_path / "Hermes_M_v0.1.0_deploy.zip"
    with zipfile.ZipFile(package, "w") as zf:
        zf.writestr("Hermes_M_v0.1.0/navigation_0.7.2_arm64.deb", b"deb")

    assert ota_backend.resolve_small_package(str(package)) == package.resolve()


def test_ota_page_routes_small_package_to_small_deploy_command(tmp_path, monkeypatch):
    package = tmp_path / "pyserial-3.5-py2.py3-none-any.whl"
    package.write_bytes(b"wheel")
    page = OtaPage.__new__(OtaPage)
    page.package = _FakeText(str(package))
    page.current_ota_target = lambda: _FakeOtaTarget("rk3588")
    calls = []

    monkeypatch.setattr(ota, "small_deploy_command", lambda *args: calls.append(args) or CommandSpec("执行小包部署", "small"))

    spec = ota_actions.OtaActionsMixin.upgrade_spec(page)

    assert spec.command == "small"
    assert calls


def test_zg3588_device_info_script_skips_mcu_for_plain_refresh():
    script = ota_remote_checks.device_info_script("/userdata/upgrade", "zg3588")

    assert "MCU_MAINTENANCE=0" in script
    assert "目标MCU:" not in script
    assert "当前MCU:" not in script
    assert "/opt/runtime/bin/mcu_upgrade -d /dev/ttyS1 -s -i" not in script
    assert "/opt/runtime/bin/actuator_tool --firmware-version all:1,2,3" not in script
    assert "/opt/runtime/bin/canfd_upgrade -s -d /dev/uart2canfd-can0" not in script


def test_device_info_script_supports_mcu_maintenance_mode():
    script = ota_remote_checks.device_info_script("~/ota", "xg_l1_point_3588", mcu_maintenance=True)

    assert "MCU_MAINTENANCE=1" in script
    assert "systemctl stop robot-launch.service" in script
    assert "目标MCU: 小狗3588" in script
    assert "/usr/local/bin/mcu_upgrade -d /dev/spidev0.0 -l 0 -j 2 -s" in script
    assert "systemctl start robot-launch.service" in script
    assert "/usr/local/bin/mcu_upgrade -d /dev/ttyS1 -i -s" in script


def test_device_info_script_reports_one_upgrade_space_field():
    script = ota_remote_checks.device_info_script("~/ota", "xg_l1_point_3588")

    assert "升级空间:" in script
    assert "根分区可用空间:" not in script
    assert "远程目录可用空间:" not in script
    assert "/userdata/update 可用空间:" not in script
    assert "/ota 可用空间:" not in script


def test_xg3588_remote_script_matches_known_jupdate_flow():
    script = ota_backend.rk_remote_script()

    assert "check_xg3588_soc" in script
    assert "/usr/local/bin/mcu_upgrade -d /dev/ttyS3 -p" in script
    assert '-d "$device" -l 0 -j 2 -s' in script
    assert '-d /dev/ttyS1 -i -f "$file"' in script
    assert '-d /dev/ttyS3 -f "$file"' in script
    assert "/usr/local/bin/mcu_upgrade -d /dev/ttyS3 -r 5" in script


def test_rk3588_tar_manifest_reports_firmware_without_tools(tmp_path):
    package = tmp_path / "606002963WCB.tar.gz"
    payload = tmp_path / "pkg"
    payload.mkdir()
    (payload / "AIO.img").write_bytes(b"RKFW" + b"\0" * 16)
    (payload / "motor.bin").write_bytes(b"fw")
    (payload / "606002963WCB.yaml").write_text(
        'motorcontrol:\n  type: "bin"\n  source: "motor.bin"\n  target: ""\n  version: "1.2.3"\n',
        encoding="utf-8",
    )
    with tarfile.open(package, "w:gz") as tf:
        tf.add(payload, arcname="606002963WCB")

    manifest = ota_backend.package_manifest(package)

    assert manifest.family == "rk3588"
    assert manifest.system_image == "606002963WCB/AIO.img"
    assert len(manifest.modules) == 1
    assert manifest.modules[0].runnable is False
    assert "依赖远端 mcu_upgrade 刷写" in ota.package_summary(str(package))
    assert ("包设备版本", "606002963WCB") in ota.package_detail_rows(str(package))
    assert ("固件 · motorcontrol", "1.2.3") in ota.package_detail_rows(str(package))
    assert ota.package_mcu_target_versions(str(package), "xg3588")["motorcontrol"] == "1.2.3"


def test_ui_package_manifest_cache_reuses_selected_package_parse(tmp_path, monkeypatch):
    package = tmp_path / "606002963WCB.tar.gz"
    payload = tmp_path / "pkg"
    payload.mkdir()
    (payload / "AIO.img").write_bytes(b"RKFW" + b"\0" * 16)
    (payload / "motor.bin").write_bytes(b"fw")
    (payload / "606002963WCB.yaml").write_text(
        'motorcontrol:\n  type: "bin"\n  source: "motor.bin"\n  target: ""\n  version: "1.2.3"\n',
        encoding="utf-8",
    )
    with tarfile.open(package, "w:gz") as tf:
        tf.add(payload, arcname="606002963WCB")

    original = ota_package_display.package_manifest
    calls = []
    ota_package_display._cached_ui_package_manifest.cache_clear()

    def wrapped(path):
        calls.append(path)
        return original(path)

    monkeypatch.setattr(ota_package_display, "package_manifest", wrapped)

    assert ota.package_detail_rows(str(package))
    assert ota.package_mcu_target_versions(str(package), "xg3588")["motorcontrol"] == "1.2.3"
    assert len(calls) == 1


def test_xg3588_tar_coverage_ignores_factory_bundled_non_ota_modules(tmp_path):
    package = tmp_path / "606002963WCB.tar.gz"
    payload = tmp_path / "pkg"
    payload.mkdir()
    (payload / "AIO-3588SJD4_Ubuntu_260424.img").write_bytes(b"RKFW" + b"\0" * 16)
    (payload / "606002963WCB.yaml").write_text(
        "\n".join(
            [
                'motorcontrol_SMGRB_P65R-152:\n  type: "bin"\n  source: "motorcontrol_SMGRB_P65R-152-1003-0305.bin"\n  target: ""\n  version: "152-1003"',
                'imu_board:\n  type: "bin"\n  source: "imu_board_release_e6645ab_V0.1.5.bin"\n  target: ""\n  version: "0.1.5"',
                'power_board:\n  type: "bin"\n  source: "power_board_release_3f5d170_v1.0.2.bin"\n  target: ""\n  version: "1.0.2"',
                'spline:\n  type: "bin"\n  source: "spline_release_56db3ba_v1.0.4.bin"\n  target: ""\n  version: "1.0.4"',
                'charge_board:\n  type: "bin"\n  source: "charge_board_release_c7f97fb_v1.0.1.bin"\n  target: ""\n  version: "1.0.1"',
                'battery:\n  type: "bin"\n  source: "JS_12S2P_V107_202506171800.bin"\n  target: ""\n  version: "12S2P_V107"',
            ]
        ),
        encoding="utf-8",
    )
    with tarfile.open(package, "w:gz") as tf:
        tf.add(payload, arcname="606002963WCB")

    manifest = ota_backend.package_manifest(package)
    coverage = ota_backend.rk3588_firmware_coverage(package, manifest)

    assert {module.name for module in coverage.supported} == {
        "motorcontrol_SMGRB_P65R-152",
        "imu_board",
        "power_board",
        "spline",
    }
    assert not coverage.unsupported
    assert "AgibotD1 v0.8.4 jupdate" in coverage.note
    assert "charge_board 与 battery 固件随产线包放置，常规 3588 OTA 不执行" in coverage.note


def test_package_firmware_summary_shows_target_versions(tmp_path):
    package = tmp_path / "zg_rk3588_ota_v0.2.4.zip"
    with zipfile.ZipFile(package, "w") as zf:
        zf.writestr("image/zg_rk3588_v0.2.4.img", b"RKFW" + b"\0" * 16)
        zf.writestr("tool/mcu_upgrade_tool", b"tool")
        zf.writestr(
            "package_info.json",
            json.dumps(
                {
                    "system": {"image_regex": "image/.*\\.img$"},
                    "modules": [
                        {
                            "name": "power_control",
                            "package_regex": "firmware/power_zg.*?\\.bin$",
                            "tool_regex": "tool/mcu_upgrade_tool.*$",
                        },
                        {
                            "name": "battery",
                            "package_regex": "firmware/I0930B_APP.*?\\.bin$",
                            "tool_regex": "tool/mcu_upgrade_tool.*$",
                        },
                    ],
                }
            ),
        )
        zf.writestr("firmware/power_zg_v1.0.3.bin", b"fw")
        zf.writestr("firmware/I0930B_APP_1026930B_v1026.bin", b"fw")

    summary = ota.package_firmware_summary(str(package))

    assert "目标固件" in summary
    assert "power_control: v1.0.3" in summary
    assert "battery: v1026" in summary


def test_nx_tar_package_still_detected(tmp_path):
    package = tmp_path / "zg_orin_nx_ota_v0.4.4.tar.gz"
    payload = tmp_path / "ota_package.tar"
    payload.write_bytes(b"nx-payload")
    with tarfile.open(package, "w:gz") as tf:
        tf.add(payload, arcname="ota_package.tar")

    assert ota_backend.package_family(package) == "nx"
    assert ota_backend.inspect_nx_package(package) == len(b"nx-payload")


def test_zgnx_zip_package_detects_nested_manifest_and_rtk_module(tmp_path):
    package = tmp_path / "zg_orin_nx_ota_v0.4.6.zip"
    payload = tmp_path / "ota_package.tar"
    payload.write_bytes(b"nx-payload")
    inner = tmp_path / "zg_orin_nx_v0.4.6_ota.tar.gz.tar.gz"
    with tarfile.open(inner, "w:gz") as tf:
        tf.add(payload, arcname="ota_package.tar")
    with zipfile.ZipFile(package, "w") as zf:
        zf.writestr(
            "zg_orin_nx_ota_v0.4.6/package_info.json",
            json.dumps(
                {
                    "system": {"image_regex": "image/.*\\.tar.gz$"},
                    "modules": [
                        {
                            "name": "rtk_mcu",
                            "package_regex": "firmware/rtk.*?\\.bin$",
                            "tool_regex": "tool/mcu_upgrade.*$",
                        }
                    ],
                }
            ),
        )
        zf.write(inner, "zg_orin_nx_ota_v0.4.6/image/zg_orin_nx_v0.4.6_ota.tar.gz.tar.gz")
        zf.writestr("zg_orin_nx_ota_v0.4.6/firmware/rtk_mcu_3150fd4_v2.2.3_zg.bin", b"fw")
        zf.writestr("zg_orin_nx_ota_v0.4.6/tool/mcu_upgrade", b"tool")

    assert ota_backend.package_family(package) == "nx"
    assert ota_backend.inspect_nx_package(package) == len(b"nx-payload")
    manifest = ota_backend.package_manifest(package)

    assert manifest.family == "nx"
    assert manifest.system_image == "zg_orin_nx_ota_v0.4.6/image/zg_orin_nx_v0.4.6_ota.tar.gz.tar.gz"
    assert manifest.runnable_module_count == 1
    assert manifest.modules[0].name == "rtk_mcu"
    assert "1 个固件模块均带工具" in ota.package_summary(str(package))


def test_zgnx_zip_package_detects_root_level_hermes_layout(tmp_path):
    package = tmp_path / "nx_ota_hermes_m_v0.1.3_full.zip"
    _write_zgnx_zip_package(package, tmp_path)

    assert ota_backend.package_family(package) == "nx"
    assert ota_backend.inspect_nx_package(package) == len(b"nx-payload")
    manifest = ota_backend.package_manifest(package)

    assert manifest.family == "nx"
    assert manifest.system_image == "image/nx_ota_hermes_m_v0.1.3.tar.gz"
    assert manifest.runnable_module_count == 1
    assert ota.package_type(str(package)) == "nx"
    assert ota.package_version(str(package)) == "v0.1.3"


def test_orin_flash_tar_is_not_remote_ota_package(tmp_path):
    package = tmp_path / "zg_orin_flash_v0.4.6.tar.gz"
    root = tmp_path / "flash"
    bootloader = root / "bootloader"
    bootloader.mkdir(parents=True)
    (bootloader / "flashcmd.txt").write_text("flash command", encoding="utf-8")
    (bootloader / "system.img").write_bytes(b"raw-system")
    with tarfile.open(package, "w:gz") as tf:
        tf.add(bootloader / "flashcmd.txt", arcname="bootloader/flashcmd.txt")
        tf.add(bootloader / "system.img", arcname="bootloader/system.img")

    assert ota_backend.package_family(package) == ""
    assert ota.package_type(str(package)) == "orin_flash"
    assert ota.package_type_hint(str(package)) == "orin_flash"
    rows = ota.package_detail_rows(str(package))
    assert ("包类型", "Orin NX 线刷包") in rows
    assert ("刷机入口", "bootloader/flashcmd.txt") in rows


def test_s100_flash_tar_is_detected_as_line_flash_package(tmp_path):
    package = tmp_path / "zg_s100_v0.0.1.tar.gz"
    root = tmp_path / "s100"
    img = root / "product" / "img_packages"
    disk = img / "disk"
    disk.mkdir(parents=True)
    (img / "flash_all.sh").write_text("#!/bin/bash\n", encoding="utf-8")
    (img / "s100-gpt.json").write_text("{}", encoding="utf-8")
    (img / "system.img").write_bytes(b"system")
    (disk / "emmc_disk.simg").write_bytes(b"disk")
    with tarfile.open(package, "w:gz") as tf:
        tf.add(root / "product", arcname="product")

    assert ota_backend.package_family(package) == ""
    assert ota.package_type(str(package)) == "s100_flash"
    assert ota.package_type_hint(str(package)) == "s100_flash"
    rows = ota.package_detail_rows(str(package))
    assert ("包类型", "S100 线刷包") in rows
    assert ("刷机入口", "product/img_packages/flash_all.sh") in rows
    assert ("整盘镜像", "执行预检时检查 eMMC/UFS 镜像") in rows


def test_s100_flash_detail_rows_use_reusable_extracted_tree(tmp_path):
    package = tmp_path / "zg_s100_v0.0.1.tar.gz"
    package.write_bytes(b"pkg")
    extracted = _write_s100_extracted_tree(package, ufs_disk=True)

    rows = ota.package_detail_rows(str(package))

    assert ("已解压目录", str(extracted)) in rows
    assert ("整盘镜像", "eMMC(disk/emmc_disk.simg)、UFS(disk/ufs_disk.simg)") in rows
    assert ("DFU 引导安全类型", "secure_ohp (13 个文件)") in rows


def test_flash_commands_use_local_fastboot_and_factory_scripts(tmp_path):
    s100_package = tmp_path / "zg_s100_v0.0.1.tar.gz"
    s100_package.write_bytes(b"pkg")
    s100_target = ota.target_for_profile(get_product("zg_surround_s100"))

    assert s100_target is not None
    assert s100_target.is_flash
    assert s100_target.family == "s100_flash"

    s100_spec = ota.flash_upgrade_command(s100_target, str(s100_package))

    assert s100_spec.title == "执行线刷"
    assert s100_spec.dangerous is True
    assert "BUNDLED_FASTBOOT=" in s100_spec.command
    assert "BUNDLED_DFU=" in s100_spec.command
    assert "DOG_REMOTE_TOOL_DFU_UTIL" in s100_spec.command
    assert "S100_REMOTE_HOST=192.168.168.100" in s100_spec.command
    assert "S100_REMOTE_EXPECTED_HOST=192.168.168.100" in s100_spec.command
    assert "S100_REMOTE_USER=robot" in s100_spec.command
    assert "S100_REMOTE_PASSWORD=1" in s100_spec.command
    assert "s100_print_entry_help" in s100_spec.command
    assert "s100_try_remote_reboot_to_flash" in s100_spec.command
    assert "S100 SSH 路由" in s100_spec.command
    assert "DOG_REMOTE_TOOL_S100_AUTO_REBOOT" in s100_spec.command
    assert "DOG_REMOTE_TOOL_S100_SSH_TIMEOUT" in s100_spec.command
    assert "reboot usb2 -f" in s100_spec.command
    assert 'timeout "$ssh_timeout" sshpass' in s100_spec.command
    assert "sshpass -p" in s100_spec.command
    assert "ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o ConnectTimeout=2 -o PreferredAuthentications=password -o PubkeyAuthentication=no" in s100_spec.command
    assert "ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o ConnectTimeout=3 -o PreferredAuthentications=password -o PubkeyAuthentication=no" in s100_spec.command
    assert "wait_for_dfu_pid" in s100_spec.command
    assert "dfu_stage" in s100_spec.command
    assert "&& dfu_download" not in s100_spec.command
    assert "cmd_load_hsmfw_ohp" in s100_spec.command
    assert "-d,3652:6610 -a 0" in s100_spec.command
    assert "-d,3652:6615 -a 0 -R" in s100_spec.command
    assert "-d,3652:6620 -a 0 -R" in s100_spec.command
    assert "-d,3652:6625 -a 3 -R" in s100_spec.command
    assert "DOG_REMOTE_TOOL_S100_BOOT_SECURITY" in s100_spec.command
    assert "DOG_REMOTE_TOOL_S100_STORAGE_TYPE" in s100_spec.command
    assert "当前包只包含 eMMC 整盘镜像，按 bootintf=mmc 继续" in s100_spec.command
    assert 'S100_USE_XBURN="${DOG_REMOTE_TOOL_S100_USE_XBURN:-0}"' in s100_spec.command
    assert "未从设备读取到 secflag，按 DFU 引导安全类型推断" in s100_spec.command
    assert 'FASTBOOT_DEVICES="$("$FASTBOOT_BIN" devices || true)"' in s100_spec.command
    assert "FASTBOOT_DEVICE_COUNT" in s100_spec.command
    assert "[ERROR] 检测到多个 fastboot 设备" in s100_spec.command
    assert 's100_fastboot_getvar bootintf' in s100_spec.command
    assert "product/img_packages/flash_all.sh" in s100_spec.command
    assert 'S100_BOOT_ROOT="$(dirname "$FLASH_DIR")"' in s100_spec.command
    assert '"$S100_BOOT_ROOT/xmodem_tools"' in s100_spec.command
    assert '$boot_root/xmodem_tools/sec/out/s100/cmd_load_hsmfw_ohp' in s100_spec.command
    assert 'local boot_path="$boot_root/$boot_file"' in s100_spec.command
    assert "MCU_S100_V1.0.img" in s100_spec.command
    assert "disk/miniboot_flash_nose.img" in s100_spec.command
    assert "bootintf=mmc" in s100_spec.command
    assert "需要 eMMC 整盘镜像" in s100_spec.command
    assert "disk/emmc_disk.simg" in s100_spec.command
    assert "需要 UFS 整盘镜像" in s100_spec.command
    assert "包和设备介质不匹配" in s100_spec.command
    assert "disk/ufs_disk.simg" in s100_spec.command
    assert "BUNDLED_XBURN" in s100_spec.command
    assert "-p RDKS100" in s100_spec.command
    assert 'XBURN_INPUT_DIR="${S100_BOOT_ROOT:-$FLASH_DIR}"' in s100_spec.command
    assert '--storage_type "$XBURN_STORAGE_TYPE"' in s100_spec.command
    assert '--security_type "$XBURN_SECURITY_TYPE"' in s100_spec.command
    assert '-i "$XBURN_INPUT_DIR"' in s100_spec.command
    assert '--batch_num "$XBURN_BATCH_NUM"' in s100_spec.command
    assert "DOG_REMOTE_TOOL_S100_USE_XBURN" in s100_spec.command
    assert "DOG_REMOTE_TOOL_S100_BATCH_NUM" in s100_spec.command
    assert "DOG_REMOTE_TOOL_S100_XBURN_REBOOT" in s100_spec.command
    assert "--select_part all" not in s100_spec.command
    assert "--reboot" in s100_spec.command
    assert "DOG_REMOTE_TOOL_FASTBOOT_SPARSE_SIZE" in s100_spec.command
    assert 'fastboot_checked -S "$FASTBOOT_SPARSE_SIZE" flash 0x0 "disk/$DISK_IMG"' in s100_spec.command
    assert "阶段 2/3: eMMC/UFS 整盘镜像" in s100_spec.command
    assert "oem test:test" not in s100_spec.command
    assert "nv_ota_start.sh" not in s100_spec.command

    s100_precheck = ota.flash_precheck_command(s100_target, str(s100_package))

    assert "S100 USB 状态摘要" in s100_precheck.command
    assert "S100 SSH 路由" in s100_precheck.command
    assert "sudo ip route replace 192.168.168.0/24 via 192.168.234.1" in s100_precheck.command
    assert "优先检查 192.168.234.1 到 S100 的内网链路/上电状态" in s100_precheck.command
    assert "[WARN] 检测到多个 fastboot 设备" in s100_precheck.command
    assert "1a86:(8091|7523)" in s100_precheck.command
    assert "当前只看到 CH340 串口/HUB" in s100_precheck.command
    assert "执行线刷时会先尝试" in s100_precheck.command
    assert "reboot usb2 -f" in s100_precheck.command
    assert "S100_REMOTE_HOST_CANDIDATES" in s100_precheck.command
    assert "192.168.168.100" in s100_precheck.command
    assert "s100_select_reachable_remote_host" in s100_precheck.command
    assert "S100 进入刷写状态方法" in s100_precheck.command
    assert "看到 3652:6610 后松开" in s100_precheck.command
    assert "只看到 CH340/ttyUSB 不是刷写态" in s100_precheck.command
    assert "sshpass: 可用" in s100_precheck.command
    assert 'ssh -o StrictHostKeyChecking=no' in s100_precheck.command
    assert "SSH 候选地址均不可登录" in s100_precheck.command
    assert "s100_report_entry_readiness" in s100_precheck.command
    assert "S100 刷写入口就绪结论" in s100_precheck.command
    assert "S100_HAS_EMMC_DISK=0" in s100_precheck.command
    assert "S100_HAS_UFS_DISK=0" in s100_precheck.command

    assert "bootintf=mmc 且包内有 eMMC 镜像" in s100_precheck.command
    assert "bootintf=scsi，但预检未确认 disk/ufs_disk.simg" in s100_precheck.command
    assert "已在 S100 BootROM DFU 3652:6610" in s100_precheck.command
    assert "reboot usb2 -f" in s100_precheck.command
    assert "手动按 BOOT/RECOVERY" in s100_precheck.command
    assert "watch -n 0.5" in s100_precheck.command
    assert "fastboot devices" in s100_precheck.command
    assert "s100_report_package_structure" in s100_precheck.command
    assert "检查已解压目录" in s100_precheck.command
    assert "S100 包结构校验" in s100_precheck.command
    assert "DOG_REMOTE_TOOL_S100_TAR_LIST_CHECK" in s100_precheck.command
    assert "S100 DFU 引导文件校验" in s100_precheck.command
    assert "secure_ohp) boot_files=" in s100_precheck.command
    assert "nosecure) boot_files=" in s100_precheck.command
    assert "product/xmodem_tools" in s100_precheck.command

    s100_entry = ota.s100_entry_monitor_command(s100_target)

    assert s100_entry.title == "S100 刷写入口观察"
    assert s100_entry.dangerous is False
    assert "DOG_REMOTE_TOOL_S100_ENTRY_WATCH_SECONDS" in s100_entry.command
    assert "S100_REMOTE_PASSWORD=1" in s100_entry.command
    assert "S100 进入刷写状态方法" in s100_entry.command
    assert "就绪: S100 BootROM DFU 3652:6610" in s100_entry.command
    assert "可自动进入: SSH" in s100_entry.command
    assert "SSH 端口可达但登录失败" in s100_entry.command
    assert "未就绪: 只看到 CH340/ttyUSB" in s100_entry.command
    assert "reboot usb2 -f" in s100_entry.command

    orin_package = tmp_path / "zg_orin_flash_v0.4.6.tar.gz"
    orin_package.write_bytes(b"pkg")
    orin_target = ota.target_for_profile(get_product("zg_lidar_nx"))

    assert orin_target is not None
    assert orin_target.is_flash
    assert orin_target.family == "orin_flash"

    orin_spec = ota.flash_upgrade_command(orin_target, str(orin_package))

    assert "bootloader/flashcmd.txt" in orin_spec.command
    assert "bash ./flashcmd.txt" in orin_spec.command
    assert "BUNDLED_DFU=" not in orin_spec.command
    assert "dfu-util" not in orin_spec.command
    assert "nv_ota_start.sh" not in orin_spec.command

    orin_precheck = ota.flash_precheck_command(orin_target, str(orin_package))

    assert "BUNDLED_DFU=" not in orin_precheck.command
    assert "dfu-util" not in orin_precheck.command
    assert "S100 USB 状态摘要" not in orin_precheck.command


def test_s100_password_ssh_options_keep_password_auth_and_timeout():
    assert ota_flash._s100_password_ssh_options(2) == (
        "-o StrictHostKeyChecking=no "
        "-o UserKnownHostsFile=/dev/null "
        "-o ConnectTimeout=2 "
        "-o PreferredAuthentications=password "
        "-o PubkeyAuthentication=no"
    )


def _write_s100_extracted_tree(package, *, ufs_disk=False):
    stem = str(package)
    if stem.endswith(".tar.gz"):
        stem = stem[:-7]
    elif stem.endswith(".tgz"):
        stem = stem[:-4]
    root = package.parent / f"{os.path.basename(stem)}_extracted"
    product = root / "product"
    img = product / "img_packages"
    disk = img / "disk"
    boot = product / "xmodem_tools" / "sec" / "out" / "s100"
    disk.mkdir(parents=True)
    boot.mkdir(parents=True)
    for name in (
        "flash_all.sh",
        "fpt.img",
        "HSM_FW.img",
        "HSM_RCA.img",
        "keyimage_ohp.img",
        "SBL.img",
        "scp.img",
        "spl.img",
        "MCU_S100_V1.0.img",
        "misc.img",
        "system.img",
        "disk/miniboot_flash.img",
        "disk/miniboot_flash_nose.img",
        "disk/emmc_disk.simg",
    ):
        path = img / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"stub")
    if ufs_disk:
        (disk / "ufs_disk.simg").write_bytes(b"stub")
    for name in (
        "cmd_load_hsmfw",
        "hsmfw_se.pkg",
        "cmd_exit_hsmfw",
        "keyimage.img",
        "hsmrca.pkg",
        "cmd_load_hsmfw_ohp",
        "hsmfw_se_ohp.pkg",
        "cmd_exit_hsmfw_ohp",
        "fpt.img",
        "keyimage_ohp.img",
        "SBL.img",
        "hsmrca_ohp.pkg",
        "spl.img",
        "MCU_S100_V1.0.img",
        "acore_cfg.img",
        "bl31.img",
        "optee.img",
        "uboot.img",
    ):
        (boot / name).write_bytes(b"stub")
    return root


def _write_s100_precheck_fakes(
    bin_dir,
    *,
    fastboot=False,
    fastboot_count=1,
    dfu_6610=False,
    ssh_open=False,
    sshpass=True,
    bootintf="mmc",
):
    bin_dir.mkdir()
    if fastboot:
        fastboot_devices = [f"s100stub{i} fastboot" for i in range(1, fastboot_count + 1)]
        fastboot_devices_line = "printf '%s\\n' " + " ".join(repr(device) for device in fastboot_devices)
    else:
        fastboot_devices_line = "true"
    dfu_list_line = 'echo "Found DFU: [3652:6610] path=\\"1-1\\""' if dfu_6610 else "true"
    ssh_probe_result = "exit 0" if ssh_open else "exit 1"
    (bin_dir / "fastboot").write_text(
        "#!/bin/sh\n"
        "if [ \"$1\" = devices ]; then\n"
        f"  {fastboot_devices_line}\n"
        "  exit 0\n"
        "fi\n"
        "if [ \"$1\" = getvar ] && [ \"$2\" = bootintf ]; then\n"
        + (
            "  echo \"getvar:bootintf                                    FAILED (remote: 'Variable not implemented')\" >&2\n"
            "  exit 1\n"
            if bootintf is None
            else f"  echo 'bootintf: {bootintf}' >&2\n  exit 0\n"
        )
        + "fi\n"
        "exit 0\n",
        encoding="utf-8",
    )
    (bin_dir / "dfu-util").write_text(
        "#!/bin/sh\n"
        "if [ \"$1\" = -l ]; then\n"
        f"  {dfu_list_line}\n"
        "  exit 0\n"
        "fi\n"
        "exit 0\n",
        encoding="utf-8",
    )
    (bin_dir / "timeout").write_text(
        "#!/bin/sh\n"
        "shift\n"
        "case \"$*\" in\n"
        f"  *'/dev/tcp/'*) {ssh_probe_result} ;;\n"
        "esac\n"
        "exec \"$@\"\n",
        encoding="utf-8",
    )
    (bin_dir / "lsusb").write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    if sshpass:
        (bin_dir / "sshpass").write_text(
            "#!/bin/sh\n"
            "echo 's100'\n"
            "echo 'eth0 UP 192.168.168.100/24 192.168.168.100/24'\n"
            f"{ssh_probe_result}\n",
            encoding="utf-8",
        )
    for path in bin_dir.iterdir():
        path.chmod(0o755)


def _write_s100_flash_entry_fakes(bin_dir):
    bin_dir.mkdir()
    (bin_dir / "fastboot").write_text(
        "#!/bin/sh\n"
        "if [ \"$1\" = devices ]; then exit 0; fi\n"
        "exit 0\n",
        encoding="utf-8",
    )
    (bin_dir / "dfu-util").write_text(
        "#!/bin/sh\n"
        "if [ \"$1\" = -l ]; then exit 0; fi\n"
        "exit 1\n",
        encoding="utf-8",
    )
    (bin_dir / "timeout").write_text(
        "#!/bin/sh\n"
        "shift\n"
        "exec \"$@\"\n",
        encoding="utf-8",
    )
    (bin_dir / "sshpass").write_text("#!/bin/sh\nexit 1\n", encoding="utf-8")
    (bin_dir / "lsusb").write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    (bin_dir / "sleep").write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    (bin_dir / "date").write_text(
        "#!/bin/sh\n"
        "state=\"${DOG_REMOTE_TOOL_TEST_DATE_STATE:-/tmp/dog_remote_tool_date_state}\"\n"
        "value=100\n"
        "if [ -f \"$state\" ]; then value=$(cat \"$state\"); fi\n"
        "value=$((value + 100))\n"
        "printf '%s' \"$value\" > \"$state\"\n"
        "printf '%s\\n' \"$value\"\n",
        encoding="utf-8",
    )
    for path in bin_dir.iterdir():
        path.chmod(0o755)


def _run_s100_precheck(
    tmp_path,
    *,
    fastboot=False,
    fastboot_count=1,
    dfu_6610=False,
    ssh_open=False,
    bootintf="mmc",
    ufs_disk=False,
):
    package = tmp_path / "zg_s100_v0.0.1.tar.gz"
    package.write_bytes(b"pkg")
    _write_s100_extracted_tree(package, ufs_disk=ufs_disk)
    bin_dir = tmp_path / "bin"
    _write_s100_precheck_fakes(
        bin_dir,
        fastboot=fastboot,
        fastboot_count=fastboot_count,
        dfu_6610=dfu_6610,
        ssh_open=ssh_open,
        bootintf=bootintf,
    )
    target = ota.target_for_profile(get_product("zg_surround_s100"))
    script = ota.flash_precheck_command(target, str(package)).command
    env = os.environ.copy()
    env.update(
        {
            "PATH": f"{bin_dir}:{env.get('PATH', '')}",
            "DOG_REMOTE_TOOL_FASTBOOT": str(bin_dir / "fastboot"),
            "DOG_REMOTE_TOOL_DFU_UTIL": str(bin_dir / "dfu-util"),
        }
    )
    result = subprocess.run(["bash", "-c", script], check=False, text=True, capture_output=True, env=env, timeout=10)
    assert result.returncode == 0, result.stdout + result.stderr
    return result.stdout


def test_s100_precheck_reports_dfu_entry_readiness(tmp_path):
    output = _run_s100_precheck(tmp_path, dfu_6610=True)

    assert "S100 DFU 引导文件校验: secure (13 个文件)" in output
    assert "结论: 已在 S100 BootROM DFU 3652:6610" in output


def test_s100_entry_monitor_reports_dfu_ready(tmp_path):
    bin_dir = tmp_path / "bin"
    _write_s100_precheck_fakes(bin_dir, dfu_6610=True)
    target = ota.target_for_profile(get_product("zg_surround_s100"))
    script = ota.s100_entry_monitor_command(target).command
    env = os.environ.copy()
    env.update(
        {
            "PATH": f"{bin_dir}:{env.get('PATH', '')}",
            "DOG_REMOTE_TOOL_FASTBOOT": str(bin_dir / "fastboot"),
            "DOG_REMOTE_TOOL_DFU_UTIL": str(bin_dir / "dfu-util"),
            "DOG_REMOTE_TOOL_S100_ENTRY_WATCH_SECONDS": "2",
        }
    )

    result = subprocess.run(["bash", "-c", script], check=False, text=True, capture_output=True, env=env, timeout=10)

    assert result.returncode == 0, result.stdout + result.stderr
    assert "S100 进入刷写状态方法" in result.stdout
    assert "就绪: S100 BootROM DFU 3652:6610" in result.stdout


def test_s100_entry_monitor_reports_ssh_auto_entry_ready(tmp_path):
    bin_dir = tmp_path / "bin"
    _write_s100_precheck_fakes(bin_dir, ssh_open=True)
    target = ota.target_for_profile(get_product("zg_surround_s100"))
    script = ota.s100_entry_monitor_command(target).command
    env = os.environ.copy()
    env.update(
        {
            "PATH": f"{bin_dir}:{env.get('PATH', '')}",
            "DOG_REMOTE_TOOL_FASTBOOT": str(bin_dir / "fastboot"),
            "DOG_REMOTE_TOOL_DFU_UTIL": str(bin_dir / "dfu-util"),
            "DOG_REMOTE_TOOL_S100_ENTRY_WATCH_SECONDS": "2",
        }
    )

    result = subprocess.run(["bash", "-c", script], check=False, text=True, capture_output=True, env=env, timeout=10)

    assert result.returncode == 0, result.stdout + result.stderr
    assert "可自动进入: SSH robot@192.168.168.100 登录可用" in result.stdout


def test_s100_entry_monitor_does_not_auto_enter_without_sshpass(tmp_path):
    bin_dir = tmp_path / "bin"
    _write_s100_precheck_fakes(bin_dir, ssh_open=True, sshpass=False)
    core_bin = tmp_path / "core-bin"
    core_bin.mkdir()
    for name in ("bash", "dirname", "sed", "wc", "tr", "grep", "date", "sleep"):
        source = shutil.which(name)
        assert source, name
        (core_bin / name).symlink_to(source)
    target = ota.target_for_profile(get_product("zg_surround_s100"))
    script = ota.s100_entry_monitor_command(target).command
    env = os.environ.copy()
    env.update(
        {
            "PATH": f"{bin_dir}:{core_bin}",
            "DOG_REMOTE_TOOL_FASTBOOT": str(bin_dir / "fastboot"),
            "DOG_REMOTE_TOOL_DFU_UTIL": str(bin_dir / "dfu-util"),
            "DOG_REMOTE_TOOL_S100_ENTRY_WATCH_SECONDS": "1",
            "DOG_REMOTE_TOOL_S100_ENTRY_WATCH_INTERVAL": "1",
        }
    )

    result = subprocess.run(["bash", "-c", script], check=False, text=True, capture_output=True, env=env, timeout=10)

    assert result.returncode != 0
    assert "SSH 端口可达但本机 sshpass 不可用" in result.stdout
    assert "可自动进入: SSH" not in result.stdout


def test_s100_precheck_reports_fastboot_emmc_media_match(tmp_path):
    output = _run_s100_precheck(tmp_path, fastboot=True, bootintf="mmc")

    assert "bootintf: mmc" in output
    assert "bootintf=mmc 且包内有 eMMC 镜像" in output


def test_s100_precheck_ignores_failed_bootintf_getvar(tmp_path):
    output = _run_s100_precheck(tmp_path, fastboot=True, bootintf=None)

    assert "bootintf: FAILED" not in output
    assert "已在 fastboot，但未读取到 bootintf" in output


def test_s100_precheck_warns_on_multiple_fastboot_devices(tmp_path):
    output = _run_s100_precheck(tmp_path, fastboot=True, fastboot_count=2, bootintf="mmc")

    assert "[WARN] 检测到多个 fastboot 设备" in output
    assert "s100stub1 fastboot" in output
    assert "s100stub2 fastboot" in output


def test_s100_precheck_reports_fastboot_ufs_media_mismatch(tmp_path):
    output = _run_s100_precheck(tmp_path, fastboot=True, bootintf="scsi")

    assert "bootintf: scsi" in output
    assert "bootintf=scsi，但预检未确认 disk/ufs_disk.simg" in output


def test_s100_precheck_reports_fastboot_ufs_media_match(tmp_path):
    output = _run_s100_precheck(tmp_path, fastboot=True, bootintf="scsi", ufs_disk=True)

    assert "bootintf: scsi" in output
    assert "已找到 UFS 整盘镜像 disk/ufs_disk.simg" in output
    assert "bootintf=scsi 且包内有 UFS 镜像" in output


def test_s100_precheck_reports_ssh_auto_entry_readiness(tmp_path):
    output = _run_s100_precheck(tmp_path, ssh_open=True)

    assert "SSH 入口: 192.168.168.100:22 可登录" in output
    assert "结论: 当前未在 USB 刷写态，但 SSH 端口和 sshpass 可用" in output


def test_s100_precheck_reports_manual_entry_needed(tmp_path):
    output = _run_s100_precheck(tmp_path)

    assert "SSH 候选地址均不可登录" in output
    assert "结论: 当前未检测到 fastboot/3652 DFU，且不能确认 SSH 自动进入" in output
    assert "S100 进入刷写状态方法" in output
    assert "看到 3652:6610 后松开" in output
    assert "只看到 CH340/ttyUSB 不是刷写态" in output
    assert "watch -n 0.5" in output
    assert "fastboot devices" in output


def test_s100_flash_failure_prints_entry_help_when_no_entry_state(tmp_path):
    package = tmp_path / "zg_s100_v0.0.1.tar.gz"
    extracted = _write_s100_extracted_tree(package)
    with tarfile.open(package, "w:gz") as tf:
        tf.add(extracted / "product", arcname="product")
    bin_dir = tmp_path / "bin"
    _write_s100_flash_entry_fakes(bin_dir)
    target = ota.target_for_profile(get_product("zg_surround_s100"))
    script = ota.flash_upgrade_command(target, str(package)).command
    env = os.environ.copy()
    env.update(
        {
            "PATH": f"{bin_dir}:{env.get('PATH', '')}",
            "XDG_CACHE_HOME": str(tmp_path / "cache"),
            "DOG_REMOTE_TOOL_FASTBOOT": str(bin_dir / "fastboot"),
            "DOG_REMOTE_TOOL_DFU_UTIL": str(bin_dir / "dfu-util"),
            "DOG_REMOTE_TOOL_S100_BOOT_SECURITY": "secure_ohp",
            "DOG_REMOTE_TOOL_TEST_DATE_STATE": str(tmp_path / "date_state"),
        }
    )

    result = subprocess.run(["bash", "-c", script], check=False, text=True, capture_output=True, env=env, timeout=10)

    output = result.stdout + result.stderr
    assert result.returncode != 0
    assert "未检测到 S100 BootROM DFU 设备" in output
    assert "S100 进入刷写状态方法" in output
    assert "看到 3652:6610 后松开" in output
    assert "只看到 CH340/ttyUSB 不是刷写态" in output


def test_s100_flash_stops_after_dfu_stage_timeout(tmp_path):
    package = tmp_path / "zg_s100_v0.0.1.tar.gz"
    extracted = _write_s100_extracted_tree(package)
    with tarfile.open(package, "w:gz") as tf:
        tf.add(extracted / "product", arcname="product")
    bin_dir = tmp_path / "bin"
    _write_s100_flash_entry_fakes(bin_dir)
    (bin_dir / "dfu-util").write_text(
        "#!/bin/sh\n"
        "for arg in \"$@\"; do [ \"$arg\" = -D ] && echo 'Download done.' && exit 0; done\n"
        "if [ \"$1\" = -l ]; then echo 'Found DFU: [3652:6610] path=\"1-1\"'; exit 0; fi\n"
        "exit 1\n",
        encoding="utf-8",
    )
    (bin_dir / "dfu-util").chmod(0o755)
    (bin_dir / "date").write_text(
        "#!/bin/sh\n"
        "state=\"${DOG_REMOTE_TOOL_TEST_DATE_STATE:-/tmp/dog_remote_tool_date_state}\"\n"
        "value=100\n"
        "if [ -f \"$state\" ]; then value=$(cat \"$state\"); fi\n"
        "value=$((value + 1))\n"
        "printf '%s' \"$value\" > \"$state\"\n"
        "printf '%s\\n' \"$value\"\n",
        encoding="utf-8",
    )
    (bin_dir / "date").chmod(0o755)
    target = ota.target_for_profile(get_product("zg_surround_s100"))
    script = ota.flash_upgrade_command(target, str(package)).command
    env = os.environ.copy()
    env.update(
        {
            "PATH": f"{bin_dir}:{env.get('PATH', '')}",
            "XDG_CACHE_HOME": str(tmp_path / "cache"),
            "DOG_REMOTE_TOOL_FASTBOOT": str(bin_dir / "fastboot"),
            "DOG_REMOTE_TOOL_DFU_UTIL": str(bin_dir / "dfu-util"),
            "DOG_REMOTE_TOOL_S100_BOOT_SECURITY": "secure_ohp",
            "DOG_REMOTE_TOOL_TEST_DATE_STATE": str(tmp_path / "date_state"),
        }
    )

    result = subprocess.run(["bash", "-c", script], check=False, text=True, capture_output=True, env=env, timeout=10)

    output = result.stdout + result.stderr
    assert result.returncode != 0
    assert output.count("等待 DFU 设备 3652:6615 超时") == 1
    assert "secure_ohp 引导后未进入 3652:6615" in output
    assert "DOG_REMOTE_TOOL_S100_BOOT_SECURITY=secure" in output
    assert "等待 DFU 设备 3652:6620 超时" not in output
    assert "等待 S100 fastboot 枚举" not in output


def test_zgnx_remote_script_runs_rtk_mcu_before_nv_ota():
    script = ota_backend.nx_remote_script()

    assert "刷写 rtk_mcu" in script
    assert "-t rtk_mcu" in script
    assert "SKIP_NX_MCU" in script
    assert "跳过 rtk_mcu 刷写" in script
    assert "nv_ota_start.sh" in script
    assert "package_info.json" in script
    assert "os.path.getsize(path)" in script
    assert "删除远端暂存包释放空间" in script
    assert "复用 /ota/$PACKAGE_NAME" in script


def test_nx_precheck_reuses_existing_ota_target_for_tar_package():
    script = ota_remote_precheck_scripts.nx_precheck_script(
        "~/ota",
        "905003065CDA.tar.gz",
        False,
        16_238_780_511,
        16_348_825_600,
        16_238_780_511,
        57_000,
        0,
    )

    assert 'TARGET_PACKAGE_PATH="/ota/$PACKAGE_NAME"' in script
    assert "跳过 /ota 空间预留" in script


def test_nx_upgrade_command_can_skip_mcu():
    default_spec = ota.upgrade_command("zgnx", "192.168.168.100", "robot", "1", "~/ota", "/tmp/pkg.zip", "/tmp/tools.tbz2")
    skip_spec = ota.upgrade_command(
        "zgnx",
        "192.168.168.100",
        "robot",
        "1",
        "~/ota",
        "/tmp/pkg.zip",
        "/tmp/tools.tbz2",
        skip_mcu=True,
    )

    assert "--skip-mcu" not in default_spec.command
    assert "--skip-mcu" in skip_spec.command


def test_common_remote_find_one_supports_root_level_zgnx_zip_layout(tmp_path):
    work_dir = tmp_path / "work"
    firmware_dir = work_dir / "firmware"
    firmware_dir.mkdir(parents=True)
    expected = firmware_dir / "rtk_mcu_3150fd4_v2.2.3_zg.bin"
    expected.write_bytes(b"fw")
    script = (
        "set -euo pipefail\n"
        f"WORK_DIR={shlex.quote(str(work_dir))}\n"
        + ota_remote_shell.remote_common_shell("test", cleanup_robot_launch=False)
        + "\nfind_one '*/firmware/rtk*.bin' 'rtk_mcu 固件'\n"
    )

    result = subprocess.run(["bash", "-c", script], check=False, text=True, capture_output=True)

    assert result.returncode == 0
    assert result.stdout.strip().endswith(str(expected))


def test_zg3588_profile_maps_to_rk_ota_target():
    target = ota.target_for_profile(get_product("zg3588"))

    assert target is not None
    assert target.key == "zg3588"
    assert not target.is_flash
    assert target.family == "rk3588"
    assert target.remote_dir == "/userdata/upgrade"
    assert target.user == "robot"
    assert target.password == "bot"


def test_zg_surround_3588_profile_uses_body_controller_endpoint():
    target = ota.target_for_profile(get_product("zg_surround_3588"))

    assert target is not None
    assert target.key == "zg3588"
    assert target.label == "中狗环视版 3588"
    assert not target.is_flash
    assert target.family == "rk3588"
    assert target.remote_dir == "/userdata/upgrade"
    assert target.host == "192.168.234.1"
    assert target.user == "robot"
    assert target.password == "bot"


def test_s100_dfu_flash_is_limited_to_s100_targets(tmp_path):
    package = tmp_path / "zg_s100_v0.0.1.tar.gz"
    package.write_bytes(b"pkg")
    target = ota.target_for_profile(get_product("xg2_3588"))

    spec = ota.flash_upgrade_command(target, str(package))

    assert "S100 DFU 线刷目前只允许" in spec.command
    assert "wait_for_dfu_pid" not in spec.command
    assert "bash ./flash_all.sh -m all" not in spec.command

    precheck = ota.flash_precheck_command(target, str(package))

    assert "S100 DFU 线刷目前只允许" in precheck.command
    assert "wait_for_dfu_pid" not in precheck.command
    assert "dfu-util" not in precheck.command


def test_xg3588_profile_maps_to_rk_ota_target():
    target = ota.target_for_profile(get_product("xg3588"))

    assert target is not None
    assert target.key == "xg3588"
    assert target.family == "rk3588"
    assert target.user == "firefly"
    assert target.password == "firefly"


def test_small_dog_nx_profile_still_maps_to_ota_target():
    target = ota.target_for_profile(get_product("xg1_nx"))

    assert target is not None
    assert target.key == "xg_l1_point_nx"
    assert target.family == "nx"
    assert not target.is_flash


def test_zg_lidar_nx_uses_zgnx_ota_target_when_nx_ota_package_selected(tmp_path):
    package = tmp_path / "nx_ota_hermes_m_v0.1.3_full.zip"
    _write_zgnx_zip_package(package, tmp_path)
    page = OtaPage.__new__(OtaPage)
    page.package = _FakeText(str(package))
    page.profile = lambda: get_product("zg_lidar_nx")

    target = OtaPage.current_ota_target(page)

    assert target is not None
    assert target.key == "zgnx"
    assert target.family == "nx"
    assert not target.is_flash
    assert target.host == "192.168.168.100"


def test_zg_lidar_nx_deb_package_routes_to_small_deploy_target(tmp_path):
    package = tmp_path / "robots_dog_msgs_0.9.0_aarch64_humble_Linux.deb"
    _write_test_deb(package, package="robots_dog_msgs", version="0.9.0", architecture="arm64")
    page = OtaPage.__new__(OtaPage)
    page.package = _FakeText(str(package))
    page.profile = lambda: get_product("zg_lidar_nx")

    target = OtaPage.current_ota_target(page)

    assert target is not None
    assert target.key == "zgnx"
    assert target.family == "small_deploy"
    assert not target.is_flash
    assert target.host == "192.168.168.100"
    assert OtaPage._upgrade_button_text(page, target) == "安装小包"


def test_zg_lidar_nx_nx_ota_package_routes_upgrade_to_zgnx_backend_without_mcu(tmp_path, monkeypatch):
    package = tmp_path / "nx_ota_hermes_m_v0.1.3_full.zip"
    _write_zgnx_zip_package(package, tmp_path)
    page = OtaPage.__new__(OtaPage)
    page.package = _FakeText(str(package))
    page.profile = lambda: get_product("zg_lidar_nx")
    page.nx_mcu_check = _FakeCheckBox(checked=True)
    calls = []

    monkeypatch.setattr(ota, "upgrade_command", lambda *args: calls.append(args) or CommandSpec("执行 OTA 升级", "zgnx-ota"))

    spec = ota_actions.OtaActionsMixin.upgrade_spec(page)

    assert spec.command == "zgnx-ota"
    assert calls
    assert calls[0][0] == "zgnx"
    assert calls[0][1] == "192.168.168.100"
    assert calls[0][7] is True


def test_zg_lidar_nx_nx_ota_package_skips_mcu_even_if_ui_checkbox_exists(tmp_path, monkeypatch):
    package = tmp_path / "nx_ota_hermes_m_v0.1.3_full.zip"
    _write_zgnx_zip_package(package, tmp_path)
    page = OtaPage.__new__(OtaPage)
    page.package = _FakeText(str(package))
    page.profile = lambda: get_product("zg_lidar_nx")
    page.nx_mcu_check = _FakeCheckBox(checked=False)
    calls = []

    monkeypatch.setattr(ota, "upgrade_command", lambda *args: calls.append(args) or CommandSpec("执行 OTA 升级", "zgnx-ota"))

    spec = ota_actions.OtaActionsMixin.upgrade_spec(page)

    assert spec.command == "zgnx-ota"
    assert calls
    assert calls[0][0] == "zgnx"
    assert calls[0][7] is True


def test_latest_package_for_family_scans_beyond_newer_unrelated_candidates(tmp_path, monkeypatch):
    target = tmp_path / "older_rk3588.tar.gz"
    payload = tmp_path / "AIO.img"
    payload.write_bytes(b"RKFW" + b"\0" * 16)
    with tarfile.open(target, "w:gz") as tf:
        tf.add(payload, arcname="AIO.img")
    os.utime(target, (100, 100))
    for index in range(6):
        candidate = tmp_path / f"newer_unrelated_{index}.zip"
        candidate.write_bytes(b"not-a-zip")
        os.utime(candidate, (200 + index, 200 + index))
    tools = tmp_path / "ota_tools.tbz2"
    tools.write_bytes(b"tools")
    os.utime(tools, (300, 300))
    monkeypatch.setattr(ota_package_locator, "DEFAULT_PACKAGE_DIRS", (tmp_path,))

    assert ota_backend.latest_package_for_family("rk3588") == target
    assert ota.latest_local("ota_tools*.tbz2") == str(tools)


def test_upload_file_uses_cached_rsync_probe_result(tmp_path, monkeypatch):
    package = tmp_path / "ota.tar.gz"
    package.write_bytes(b"ota")
    target = ota_backend.TARGETS["zgnx"]
    commands = []

    def fail_capture(*_args, **_kwargs):
        raise AssertionError("cached rsync probe should avoid capture")

    monkeypatch.setattr(ota_backend, "capture", fail_capture)
    monkeypatch.setattr(ota_backend, "run_stream", lambda args, input_text=None: commands.append(args))
    monkeypatch.setattr(ota_backend, "remote_file_size", lambda _target, _remote_path: package.stat().st_size)

    remote_path = ota_backend.upload_file(target, package, "/tmp/ota", remote_has_rsync=False)

    assert remote_path == "/tmp/ota/ota.tar.gz"
    assert commands and "scp" in commands[0]


def test_nx_run_skips_package_upload_when_ota_target_is_complete(tmp_path, monkeypatch):
    package = tmp_path / "905003065CDA.tar.gz"
    package.write_bytes(b"ota")
    tools = tmp_path / "ota_tools.tbz2"
    tools.write_bytes(b"tools")
    uploads = []
    scripts = []

    args = SimpleNamespace(
        target="xg_l1_point_nx",
        package=str(package),
        tools=str(tools),
        remote_dir="~/ota",
        prepare_only=False,
        skip_mcu=True,
        host="",
        user="",
        password="",
    )

    manifest = ota_backend.OtaPackageManifest(package.name, "nx", "ota_package.tar", 123)
    monkeypatch.setattr(ota_backend, "validate_local_inputs", lambda *_args: manifest)
    monkeypatch.setattr(ota_backend, "remote_precheck", lambda *_args: None)
    monkeypatch.setattr(ota_backend, "remote_supports_rsync", lambda _target: False)
    monkeypatch.setattr(ota_backend, "remote_file_size_or_zero", lambda _target, remote_path: package.stat().st_size if remote_path == f"/ota/{package.name}" else 0)
    monkeypatch.setattr(ota_backend, "upload_file", lambda _target, src, _remote_dir, remote_has_rsync=None: uploads.append(src.name) or f"/tmp/{src.name}")
    monkeypatch.setattr(ota_backend, "run_remote_script", lambda *_args: scripts.append(True))

    ota_backend.command_run(args)

    assert package.name not in uploads
    assert tools.name in uploads
    assert scripts


def test_remote_precheck_reuses_rk_manifest_inspection(tmp_path, monkeypatch):
    package = tmp_path / "ota.tar.gz"
    package.write_bytes(b"ota")
    target = ota_backend.TARGETS["xg3588"]
    manifest = ota_backend.OtaPackageManifest(package.name, "rk3588", "AIO.img", 123)
    streams = []

    monkeypatch.setattr(ota_backend, "inspect_rk3588_package", lambda _package: (_ for _ in ()).throw(AssertionError("manifest should be reused")))
    monkeypatch.setattr(ota_backend, "run_stream", lambda args, input_text=None: streams.append((args, input_text)))

    ota_backend.remote_precheck(target, "/tmp/ota", package, None, manifest)

    assert streams
    assert "IMG_SIZE=123" in streams[0][0][-1]


def test_ota_backend_validate_local_inputs_delegates(monkeypatch, tmp_path):
    package = tmp_path / "ota.tar.gz"
    tools = tmp_path / "tools.tbz2"
    target = ota_backend.TARGETS["zgnx"]
    calls = []

    def fake_validate(call_target, call_package, call_tools):
        calls.append((call_target, call_package, call_tools))

    monkeypatch.setattr(ota_local_validation, "validate_local_inputs", fake_validate)

    ota_backend.validate_local_inputs(target, package, tools)

    assert calls == [(target, package, tools)]


def test_run_remote_script_uploads_executes_and_cleans(monkeypatch):
    target = ota_backend.TARGETS["zgnx"]
    streams = []
    captures = []

    monkeypatch.setattr(ota_backend_runner, "ssh_args", lambda _target, remote: ["ssh", remote])
    monkeypatch.setattr(ota_backend_runner, "run_stream", lambda args, input_text=None: streams.append((args, input_text)))
    monkeypatch.setattr(ota_backend_runner, "capture", lambda args, input_text=None: captures.append((args, input_text)) or "")

    ota_remote_execution.run_remote_script(target, "echo ok", {"A": "1", "SUDO_PASSWORD": "pw"})

    assert streams[0][1] == "echo ok"
    assert "cat > /tmp/dog_remote_ota_" in streams[0][0][1]
    assert "A=1 bash /tmp/dog_remote_ota_" in streams[1][0][1]
    assert streams[1][1] == "pw\n"
    assert captures and "rm -f /tmp/dog_remote_ota_" in captures[0][0][1]


def test_masked_command_only_masks_password_argument():
    command = "/usr/bin/python3 -m dog_remote_tool.modules.ota.backend run -H 192.168.168.100 -u robot -p bot"

    assert ota.masked_command(command, "bot") == ota_commands.masked_command(command, "bot")

    masked = ota.masked_command(command, "bot")

    assert "-u robot" in masked
    assert "192.168.168.100" in masked
    assert "-p '***'" in masked
    assert "-p bot" not in masked
