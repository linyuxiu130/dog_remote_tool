from dog_remote_tool.core.profiles import get_product
from dog_remote_tool.core.shell import CommandSpec
from dog_remote_tool.modules import mobile_diag
from dog_remote_tool.modules.mobile_diag import performance as mobile_diag_performance
from dog_remote_tool.modules.mobile_diag import performance_script as mobile_diag_performance_script
from dog_remote_tool.modules.mobile_diag import services as mobile_diag_services
from dog_remote_tool.modules.mobile_diag import temperature_script as mobile_diag_temperature_script
from dog_remote_tool.ui.pages.mobile_diag import layout as mobile_diag_layout
from dog_remote_tool.ui.pages.mobile_diag.page import MobileDiagPage
from helpers import FakeSignal as _FakeSignal


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


class _FakeButton:
    def __init__(self):
        self.enabled = True
        self.tooltip = ""

    def setEnabled(self, enabled):
        self.enabled = enabled

    def setToolTip(self, tooltip):
        self.tooltip = tooltip


class _FakeProfile:
    def __init__(self, *, capabilities):
        self.label = "S100"
        self.user = "robot"
        self.host = "192.168.1.2"
        self.capabilities = capabilities



class _FakeProcess:
    def __init__(self):
        self.readyReadStandardOutput = _FakeSignal()
        self.finished = _FakeSignal()
        self.started = False

    def start(self):
        self.started = True


class _FakePerfSlot:
    def __init__(self, running=False, read_result=False, output=""):
        self.running = running
        self.start_calls = []
        self.login_shell_values = []
        self.read_result = read_result
        self.read_calls = []
        self.finish_output = output
        self.finish_calls = []
        self.stop_calls = 0
        self.process = _FakeProcess()

    def is_running(self):
        return self.running

    def start_bash(self, command, login_shell=True):
        self.start_calls.append(command)
        self.login_shell_values.append(login_shell)
        self.running = True
        return self.process, 6

    def start_spec(self, spec, *, login_shell=True):
        return self.start_bash(spec.command, login_shell=login_shell)

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


class _FakeTimer:
    def __init__(self):
        self.start_calls = 0
        self.stop_calls = 0

    def start(self):
        self.start_calls += 1

    def stop(self):
        self.stop_calls += 1


class _FakeMobileDiagPage(MobileDiagPage):
    def __init__(self):
        self.perf_target = _FakeLabel()
        self.perf_record_status = _FakeLabel()
        self.mobile_notice = _FakeLabel()
        self.ros_shm_notice = _FakeLabel()
        self.recover_btn = _FakeButton()
        self.reboot_btn = _FakeButton()
        self.commands = []

    def profile(self):
        return object()

    def set_command(self, spec):
        self.commands.append(spec)
        return False


class _FakeMobileDiagRefreshPage(MobileDiagPage):
    def __init__(self, *, active=True, running=False):
        self.page_active = active
        self.perf_slot = _FakePerfSlot(running=running)
        self.perf_values = {
            key: _FakeLabel()
            for key in ("load", "mem", "swap", "ros_shm", "cpu_idle", "io", "temp_current", "top_mem", "joint_max")
        }
        self.perf_details = {key: _FakeLabel() for key in self.perf_values}
        self.top_cpu_rows = [(_FakeLabel(), _FakeLabel(), _FakeLabel(), _FakeLabel())]
        self.cpu_module_rows = [(_FakeLabel(), _FakeLabel(), _FakeLabel())]
        self.top_cpu_hint = _FakeLabel()
        self.joint_temp_status = _FakeLabel()
        self.joint_temp_cells = {"fl": _FakeLabel()}
        self.top_cpu_updates = []
        self.cpu_module_updates = []
        self.joint_updates = []

    def profile(self):
        return type(
            "Profile",
            (),
            {
                "label": "S100",
                "key": "xg2_s100",
                "user": "robot",
                "host": "192.168.1.2",
                "password": "bot",
                "target": "robot@192.168.1.2",
                "platform": "RK3588",
                "ros_domain_id": "42",
                "rmw": "rmw_cyclonedds_cpp",
            },
        )()

    def _read_perf_output(self, process, request_id):
        return MobileDiagPage._read_perf_output(self, process, request_id)

    def _perf_finished(self, process, request_id, profile, exit_code):
        return MobileDiagPage._perf_finished(self, process, request_id, profile, exit_code)

    def _update_top_cpu_rows(self, values):
        self.top_cpu_updates.append(dict(values))

    def _update_cpu_module_rows(self, values):
        self.cpu_module_updates.append(dict(values))

    def _update_joint_temperatures(self, values):
        self.joint_updates.append(dict(values))


def test_performance_record_actions_mark_not_started_when_runner_rejects_start(monkeypatch):
    page = _FakeMobileDiagPage()
    monkeypatch.setattr(mobile_diag, "performance_snapshot_command", lambda profile: CommandSpec("性能快照", "snapshot"))
    monkeypatch.setattr(mobile_diag, "performance_sample_command", lambda profile: CommandSpec("30秒采样", "sample"))

    assert MobileDiagPage.record_performance_snapshot(page) is False
    assert page.perf_record_status.text == "性能快照：任务未启动，当前有任务运行，请稍后再试。"

    assert MobileDiagPage.record_performance_sample(page) is False
    assert page.perf_record_status.text == "30秒采样：任务未启动，当前有任务运行，请稍后再试。"
    assert [command.title for command in page.commands] == ["性能快照", "30秒采样"]
    assert page.perf_record_status.styles == [
        "color:#8a5a00; font-weight:700;",
        "color:#8a5a00; font-weight:700;",
    ]


def test_mobile_network_actions_mark_not_started_when_runner_rejects_start(monkeypatch):
    page = _FakeMobileDiagPage()
    monkeypatch.setattr(mobile_diag, "recover_and_diag_command", lambda profile: CommandSpec("检测并恢复网络服务", "recover"))
    monkeypatch.setattr(mobile_diag, "reboot_command", lambda profile: CommandSpec("重启设备", "reboot"))

    assert MobileDiagPage.recover_mobile_network(page) is False
    assert page.mobile_notice.text == "网络恢复：任务未启动，当前有任务运行，请稍后再试。"

    assert MobileDiagPage.reboot_mobile_device(page) is False
    assert page.mobile_notice.text == "重启设备：任务未启动，当前有任务运行，请稍后再试。"
    assert [command.title for command in page.commands] == ["检测并恢复网络服务", "重启设备"]
    assert page.mobile_notice.styles == [
        "color:#8a5a00; font-weight:700;",
        "color:#8a5a00; font-weight:700;",
    ]


def test_mobile_diag_network_commands_use_route_repair_without_breaking_pipe(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path))
    profile = get_product("xg2_3588")

    diag = mobile_diag.diag_command(profile)
    recover = mobile_diag.recover_and_diag_command(profile)

    assert diag.command.index("192.168.234.0/24") < diag.command.index("python3 -m dog_remote_tool.modules.mobile_diag")
    assert diag.command.index("python3 -m dog_remote_tool.modules.mobile_diag") < diag.command.index(" ssh ")
    assert recover.command.index("192.168.234.0/24") < recover.command.index("python3 -m dog_remote_tool.modules.mobile_diag")
    assert recover.command.index("python3 -m dog_remote_tool.modules.mobile_diag") < recover.command.index(" ssh ")


def test_mobile_diag_service_commands_use_strict_sudo_run():
    profile = type(
        "Profile",
        (),
        {
            "password": "1",
            "target": "robot@192.168.168.100",
        },
    )()

    status = mobile_diag.service_status_command(profile)
    restart = mobile_diag.restart_service_command(profile)
    enable = mobile_diag.enable_service_command(profile)
    reboot = mobile_diag.reboot_command(profile)

    assert "sudo_run journalctl -u quectel-cm.service" in status.command
    assert "sudo_run systemctl restart quectel-cm.service" in restart.command
    assert "sudo_run systemctl start quectel-cm.service" in restart.command
    assert "sudo_run systemctl enable quectel-cm.service" in enable.command
    assert "sudo_run reboot" in reboot.command
    assert "command -v sudo" not in restart.command
    assert "command -v sudo" not in reboot.command
    assert reboot.dangerous is True


def test_ros_shm_actions_mark_not_started_when_runner_rejects_start(monkeypatch):
    page = _FakeMobileDiagPage()
    monkeypatch.setattr(mobile_diag, "ros_shm_check_command", lambda profile: CommandSpec("检查 ROS 共享内存", "check"))
    monkeypatch.setattr(mobile_diag, "ros_shm_cleanup_command", lambda profile: CommandSpec("清理 ROS 共享内存临时资源", "clean", dangerous=True))

    assert MobileDiagPage.check_ros_shm(page) is False
    assert page.ros_shm_notice.text == "共享内存检查：任务未启动，当前有任务运行，请稍后再试。"

    assert MobileDiagPage.clean_ros_shm(page) is False
    assert page.ros_shm_notice.text == "共享内存清理：任务未启动，当前有任务运行，请稍后再试。"
    assert [command.title for command in page.commands] == ["检查 ROS 共享内存", "清理 ROS 共享内存临时资源"]
    assert page.commands[-1].dangerous is True


def test_mobile_diag_profile_action_text_uses_common_label_style_helper():
    page = _FakeMobileDiagPage()

    MobileDiagPage._update_mobile_actions(page, _FakeProfile(capabilities={"5g"}))

    assert page.perf_target.text == "S100"
    assert page.mobile_notice.text == "当前目标：S100"
    assert page.mobile_notice.styles[-1] == ""
    assert page.recover_btn.enabled is True
    assert page.reboot_btn.enabled is True
    assert page.recover_btn.tooltip == "启用并重启 quectel-cm 服务，然后执行完整 4G/5G 诊断。"

    MobileDiagPage._update_mobile_actions(page, _FakeProfile(capabilities=set()))

    assert page.mobile_notice.text.startswith("当前目标 S100 不支持 4G/5G 诊断")
    assert page.mobile_notice.styles[-1] == ""
    assert page.recover_btn.enabled is False
    assert page.reboot_btn.enabled is False
    assert page.reboot_btn.tooltip == "当前设备不是 4G/5G 诊断目标。"


def test_mobile_diag_refresh_performance_returns_start_result():
    inactive = _FakeMobileDiagRefreshPage(active=False)

    assert MobileDiagPage.refresh_performance_status(inactive) is False
    assert inactive.perf_slot.start_calls == []

    busy = _FakeMobileDiagRefreshPage(running=True)

    assert MobileDiagPage.refresh_performance_status(busy) is False
    assert busy.perf_slot.start_calls == []

    page = _FakeMobileDiagRefreshPage()

    assert MobileDiagPage.refresh_performance_status(page) is True
    assert page.perf_slot.process.started is True
    assert page.perf_slot.login_shell_values == [False]
    assert len(page.perf_slot.start_calls) == 1
    assert "HOSTNAME=" in page.perf_slot.start_calls[0]


def test_mobile_diag_activate_page_does_not_repeat_auto_refresh(monkeypatch):
    calls = []
    monkeypatch.setattr(
        "dog_remote_tool.ui.pages.mobile_diag.page.QTimer.singleShot",
        lambda delay, callback: calls.append((delay, getattr(callback, "__name__", ""))),
    )
    page = _FakeMobileDiagRefreshPage(active=False)

    MobileDiagPage.activate_page(page)

    assert page.page_active is True
    assert calls == [(300, "refresh_performance_status")]

    MobileDiagPage.activate_page(page)

    assert calls == [(300, "refresh_performance_status")]


def test_mobile_diag_lifecycle_stops_performance_polling():
    page = _FakeMobileDiagRefreshPage()

    MobileDiagPage.deactivate_page(page)

    assert page.page_active is False
    assert page.perf_slot.stop_calls == 1

    MobileDiagPage.shutdown_processes(page)

    assert page.perf_slot.stop_calls == 2


def test_mobile_diag_read_perf_output_returns_slot_result():
    page = _FakeMobileDiagRefreshPage()
    page.perf_slot = _FakePerfSlot(read_result=True)

    assert MobileDiagPage._read_perf_output(page, page.perf_slot.process, request_id=7) is True
    assert page.perf_slot.read_calls == [(page.perf_slot.process, 7)]

    page.perf_slot.read_result = False

    assert MobileDiagPage._read_perf_output(page, page.perf_slot.process, request_id=8) is False


def test_mobile_diag_perf_finished_returns_accept_result(monkeypatch):
    stale = _FakeMobileDiagRefreshPage()
    stale.perf_slot = _FakePerfSlot(output=None)

    assert MobileDiagPage._perf_finished(stale, stale.perf_slot.process, request_id=9, profile=stale.profile(), exit_code=0) is False

    failed = _FakeMobileDiagRefreshPage()
    failed.perf_slot = _FakePerfSlot(output="ssh failed")

    assert MobileDiagPage._perf_finished(failed, failed.perf_slot.process, request_id=10, profile=failed.profile(), exit_code=1) is True
    assert failed.perf_values["load"].text == "读取失败"
    assert failed.perf_details["load"].text == "检查 SSH 或目标设备状态"
    assert failed.top_cpu_rows[0][0].text == "读取失败"
    assert failed.cpu_module_rows[0][0].text == "读取失败"
    assert failed.joint_temp_status.text == "读取失败"
    assert failed.joint_temp_cells["fl"].text == "--"

    values = {
        "LOAD_1": "0.10",
        "LOAD_5": "0.20",
        "LOAD_15": "0.30",
        "MEM_TOTAL_MB": "1000",
        "MEM_USED_MB": "250",
        "MEM_AVAILABLE_MB": "700",
        "SWAP_TOTAL_MB": "0",
        "SHM_TOTAL_MB": "1024",
        "SHM_USED_MB": "512",
        "SHM_USE_PERCENT": "50",
        "SHM_ZENOH_COUNT": "3",
        "SHM_ZENOH_256M_COUNT": "2",
        "SHM_DOG_REMOTE_HELPER_COUNT": "1",
        "CPU_IDLE": "75",
        "CPU_NI": "0",
        "CPU_CORES": "8",
        "IO_BI": "1",
        "IO_BO": "2",
        "CUR_TEMP_SOURCE": "3588",
        "CUR_TEMP_MAIN": "50",
        "CUR_TEMP_GPU": "45",
        "TOP_MEM_PROC": "python",
        "TOP_MEM_PERCENT": "3.5",
        "TIME": "12:00:00",
        "HOSTNAME": "dog01",
    }
    monkeypatch.setattr(mobile_diag, "parse_performance_probe_output", lambda output: values)
    success = _FakeMobileDiagRefreshPage()
    success.perf_slot = _FakePerfSlot(output="probe")

    assert MobileDiagPage._perf_finished(success, success.perf_slot.process, request_id=11, profile=success.profile(), exit_code=0) is True
    assert success.perf_values["load"].text == "0.10"
    assert success.perf_values["mem"].text == "25.0%"
    assert success.perf_values["swap"].text == "0%"
    assert success.perf_values["ros_shm"].text == "50.0%"
    assert success.perf_details["ros_shm"].text == "512/1024 MB  通信文件 3 / 256M 2  工具 1"
    assert success.perf_values["top_mem"].text == "python"
    assert success.top_cpu_updates == [values]
    assert success.cpu_module_updates == [values]
    assert success.joint_updates == [values]
    assert success.perf_values["load"].tooltip == "最近检测：12:00:00"


def test_mobile_diag_top_cpu_rows_update_text_and_tooltips():
    page = _FakeMobileDiagRefreshPage()
    values = {
        "CPU_CORES": "8",
        "TOP_CPU_1_PROC": "ros2",
        "TOP_CPU_1_PID": "1234",
        "TOP_CPU_1_PERCENT": "12.5",
        "TOP_CPU_1_TOTAL_PERCENT": "1.6",
        "TOP_CPU_1_MEM": "3.2",
    }

    MobileDiagPage._update_top_cpu_rows(page, values)

    name, pid, cpu, total_cpu = page.top_cpu_rows[0]
    assert page.top_cpu_hint.text == "前 6 个进程 / 8核"
    assert name.text == "1. ros2"
    assert name.tooltip == "ros2  MEM 3.2%"
    assert pid.text == "1234"
    assert pid.tooltip == "ros2  PID 1234"
    assert cpu.text == "12.5%"
    assert cpu.tooltip == "ros2  top 单核口径 12.5% / MEM 3.2%"
    assert total_cpu.text == "1.6%"
    assert total_cpu.tooltip == "ros2  htop 整机口径 1.6%"


def test_mobile_diag_cpu_module_rows_update_text_and_tooltips():
    page = _FakeMobileDiagRefreshPage()
    values = {
        "CPU_MODULE_1_NAME": "navigation",
        "CPU_MODULE_1_TOP_PERCENT": "45",
        "CPU_MODULE_1_TOTAL_PERCENT": "5.6",
    }

    MobileDiagPage._update_cpu_module_rows(page, values)

    name, cpu, total_cpu = page.cpu_module_rows[0]
    tooltip = "navigation  top 单核口径 45.0% / htop 整机口径 5.6%"
    assert name.text == "navigation"
    assert name.tooltip == tooltip
    assert cpu.text == "45.0%"
    assert cpu.tooltip == tooltip
    assert total_cpu.text == "5.6%"
    assert total_cpu.tooltip == tooltip


def test_ros_shm_commands_include_zenoh_and_tool_cleanup():
    profile = type(
        "Profile",
        (),
        {
            "password": "1",
            "target": "robot@192.168.168.100",
        },
    )()

    check = mobile_diag.ros_shm_check_command(profile)
    cleanup = mobile_diag.ros_shm_cleanup_command(profile)

    assert "/dev/shm" in check.command
    assert "*.zenoh" in check.command
    assert "dog_remote_start_navigation_helper" in check.command
    assert "sudo_ok=0" in check.command
    assert "sudo -S -p" in check.command
    assert "true >/dev/null 2>&1; then sudo_ok=1" in check.command
    assert "if [ \"$sudo_ok\" = 1 ]" in check.command
    assert "sudo_run lsof +D /dev/shm" in check.command
    assert cleanup.dangerous is True
    assert "dog_remote_tool_pose_stream" in cleanup.command
    assert "ros2cli.daemon.daemonize" in cleanup.command
    assert "sudo_run rm -f -- \"$file\"" in cleanup.command
    assert "已删除未占用文件" in cleanup.command
