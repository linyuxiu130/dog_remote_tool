import time
import re

from PyQt5.QtWidgets import QMessageBox

from dog_remote_tool.core.profiles import PRODUCTS
from dog_remote_tool.core.shell import CommandSpec, quote
from dog_remote_tool.modules import arc_app_ws
from dog_remote_tool.modules import mapping
from dog_remote_tool.modules.mapping import arc as mapping_arc
from dog_remote_tool.modules.mapping import arc_common as mapping_arc_common
from dog_remote_tool.modules.mapping import arc_status as mapping_arc_status
from dog_remote_tool.modules.mapping import defaults as mapping_defaults
from dog_remote_tool.modules.mapping import pgm_editor as mapping_pgm_editor
from dog_remote_tool.modules.mapping import probe as mapping_probe
from dog_remote_tool.modules import localization
from dog_remote_tool.modules.localization import pose_record as localization_pose_record
from dog_remote_tool.modules.localization import alg as localization_alg
from dog_remote_tool.modules.localization import probe as localization_probe
from dog_remote_tool.modules.localization import runtime as localization_runtime
from dog_remote_tool.ui import image_preview, image_zoom, map_helpers, map_history_helpers, mapping_status_summary
from dog_remote_tool.ui.pages.mapping import lifecycle as mapping_lifecycle
from dog_remote_tool.ui.pages.mapping import actions as mapping_actions
from dog_remote_tool.ui.pages.mapping import map_history as mapping_map_history
from dog_remote_tool.ui.pages.mapping import preview as mapping_preview
from dog_remote_tool.ui.pages.mapping import status as mapping_status
from dog_remote_tool.ui.pages.mapping import transfer_actions as mapping_transfer_actions
from dog_remote_tool.ui.pages.mapping.page import MapHistoryCard, MappingPage
from dog_remote_tool.ui import navigation_helpers
from helpers import remote_command as _remote_command, FakeSignal as _FakeSignal


def test_format_history_map_size():
    assert map_helpers.format_history_map_size("") == "--"
    assert map_helpers.format_history_map_size("512") == "512 B"
    assert map_helpers.format_history_map_size("1536") == "1.5 KB"


def test_mapping_arc_action_script_reuses_common_app_ws_helpers():
    common = arc_app_ws.common_arc_app_ws_python()
    script = mapping_arc._arc_app_ws_action_python()

    assert script.startswith(common)
    assert "def send_text(sock, obj):" in script
    assert "def send_close(sock):" in script
    assert "def recv_text(sock):" in script
    assert "def parse_app_response(message):" in script
    assert "start_arc_align_coarse" in script
    assert "exit_charging" in script


def test_common_arc_app_ws_cleans_stale_tool_owned_busy_channel_before_retry():
    script = arc_app_ws.common_arc_app_ws_python()

    assert "def cleanup_stale_app_ws_owner():" in script
    assert "if cleanup_stale_app_ws_owner():" in script
    assert "continue" in script
    assert "def _tcp_10010_inodes():" in script
    assert "def _process_socket_inodes(pid):" in script
    assert "def _is_stale_dog_remote_app_ws_client(pid):" in script
    assert 'cmdline.startswith("python3 ")' in script
    assert "127.0.0.1" in script
    assert "10010" in script
    assert "signal.SIGTERM" in script
    assert "signal.SIGKILL" in script
    assert "已清理遗留系统应用通道客户端，正在重试" in script


def test_common_arc_app_ws_only_treats_client_connections_as_busy():
    script = arc_app_ws.common_arc_app_ws_python()

    assert 'remote.rsplit(":", 1)[-1].upper() == "271A"' in script
    assert 'local.rsplit(":", 1)[-1].upper() == "271A" or remote.rsplit(":", 1)[-1].upper() == "271A"' not in script


def test_common_arc_app_ws_cleanup_handles_python_stdin_clients_and_transient_busy():
    script = arc_app_ws.common_arc_app_ws_python()

    assert 'return cmdline.startswith("python3 ") or cmdline == "python3"' in script
    assert "系统应用通道被占用，等待重试" in script
    assert "cleanup_stale_app_ws_owner()" in script


def test_common_arc_app_ws_uses_persistent_broker_socket_for_requests():
    script = arc_app_ws.common_arc_app_ws_python()

    assert 'APP_WS_BROKER_SOCKET = "/tmp/dog_remote_app_ws.sock"' in script
    assert 'APP_WS_BROKER_SCRIPT = "/tmp/dog_remote_app_ws_broker.py"' in script
    assert "APP_WS_BROKER_VERSION = 2" in script
    assert "class AppWsBrokerClient:" in script
    assert "def ensure_app_ws_broker():" in script
    assert "def write_app_ws_broker_script():" in script
    assert "def cleanup_stale_app_ws_broker():" in script
    assert "def _direct_connect_ws():" in script
    assert "return AppWsBrokerClient()" in script
    assert '"op": "request"' in script
    assert "start_app_ws_broker()" in script
    assert "if ping_app_ws_broker():" in script
    assert "if ping_app_ws_broker() and not is_app_channel_busy():" not in script


def test_common_arc_app_ws_request_once_dispatches_through_broker_client():
    script = arc_app_ws.common_arc_app_ws_python()

    assert "if isinstance(sock, AppWsBrokerClient):" in script
    assert "messages = sock.request(request(func, frame, value), func, wait_seconds)" in script
    assert "for message in messages:" in script
    assert "send_text(sock, request(func, frame, value))" in script


def test_common_arc_app_ws_broker_has_idle_timeout_and_versioned_ping():
    script = arc_app_ws.common_arc_app_ws_python()

    assert "IDLE_SECONDS = 45" in script
    assert "BROKER_VERSION = 2" in script
    assert 'response(handle, {"ok": True, "pong": True, "version": BROKER_VERSION})' in script
    assert 'response.get("version") == APP_WS_BROKER_VERSION' in script
    assert "server.settimeout(1.0)" in script
    assert "time.monotonic() - LAST_ACTIVITY > IDLE_SECONDS" in script
    assert "reset_app_ws()" in script
    assert "os.unlink(SOCKET_PATH)" in script


def test_common_arc_app_ws_reclaims_unreachable_or_old_broker_processes():
    script = arc_app_ws.common_arc_app_ws_python()

    assert "def _argv_for_pid(pid):" in script
    assert "def _is_app_ws_broker_process(pid):" in script
    assert "def cleanup_stale_app_ws_broker():" in script
    assert "cleanup_stale_app_ws_broker()" in script
    assert "APP_WS_BROKER_SCRIPT in argv[1:]" in script
    assert "signal.SIGTERM" in script
    assert "signal.SIGKILL" in script


def test_stale_app_ws_shell_cleanup_no_longer_kills_broker_clients():
    shell = arc_app_ws.stale_app_ws_cleanup_shell()

    assert "dog_remote_cleanup_stale_app_ws()" in shell
    assert "true;" in shell
    assert "kill $old_app_ws_pids" not in shell
    assert "index($0, \"PORT = 10010\")" not in shell


def test_history_map_display_for_history_map():
    label, detail = map_helpers.history_map_display(
        "/opt/data/.robot/map/history_map/2026_05_25_09_30_00/map.pgm",
        "2026-05-25 09:30:11",
        "2048",
    )

    assert label == "2026-05-25 09:30 | 2.0 KB | 2026_05_25_09_30_00"
    assert "目录：/opt/data/.robot/map/history_map/2026_05_25_09_30_00" in detail


def test_compact_history_map_label_uses_display_time_or_directory_name():
    assert map_helpers.history_map_label_prefix("2026-05-25 09:30 | 2.0 KB") == "2026-05-25 09:30"
    assert map_helpers.history_map_label_prefix("--") == ""
    assert (
        map_helpers.history_map_timestamp_label(
            "/opt/data/.robot/map/history_map/2026_05_25_09_30_00/map.pgm",
            include_seconds=False,
        )
        == "05-25 09:30"
    )
    assert (
        map_helpers.compact_history_map_label(
            "2026-05-25 09:30 | 2.0 KB | 2026_05_25_09_30_00",
            "/opt/data/.robot/map/history_map/2026_05_25_09_30_00/map.pgm",
        )
        == "2026-05-25 09:30"
    )
    assert (
        map_helpers.compact_history_map_label("--", "/opt/data/.robot/map/history_map/2026_05_25_09_30_00/map.pgm")
        == "05-25 09:30:00"
    )
    assert map_helpers.compact_history_map_label("--", "/opt/data/.robot/map/map.pgm") == "地图"


def test_mapping_page_pgm_editor_method_comes_from_actions_module():
    assert MappingPage.open_map_pgm_editor is mapping_actions.MappingActionsMixin.open_map_pgm_editor


def test_parse_history_map_list_helpers_deduplicate_and_extract_disk_detail():
    output = "\n".join(
        [
            "DISK\t1024\t2048\t50%\t/opt/data",
            "1700000000\t2026-05-25 09:30:11\t2048\t/opt/data/.robot/map/history_map/a/map.pgm",
            "1700000001\t2026-05-25 09:31:11\t4096\t/opt/data/.robot/map/history_map/a/map.pgm",
            "bad\tline",
            "1700000002\t2026-05-25 09:32:11\t512\t/opt/data/.robot/map/map.pgm",
        ]
    )

    entries = map_helpers.parse_history_map_entries(output)

    assert [entry[1] for entry in entries] == [
        "/opt/data/.robot/map/history_map/a/map.pgm",
    ]
    assert navigation_helpers.parse_map_list_entries(output) == entries
    assert entries[0][0] == "2026-05-25 09:30 | 2.0 KB | a"
    assert map_helpers.parse_history_map_disk_detail(output) == "可用空间 1.0 KB / 2.0 KB（已用 50%）；分区 /opt/data"


def test_navigation_pose_parsers_share_field_conversion():
    assert navigation_helpers.parse_pose_probe("POSE=ok\nX=1.5\nY=-2.5\n") == (1.5, -2.5, 0.0)
    assert navigation_helpers.parse_pose_stream_line("POSE=ok X=1.5 Y=-2.5") == (1.5, -2.5, 0.0)
    assert navigation_helpers.parse_pose_probe("POSE=ok\nX=bad\nY=-2.5\nYAW=0.3\n") is None
    assert navigation_helpers.parse_pose_stream_line("POSE=ok X=1.5 Y=bad YAW=0.3") is None


def test_local_map_preview_dir_is_stable_for_remote_path():
    assert str(
        map_helpers.local_map_preview_dir(
            "xg2_s100",
            "192.168.168.100",
            "/opt/data/.robot/map/history_map/a/map.pgm",
            "/tmp/maps",
        )
    ) == "/tmp/maps/_preview/xg2_s100_192_168_168_100_opt_data__robot_map_history_map_a"


def test_summarize_mapping_status_parses_alg_and_disk_fields():
    profile = PRODUCTS["xg2_s100"]
    output = "\n".join(
        [
            "STATUS=ready",
            "TEXT=空闲",
            "MAP_COUNT=2",
            "LATEST_MAP=/opt/data/.robot/map/history_map/a/map.pgm",
            "ALG_MAPPING_STATUS=MappingRunning",
            "ALG_MAPPING_SOURCE=robot_alg_manager",
            "SLAM_MILEAGE=12.345",
            "DISK_AVAILABLE=1024",
            "DISK_SIZE=2048",
            "DISK_USED_PERCENT=50%",
            "DISK_TARGET=/opt/data",
        ]
    )

    summary = map_helpers.summarize_mapping_status(profile, output, 0, "结束保存中")

    assert summary.state == "mapping"
    assert summary.alg_status == "MappingRunning"
    assert "远端状态：建图中" in summary.detail
    assert "历史地图：2 张" in summary.detail
    assert "最新地图：map.pgm" in summary.detail
    assert "剩余空间：1.0 KB / 2.0 KB（已用 50%）" in summary.detail
    assert "保存流程进行中，正在确认地图文件" in summary.detail


def test_summarize_mapping_status_infers_recent_save_from_map_age():
    profile = PRODUCTS["xg2_s100"]
    output = "\n".join(
        [
            "STATUS=ready",
            "TEXT=空闲",
            "MAP_COUNT=3",
            "LATEST_MAP=/opt/data/.robot/map/history_map/new/map.pgm",
            "LATEST_MAP_AGE=12",
        ]
    )

    summary = map_helpers.summarize_mapping_status(profile, output, 0)

    assert summary.state == "success"
    assert summary.text == "保存完成"
    assert "最新地图刚更新：12s 前" in summary.detail
    assert "保存流程进行中" not in summary.detail


def test_summarize_mapping_status_does_not_show_saving_copy_after_recent_save():
    profile = PRODUCTS["xg2_s100"]
    output = "\n".join(
        [
            "STATUS=ready",
            "TEXT=空闲",
            "MAP_COUNT=3",
            "LATEST_MAP=/opt/data/.robot/map/history_map/new/map.pgm",
            "LATEST_MAP_AGE=12",
        ]
    )

    summary = map_helpers.summarize_mapping_status(profile, output, 0, "保存确认中")

    assert summary.state == "success"
    assert summary.text == "保存完成"
    assert "保存流程进行中" not in summary.detail


def test_summarize_mapping_status_keeps_saving_when_alg_ready_during_finish():
    profile = PRODUCTS["zg_lidar_nx"]
    output = "\n".join(
        [
            "STATUS=ready",
            "TEXT=已就绪",
            "ALG_MAPPING_STATUS=MappingReady",
            "MAP_COUNT=2",
            "LATEST_MAP=/ota/alg_data/map/history_map/old/map.pgm",
            "LATEST_MAP_AGE=600",
        ]
    )

    summary = map_helpers.summarize_mapping_status(profile, output, 0, "结束保存中")

    assert summary.state == "saving"
    assert summary.text == "保存确认中"


def test_summarize_mapping_status_reports_command_failure_without_status_payload():
    profile = PRODUCTS["xg2_s100"]

    summary = map_helpers.summarize_mapping_status(profile, "ssh failed\nnetwork unreachable", 255)

    assert summary.failed
    assert summary.state == "unknown"
    assert summary.text == "读取失败"
    assert summary.detail == "ssh failed；network unreachable"


class _FakeMappingFinishedPage:
    def __init__(self):
        self.mapping_runner_task_id = 12
        self.mapping_operation_active = True
        self.operations = []

    def set_mapping_operation(self, text, state="idle"):
        self.operations.append((text, state))


class _FakeMappingAutoPullSavedPage:
    def __init__(self):
        self.mapping_runner_task_id = 21
        self.mapping_operation_active = True
        self.preview_status = _FakeLabel()
        self.operations = []
        self.next_step_hints = []
        self.map_list_refreshes = []

    def set_mapping_operation(self, text, state="idle"):
        self.operations.append((text, state))

    def show_mapping_next_steps(self, hint):
        self.next_step_hints.append(hint)

    def refresh_map_list(self, *args, **kwargs):
        self.map_list_refreshes.append((args, kwargs))
        return True


class _FakeMappingDeleteFinishedPage:
    def __init__(self):
        self.mapping_runner_task_id = 31
        self.mapping_operation_active = True
        self.preview_status = _FakeLabel()
        self.preview_remote_pgm = "/opt/data/.robot/map/history_map/a/map.pgm"
        self.fetching_preview_remote_pgm = self.preview_remote_pgm
        self.preview_file = "/tmp/maps/a/map.pgm"
        self.preview_pixmap = object()
        self.operations = []
        self.map_list_refreshes = []

    def set_mapping_operation(self, text, state="idle"):
        self.operations.append((text, state))

    def refresh_map_list(self, *args, **kwargs):
        self.map_list_refreshes.append((args, kwargs))
        return True


def test_mapping_runner_finished_ignores_unrelated_task():
    page = _FakeMappingFinishedPage()

    MappingPage.handle_mapping_runner_finished(page, 99, 0, "结束并保存建图")

    assert page.mapping_runner_task_id == 12
    assert page.operations == []


def test_mapping_save_finish_shows_next_step_actions():
    page = _FakeMappingAutoPullSavedPage()

    MappingPage.handle_mapping_runner_finished(page, 21, 0, "结束并保存建图")

    assert page.operations == [("保存完成", "done")]
    assert page.next_step_hints == ["地图已保存，可继续编辑路网或进入导航。"]
    assert page.map_list_refreshes == []


def test_mapping_save_finish_refreshes_preview():
    page = _FakeMappingAutoPullSavedPage()

    MappingPage.handle_mapping_runner_finished(page, 21, 0, "结束并保存建图")

    assert page.operations == [("保存完成", "done")]
    assert page.next_step_hints == ["地图已保存，可继续编辑路网或进入导航。"]
    assert page.map_list_refreshes == []
    assert page.preview_status.text() == "建图已保存"


def test_mapping_runner_finished_waits_for_alg_saved_output_before_refresh():
    start_page = _FakeMappingAutoPullSavedPage()

    MappingPage.handle_mapping_runner_finished(start_page, 21, 0, "开始建图")

    assert start_page.map_list_refreshes == []

    saved_page = _FakeMappingAutoPullSavedPage()

    MappingPage.handle_mapping_runner_finished(saved_page, 21, 0, "结束并保存建图")

    assert saved_page.map_list_refreshes == []


def test_mapping_save_wait_interrupted_stays_in_confirming_state():
    page = _FakeMappingAutoPullSavedPage()

    MappingPage.handle_mapping_runner_finished(page, 21, 143, "结束并保存建图")

    assert page.operations == [("保存确认中", "saving")]
    assert page.mapping_operation_active is True
    assert page.preview_status.text() == "远端已接收结束保存，本地等待被中断；请刷新状态确认最新地图。"
    assert page.map_list_refreshes == []


def test_mapping_delete_finish_refreshes_history_previews():
    page = _FakeMappingDeleteFinishedPage()

    MappingPage.handle_mapping_runner_finished(page, 31, 0, "删除选中地图")

    assert page.operations == [("删除完成", "done")]
    assert page.preview_status.text() == "地图已删除，正在刷新历史图列表"
    assert page.preview_remote_pgm == ""
    assert page.fetching_preview_remote_pgm == ""
    assert page.preview_file == ""
    assert page.preview_pixmap is None
    assert page.map_list_refreshes == [((), {"silent": False, "force_preview": True, "force_latest": True})]
    assert page.mapping_operation_active is False


def test_mapping_delete_failure_keeps_current_previews_until_user_refreshes():
    page = _FakeMappingDeleteFinishedPage()

    MappingPage.handle_mapping_runner_finished(page, 31, 5, "删除选中地图")

    assert page.operations == [("删除失败", "blocked")]
    assert page.preview_status.text() == "地图删除失败，请查看执行日志"
    assert page.preview_remote_pgm == "/opt/data/.robot/map/history_map/a/map.pgm"
    assert page.preview_pixmap is not None
    assert page.map_list_refreshes == []
    assert page.mapping_operation_active is False


class _FakeRunner:
    def __init__(self, *, task_id=0, conflict=""):
        self.task_id = task_id
        self.conflict = conflict
        self.output = self
        self.output_lines = []
        self.run_calls = 0
        self.run_args = []

    def conflict_reason(self, *args, **kwargs):
        return self.conflict

    def emit(self, text):
        self.output_lines.append(text)

    def is_running(self):
        return False

    def run(self, *args, **kwargs):
        self.run_calls += 1
        self.run_args.append((args, kwargs))
        return self.task_id


class _FakeMappingConflictPage:
    def __init__(self):
        self.runner = _FakeRunner(conflict="已有任务")
        self.mapping_operation_active = True
        self.mapping_runner_task_id = 41
        self.current_spec = type(
            "Spec",
            (),
            {"title": "保存编辑地图", "dangerous": False, "description": ""},
        )()
        self.last_mapping_status_at = time.monotonic()
        self.last_mapping_alg_status = "MappingRunning"
        self.operations = []

    def profile(self):
        return PRODUCTS["xg2_s100"]

    def mapping_values(self):
        return (
            "richbeam",
            "/opt/data/.robot/map",
            "/opt/data/.robot/calibration.yaml",
            "/opt/data/.robot/arc.yaml",
        )

    def set_mapping_operation(self, text, state="idle"):
        self.operations.append((text, state))

    def refresh_mapping_status(self):
        raise AssertionError("valid mapping status should not refresh")


def _assert_mapping_conflict_state_preserved(page):
    assert page.mapping_operation_active is True
    assert page.mapping_runner_task_id == 41
    assert page.current_spec.title == "保存编辑地图"
    assert page.runner.run_calls == 0


def test_mapping_start_preflight_conflict_does_not_mutate_pending_state():
    page = _FakeMappingConflictPage()

    started = MappingPage.make_start_mapping(page)

    assert started is False
    _assert_mapping_conflict_state_preserved(page)
    assert page.operations == []
    assert page.runner.output_lines == ["[WARN] 当前已有任务运行，未发送开始建图请求。已有任务\n"]


def test_mapping_finish_preflight_conflict_does_not_mutate_pending_state():
    page = _FakeMappingConflictPage()

    started = MappingPage.make_finish_mapping(page)

    assert started is False
    _assert_mapping_conflict_state_preserved(page)
    assert page.operations == []
    assert page.runner.output_lines == ["[WARN] 当前已有任务运行，未发送结束保存请求。已有任务\n"]


def test_mapping_cancel_preflight_conflict_does_not_mutate_pending_state():
    page = _FakeMappingConflictPage()

    started = MappingPage.make_cancel_mapping(page)

    assert started is False
    _assert_mapping_conflict_state_preserved(page)
    assert page.operations == []
    assert page.runner.output_lines == ["[WARN] 当前已有任务运行，未发送取消建图请求。已有任务\n"]


class _FakeMappingActionSuccessPage(_FakeMappingConflictPage):
    def __init__(self):
        super().__init__()
        self.runner = _FakeRunner(task_id=77)


class _FakeStoppableSlot:
    def __init__(self):
        self.stopped = 0

    def is_running(self):
        return True

    def stop(self):
        self.stopped += 1
        return True


def test_mapping_start_returns_started_when_runner_starts():
    page = _FakeMappingActionSuccessPage()

    started = MappingPage.make_start_mapping(page)

    assert started is True
    assert page.mapping_runner_task_id == 77
    assert page.mapping_operation_active is True
    assert page.operations[-1] == ("开始建图中", "running")
    assert page.runner.run_calls == 1
    assert page.runner.output_lines[0] == "[INFO] 建图：已请求开始建图。\n"


def test_mapping_finish_stops_inflight_status_probe_before_save():
    page = _FakeMappingActionSuccessPage()
    page.status_slot = _FakeStoppableSlot()

    started = MappingPage.make_finish_mapping(page)

    assert started is True
    assert page.status_slot.stopped == 1
    assert page.runner.run_calls == 1


def test_mapping_start_uses_alg_route_without_slam_state_probe():
    page = _FakeMappingActionSuccessPage()

    started = MappingPage.make_start_mapping(page)

    assert started is True
    spec = page.runner.run_args[0][0][0]
    assert "start_mapping" in spec.command
    assert '"start": 1' in spec.command
    assert "get_mapping_status" in spec.command
    assert "ALG_MAPPING_STATUS=" in spec.command
    assert "SLAM_CODE_MODE" not in spec.command
    assert "robots_dog_msgs/srv/GetSlamState" not in spec.command


def test_mapping_finish_starts_save_directly():
    page = _FakeMappingActionSuccessPage()

    started = MappingPage.make_finish_mapping(page)

    assert started is True
    assert page.mapping_runner_task_id == 77
    assert page.operations[-1] == ("结束保存中", "saving")
    assert page.runner.run_calls == 1


def test_mapping_actions_start_without_extra_status_refresh_scheduler():
    for action in (
        MappingPage.make_start_mapping,
        MappingPage.make_finish_mapping,
        MappingPage.make_cancel_mapping,
    ):
        page = _FakeMappingActionSuccessPage()

        assert action(page) is True
        assert page.runner.run_calls == 1


def test_arc_start_action_command_uses_start_arc_enums():
    profile = PRODUCTS["zg_lidar_nx"]
    dock = mapping.arc_start_action_command(profile, "dock", "/ota/alg_data/map/history_map/a/map.pcd")
    undock = mapping.arc_start_action_command(profile, "undock")

    dock_remote = _remote_command(dock, profile.target)
    undock_remote = _remote_command(undock, profile.target)

    assert dock.title == "回充"
    assert "start_arc_align_coarse" in dock_remote
    assert "MONITOR_SECONDS = int(sys.argv[2])" in dock_remote
    assert " dock 120" in dock_remote
    assert "ros2 topic pub --once /arc/start_arc" not in dock_remote
    assert "/ota/alg_data/map/history_map/a/map.pcd" not in dock_remote
    assert "get_arc_alg_status" in dock_remote
    assert "get_arc_dock_status" in dock_remote
    assert "ARC_ERROR_CODES = set()" in dock_remote
    assert "ARC 无图进桩失败" in dock_remote
    assert '"Passive", "UnDockReset", "ChargedExit"' in dock_remote
    assert "DOCK_NOT_READY" in dock_remote
    assert "完成蓝牙/UWB/桩配对" in dock_remote
    assert "清理遗留控制权发布器" not in dock_remote
    assert "/control_right/test" not in dock_remote
    assert "'{data: true}'" not in dock_remote
    assert "/robot_roamerx/is_in_nav_control" not in dock_remote
    assert "'{data: false}'" not in dock_remote
    assert "已启动 ARC 动作控制权抢占/保持任务" not in dock_remote
    assert "robot-launch start robot_roamerx" in dock.command
    assert undock.title == "出桩"
    assert "exit_charging" in undock_remote
    assert "undock_success_seen = False" in undock_remote
    assert 'alg == "Success"' in undock_remote
    assert "不能仅凭 StandBy 判定成功" in undock_remote
    assert "EXIT_DOCK_FAILURE" in undock_remote
    assert "/control_right/test" not in undock_remote
    assert "'{data: true}'" not in undock_remote
    assert "/robot_roamerx/is_in_nav_control" not in undock_remote
    assert "'{data: false}'" not in undock_remote
    assert "/robot_control_server/current_requester_info" in undock.command
    assert "出桩前清理本工具遗留控制权发布器" in undock.command
    assert "/control_right/test" in undock.command
    assert "'{data: false}'" in undock.command
    assert "dog_remote_arc_undock_pre_release_control_right.log" in undock.command
    assert "出桩前检测到底盘控制权占用" in undock.command
    assert "正在尝试抢占/切换控制权" in undock.command
    assert "出桩控制权处理后 requester=" in undock.command
    assert "robot_remote_has_client" in undock.command
    assert "is_allowed_undock_requester" in undock.command
    assert '"arc" in normalized or "charg" in normalized' in undock.command
    assert "restart_robot_remote_if_possible" in undock.command
    assert '"restart", "robot_remote"' in undock.command
    assert "仍被 robot_remote 占用" in undock.command
    assert "请关闭对应 app 后再出桩" in undock.command
    assert "/robot_control_server/current_requester_info" not in dock.command
    assert "出桩前清理本工具遗留控制权发布器" not in dock.command
    assert "robot-launch start robot_roamerx" in undock.command
    assert "locks=(" not in undock_remote


def test_arc_start_action_command_clamps_monitor_seconds_to_120():
    profile = PRODUCTS["zg_lidar_nx"]

    spec = mapping.arc_start_action_command(profile, "undock", monitor_seconds=999)
    remote = _remote_command(spec, profile.target)

    assert " undock 120" in remote


def test_arc_release_control_command_publishes_false():
    profile = PRODUCTS["zg_lidar_nx"]

    spec = mapping.arc_release_control_command(profile)
    remote = _remote_command(spec, profile.target)

    assert spec.title == "ARC 释放控制权"
    assert spec.dangerous is False
    assert "/control_right/test" in remote
    assert "'{data: false}'" in remote
    assert "dog_remote_arc_control_release.log" in remote


def test_arc_status_snapshot_command_reads_dock_and_arc_topics():
    command = mapping.arc_status_snapshot_command(PRODUCTS["zg_lidar_nx"])

    assert "/arc/dock_state" in command
    assert "/arc/arc_state" in command
    assert "/arc/dock_pose" in command
    assert "ARC_DOCK_DETECTED" in command
    assert "ARC_DOCK_TEXT" in command
    assert "/navigation_state" in command
    assert "ARC_APP_CHANNEL=SKIPPED_NAV_ACTIVE" in command
    assert "ARC_NAV_TASK_STATUS" in command
    assert 'APP_WS_BROKER_SOCKET = "/tmp/dog_remote_app_ws.sock"' in command
    assert "class AppWsBrokerClient:" in command
    assert "ESTAB.*:10010" not in command
    assert "ARC_APP_CHANNEL=BUSY" not in command
    assert "ARC_APP_ALG_STATUS" in command
    assert "充电中" in command


def test_arc_commands_for_zg3588_run_on_arc_compute_target():
    source = PRODUCTS["zg3588"]
    arc_target = PRODUCTS["zg_lidar_nx"]

    spec = mapping.arc_start_action_command(source, "undock")
    remote = _remote_command(spec, arc_target.target)

    assert arc_target.target in spec.command
    assert source.target in spec.command
    assert "robot-launch start robot_roamerx" in spec.command
    assert "exit_charging" in remote


def test_arc_status_for_zg3588_reads_compute_target():
    source = PRODUCTS["zg3588"]
    arc_target = PRODUCTS["zg_lidar_nx"]

    command = mapping.arc_status_snapshot_command(source)

    assert arc_target.target in command
    assert "ProxyCommand=" in command
    assert source.target in command
    assert "/arc/dock_state" in _remote_command(CommandSpec("status", command), arc_target.target)


class _FakeMappingSpec:
    title = "保存编辑地图"
    dangerous = False
    description = ""


class _FakeMappingRunPage:
    def __init__(self):
        self.current_spec = _FakeMappingSpec()
        self.runner = _FakeRunner(task_id=None)
        self.mapping_operation_active = True
        self.mapping_runner_task_id = 41
        self.operations = []

    def display_command_for_log(self):
        return self.current_spec.title

    def set_mapping_operation(self, text, state="idle"):
        self.operations.append((text, state))

    def _handle_mapping_run_not_started(self):
        MappingPage._handle_mapping_run_not_started(self)

    def _clear_mapping_run_tracking(self):
        MappingPage._clear_mapping_run_tracking(self)


def test_mapping_run_current_clears_pending_when_runner_rejects_start():
    page = _FakeMappingRunPage()

    started = MappingPage.run_current(page)

    assert started is False
    assert page.mapping_operation_active is False
    assert page.mapping_runner_task_id == 0
    assert page.operations[-1] == ("任务未启动", "blocked")


class _FakeMappingActionButtonsPage:
    def __init__(self, *, alg_status="", operation="空闲", supported=True):
        self.start_mapping_btn = _FakeButton()
        self.finish_mapping_btn = _FakeButton()
        self.cancel_mapping_btn = _FakeButton()
        self.refresh_status_btn = _FakeButton()
        self.last_mapping_alg_status = alg_status
        self.mapping_operation_title = operation
        self.supported = supported

    def profile(self):
        return PRODUCTS["xg2_s100"]

    def mapping_supported(self):
        return self.supported


def test_mapping_action_buttons_keep_visible_slots_by_remote_state():
    idle = _FakeMappingActionButtonsPage()

    MappingPage.update_mapping_action_buttons(idle)

    assert idle.start_mapping_btn.visible is True
    assert idle.start_mapping_btn.enabled is True
    assert idle.start_mapping_btn.object_name == "Primary"
    assert idle.finish_mapping_btn.visible is True
    assert idle.finish_mapping_btn.enabled is False
    assert idle.finish_mapping_btn.object_name == "SoftPrimary"
    assert idle.cancel_mapping_btn.enabled is False
    assert idle.refresh_status_btn.enabled is True

    mapping_remote = _FakeMappingActionButtonsPage(alg_status="MappingRunning")

    MappingPage.update_mapping_action_buttons(mapping_remote)

    assert mapping_remote.start_mapping_btn.visible is True
    assert mapping_remote.start_mapping_btn.enabled is False
    assert mapping_remote.start_mapping_btn.object_name == "SoftPrimary"
    assert mapping_remote.finish_mapping_btn.visible is True
    assert mapping_remote.finish_mapping_btn.enabled is True
    assert mapping_remote.finish_mapping_btn.object_name == "Primary"
    assert mapping_remote.cancel_mapping_btn.enabled is True
    assert "正在建图" in mapping_remote.cancel_mapping_btn.tooltip

    starting_without_remote_active = _FakeMappingActionButtonsPage(operation="开始建图中")

    MappingPage.update_mapping_action_buttons(starting_without_remote_active)

    assert starting_without_remote_active.start_mapping_btn.enabled is False
    assert starting_without_remote_active.finish_mapping_btn.enabled is True
    assert starting_without_remote_active.cancel_mapping_btn.enabled is False
    assert "状态确认为建图中" in starting_without_remote_active.cancel_mapping_btn.tooltip

    saving = _FakeMappingActionButtonsPage(alg_status="MappingRunning", operation="结束保存中")

    MappingPage.update_mapping_action_buttons(saving)

    assert saving.start_mapping_btn.enabled is False
    assert saving.finish_mapping_btn.visible is True
    assert saving.finish_mapping_btn.enabled is False
    assert saving.cancel_mapping_btn.enabled is False


class _FakeLabel:
    def __init__(self, text=""):
        self._text = text
        self.tooltip = ""
        self.style = ""

    def text(self):
        return self._text

    def setText(self, text):
        self._text = text

    def setToolTip(self, tooltip):
        self.tooltip = tooltip

    def setStyleSheet(self, style):
        self.style = style


class _FakePanel:
    def __init__(self):
        self.hidden = False

    def hide(self):
        self.hidden = True

    def show(self):
        self.hidden = False


class _FakeLayoutItem:
    def __init__(self, widget):
        self._widget = widget

    def widget(self):
        return self._widget


class _FakeLayout:
    def __init__(self):
        self.widgets = []

    def count(self):
        return len(self.widgets)

    def takeAt(self, index):
        return _FakeLayoutItem(self.widgets.pop(index))

    def addWidget(self, widget, *_args):
        self.widgets.append(widget)


class _FakeButton:
    def __init__(self):
        self.visible = True
        self.enabled = True
        self.tooltip = ""
        self.object_name = ""

    def setVisible(self, visible):
        self.visible = visible

    def setEnabled(self, enabled):
        self.enabled = enabled

    def setToolTip(self, tooltip):
        self.tooltip = tooltip

    def setObjectName(self, name):
        self.object_name = name



class _FakeProcess:
    def __init__(self):
        self.readyReadStandardOutput = _FakeSignal()
        self.finished = _FakeSignal()
        self.started = False

    def start(self):
        self.started = True


class _FakeSlot:
    def __init__(self, running=False, read_result=False, output=""):
        self.running = running
        self.start_calls = []
        self.stop_calls = 0
        self.read_result = read_result
        self.read_calls = []
        self.finish_output = output
        self.finish_calls = []
        self.process = _FakeProcess()
        self.runner = None

    def is_running(self):
        return self.running

    def start_bash(self, command):
        self.start_calls.append(command)
        self.running = True
        return self.process, 21

    def start_spec(self, spec, **_kwargs):
        if self.runner is not None and self.runner.conflict_reason(spec):
            return None, 0
        return self.start_bash(spec.command)

    def stop(self):
        self.stop_calls += 1
        was_running = self.running
        self.running = False
        return was_running

    def read_available_output(self, process, request_id):
        self.read_calls.append((process, request_id))
        return self.read_result

    def finish(self, process, request_id):
        self.finish_calls.append((process, request_id))
        self.running = False
        return self.finish_output


class _FakeMapSelector:
    def __init__(self, current="/opt/data/.robot/map/history_map/a/map.pgm"):
        self.current = current
        self.cleared = False
        self.items = []
        self.tooltips = {}
        self.current_index = 0 if current else -1
        if current:
            self.items.append(("current", current))

    def currentData(self):
        if 0 <= self.current_index < len(self.items):
            return self.items[self.current_index][1]
        return self.current

    def clear(self):
        self.cleared = True
        self.items = []
        self.tooltips = {}
        self.current_index = -1

    def addItem(self, label, data):
        self.items.append((label, data))
        if self.current_index < 0:
            self.current_index = 0

    def setItemData(self, index, value, _role):
        self.tooltips[index] = value

    def count(self):
        return len(self.items)

    def findData(self, data):
        for index, (_label, item_data) in enumerate(self.items):
            if item_data == data:
                return index
        return -1

    def setCurrentIndex(self, index):
        self.current_index = index

    def currentIndex(self):
        return self.current_index


class _FakeMappingRefreshPage:
    def __init__(
        self,
        *,
        active=True,
        supported=True,
        status_running=False,
        list_running=False,
        fetch_running=False,
        selected_map="/opt/data/.robot/map/history_map/a/map.pgm",
    ):
        self.page_active = active
        self.supported = supported
        self.status_slot = _FakeSlot(status_running)
        self.map_list_slot = _FakeSlot(list_running)
        self.map_fetch_slot = _FakeSlot(fetch_running)
        self.mapping_operation_active = False
        self.mapping_operation_title = ""
        self.last_mapping_status_state = "ready"
        self.last_mapping_alg_status = "MappingRunning"
        self.last_mapping_status_at = time.monotonic()
        self.statuses = []
        self.preview_status = _FakeLabel()
        self.map_selector = _FakeMapSelector(selected_map)
        self.map_entry_details = {"x": "y"}
        self.map_entries_signature = ("old",)
        self.force_preview_after_list = False
        self.force_latest_after_list = False
        self.preview_autoload_enabled = True
        self.fetch_selected_preview_calls = []
        self.preview_remote_pgm = ""
        self.preview_pixmap = None
        self.fetching_preview_remote_pgm = ""
        self.preview_file = ""
        self.selected_map_detail = _FakeLabel()
        self.runner = _FakeRunner()
        for slot in (self.status_slot, self.map_list_slot, self.map_fetch_slot):
            slot.runner = self.runner
        self.refresh_calls = []
        self.operations = []

    def profile(self):
        return PRODUCTS["xg2_s100"]

    def mapping_supported(self):
        return self.supported

    def mapping_values(self):
        return (
            "richbeam",
            "/opt/data/.robot/map",
            "/opt/data/.robot/calibration.yaml",
            "/opt/data/.robot/arc.yaml",
        )

    def set_mapping_status(self, state, text, detail):
        self.statuses.append((state, text, detail))

    def read_status_output(self, process, request_id):
        return MappingPage.read_status_output(self, process, request_id)

    def status_finished(self, process, exit_code, request_id, profile):
        return MappingPage.status_finished(self, process, exit_code, request_id, profile)

    def read_map_list_output(self, process, request_id):
        return MappingPage.read_map_list_output(self, process, request_id)

    def map_list_finished(self, process, exit_code, request_id):
        return MappingPage.map_list_finished(self, process, exit_code, request_id)

    def read_map_fetch_output(self, process, request_id):
        return MappingPage.read_map_fetch_output(self, process, request_id)

    def map_fetch_finished(self, process, exit_code, request_id):
        return MappingPage.map_fetch_finished(self, process, exit_code, request_id)

    def update_selected_map_detail(self):
        self.selected_map_detail.setText("updated")

    def refresh_mapping_status(self):
        return MappingPage.refresh_mapping_status(self)

    def refresh_mapping_page(self):
        return MappingPage.refresh_mapping_page(self)

    def selected_remote_map_pgm(self):
        return str(self.map_selector.currentData() or "")

    def fetch_map_preview(self, force=False):
        return MappingPage.fetch_map_preview(self, force=force)

    def fetch_selected_map_preview(self, force=False):
        self.fetch_selected_preview_calls.append(force)
        return True

    def refresh_map_list(self, *, silent=False, force_preview=False, force_latest=False):
        self.refresh_calls.append((silent, force_preview, force_latest))
        return True

    def _local_map_preview_cache_ready(self, local_dir):
        return MappingPage._local_map_preview_cache_ready(self, local_dir)

    def _load_map_preview_from_local(self, remote_pgm, *, cached):
        return MappingPage._load_map_preview_from_local(self, remote_pgm, cached=cached)

    def set_mapping_operation(self, text, state="idle"):
        self.operations.append((text, state))

    def mapping_probe_process_running(self):
        return self.status_slot.is_running()

    def local_preview_dir(self, remote_pgm, profile):
        return map_helpers.local_map_preview_dir(profile.key, profile.host, remote_pgm, "/tmp/maps")


class _FakeLatestPreviewRefreshPage:
    def __init__(self, refresh_result=True):
        self.force_latest_after_list = False
        self.force_preview_after_list = False
        self.preview_remote_pgm = "old"
        self.preview_status = _FakeLabel()
        self.refresh_result = refresh_result
        self.refresh_calls = []

    def refresh_map_list(self, *, silent=False, force_preview=False, force_latest=False):
        self.refresh_calls.append((silent, force_preview, force_latest))
        return self.refresh_result


class _FakeNullPixmap:
    def isNull(self):
        return True


class _FakeMappingStatusPage:
    def __init__(self):
        self.commands = []
        self.statuses = []

    def profile(self):
        return PRODUCTS["xg2_s100"]

    def mapping_values(self):
        return (
            "richbeam",
            "/opt/data/.robot/map",
            "/opt/data/.robot/calibration.yaml",
            "/opt/data/.robot/arc.yaml",
        )

    def set_command(self, spec):
        self.commands.append(spec)
        return False

    def set_mapping_status(self, state, text, detail):
        self.statuses.append((state, text, detail))


def test_mapping_refresh_status_returns_start_result():
    inactive = _FakeMappingRefreshPage(active=False)

    assert MappingPage.refresh_mapping_status(inactive) is False
    assert inactive.status_slot.start_calls == []

    unsupported = _FakeMappingRefreshPage(supported=False)

    assert MappingPage.refresh_mapping_status(unsupported) is False
    assert unsupported.last_mapping_status_state == "unknown"
    assert unsupported.statuses == [("unknown", "当前设备不支持建图", "请选择小狗二代 S100、NX 或中狗建图目标。")]

    busy = _FakeMappingRefreshPage(status_running=True)

    assert MappingPage.refresh_mapping_status(busy) is False
    assert busy.status_slot.start_calls == []

    page = _FakeMappingRefreshPage()

    assert MappingPage.refresh_mapping_status(page) is True
    assert page.status_slot.process.started is True
    assert len(page.status_slot.start_calls) == 1
    assert "/opt/data/.robot/map" in page.status_slot.start_calls[0]


def test_mapping_refresh_status_skips_while_mapping_runner_has_lock():
    page = _FakeMappingRefreshPage()
    page.runner.conflict = "当前任务与正在运行的任务冲突：开始建图"

    assert MappingPage.refresh_mapping_status(page) is False
    assert page.status_slot.start_calls == []


def test_mapping_refresh_page_refreshes_status_and_map_list():
    page = _FakeMappingRefreshPage()

    assert MappingPage.refresh_mapping_page(page) is True
    assert page.status_slot.process.started is True
    assert page.refresh_calls == [(False, True, True)]


def test_mapping_activate_page_does_not_repeat_auto_refresh(monkeypatch):
    scheduled = []
    monkeypatch.setattr(
        "dog_remote_tool.ui.pages.mapping.page.QTimer.singleShot",
        lambda delay, callback: scheduled.append((delay, getattr(callback, "__name__", ""))),
    )
    page = _FakeMappingRefreshPage(active=False)

    MappingPage.activate_page(page)

    assert page.page_active is True
    assert scheduled == [(200, "refresh_mapping_page")]

    MappingPage.activate_page(page)

    assert scheduled == [(200, "refresh_mapping_page")]


def test_mapping_read_callbacks_return_slot_result():
    page = _FakeMappingRefreshPage()
    page.status_slot = _FakeSlot(read_result=False)
    page.map_list_slot = _FakeSlot(read_result=True)
    page.map_fetch_slot = _FakeSlot(read_result=False)

    assert MappingPage.read_status_output(page, page.status_slot.process, request_id=32) is False
    assert page.status_slot.read_calls == [(page.status_slot.process, 32)]

    assert MappingPage.read_map_list_output(page, page.map_list_slot.process, request_id=33) is True
    assert page.map_list_slot.read_calls == [(page.map_list_slot.process, 33)]

    assert MappingPage.read_map_fetch_output(page, page.map_fetch_slot.process, request_id=34) is False
    assert page.map_fetch_slot.read_calls == [(page.map_fetch_slot.process, 34)]


def test_mapping_finished_callbacks_return_accept_result(monkeypatch):
    class FakeBlocker:
        def __init__(self, _target):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

    monkeypatch.setattr("dog_remote_tool.ui.pages.mapping.page.QSignalBlocker", FakeBlocker)

    status_stale = _FakeMappingRefreshPage()
    status_stale.status_slot = _FakeSlot(output=None)

    assert MappingPage.status_finished(status_stale, status_stale.status_slot.process, exit_code=0, request_id=38, profile=status_stale.profile()) is False

    status_failed = _FakeMappingRefreshPage()
    status_failed.status_slot = _FakeSlot(output="ssh failed\n")

    assert MappingPage.status_finished(status_failed, status_failed.status_slot.process, exit_code=1, request_id=39, profile=status_failed.profile()) is True
    assert status_failed.last_mapping_status_state == "unknown"
    assert status_failed.statuses[-1][0] == "unknown"

    status_ok = _FakeMappingRefreshPage()
    status_ok.status_slot = _FakeSlot(output="STATUS=ready\nTEXT=空闲\nALG_MAPPING_STATUS=MappingRunning\n")

    assert MappingPage.status_finished(status_ok, status_ok.status_slot.process, exit_code=0, request_id=40, profile=status_ok.profile()) is True
    assert status_ok.last_mapping_status_state == "mapping"
    assert status_ok.last_mapping_alg_status == "MappingRunning"
    assert status_ok.statuses[-1][0] == "mapping"

    status_saved = _FakeMappingRefreshPage()
    status_saved.last_mapping_alg_status = "MappingRunning"
    status_saved.status_slot = _FakeSlot(output="STATUS=ready\nTEXT=空闲\nALG_MAPPING_STATUS=MappingSaved\n")

    assert MappingPage.status_finished(status_saved, status_saved.status_slot.process, exit_code=0, request_id=44, profile=status_saved.profile()) is True
    assert status_saved.refresh_calls == []

    assert MappingPage.status_finished(status_saved, status_saved.status_slot.process, exit_code=0, request_id=45, profile=status_saved.profile()) is True
    assert status_saved.refresh_calls == []

    inferred_saved = _FakeMappingRefreshPage()
    inferred_saved.mapping_operation_active = True
    inferred_saved.mapping_operation_title = "保存确认中"
    inferred_saved.last_mapping_status_state = "saving"
    inferred_saved.last_mapping_alg_status = "MappingReady"
    inferred_saved.status_slot = _FakeSlot(
        output="\n".join(
            [
                "STATUS=ready",
                "TEXT=空闲",
                "MAP_COUNT=3",
                "LATEST_MAP=/opt/data/.robot/map/history_map/new/map.pgm",
                "LATEST_MAP_AGE=12",
            ]
        )
    )

    assert (
        MappingPage.status_finished(
            inferred_saved,
            inferred_saved.status_slot.process,
            exit_code=0,
            request_id=46,
            profile=inferred_saved.profile(),
        )
        is True
    )
    assert inferred_saved.statuses[-1][0:2] == ("success", "保存完成")
    assert inferred_saved.operations == [("保存完成", "done")]
    assert inferred_saved.mapping_operation_active is False
    assert inferred_saved.refresh_calls == []

    status_live = _FakeMappingRefreshPage()
    status_live.last_mapping_alg_status = "MappingRunning"

    assert MappingPage.capture_mapping_runner_output(status_live, "[INFO] 建图状态：保存中（MappingSaving）\n") is True
    assert status_live.last_mapping_status_state == "saving"
    assert status_live.last_mapping_alg_status == "MappingSaving"
    assert status_live.statuses[-1][0:2] == ("saving", "保存中")
    assert status_live.statuses[-1][2] == "远端状态：保存中"
    assert status_live.refresh_calls == []

    assert MappingPage.capture_mapping_runner_output(status_live, "[INFO] 地图已保存：/ota/alg_data/map/history_map/a/map.pgm\n") is True
    assert status_live.last_mapping_status_state == "success"
    assert status_live.last_mapping_alg_status == "MappingSaved"
    assert status_live.statuses[-1][0:2] == ("success", "保存完成")
    assert status_live.refresh_calls == [(False, True, True)]

    status_r3 = _FakeMappingRefreshPage()
    status_r3.last_mapping_alg_status = "MappingReady"

    assert (
        MappingPage.capture_mapping_runner_output(
            status_r3,
            "[INFO] 建图状态：建图中（MappingRunning）\n",
        )
        is True
    )
    assert status_r3.last_mapping_status_state == "mapping"
    assert status_r3.last_mapping_alg_status == "MappingRunning"
    assert status_r3.statuses[-1][0:2] == ("mapping", "建图中")


def test_mapping_update_map_cards_reuses_existing_cards(monkeypatch):
    created = []

    class FakeCard:
        compact_label = staticmethod(lambda label, _remote_pgm: label)

        def __init__(self, label, remote_pgm, detail):
            self.remote_pgm = remote_pgm
            self.title = _FakeLabel(label)
            self.tooltip = detail
            self.deleted = False
            self.clicked = _FakeSignal()
            created.append(self)

        def setToolTip(self, detail):
            self.tooltip = detail

        def deleteLater(self):
            self.deleted = True

        def set_selected(self, _selected):
            pass

    monkeypatch.setattr(mapping_map_history, "MapHistoryCard", FakeCard)
    page = _FakeMappingRefreshPage()
    page.map_cards_layout = _FakeLayout()
    page.map_cards_empty = _FakePanel()
    page.map_cards_panel = _FakePanel()
    page.map_cards = {}
    page.select_history_map = lambda _remote_pgm: True
    page.update_map_card_thumbnail = lambda *_args, **_kwargs: True
    page.preload_map_card_thumbnails = lambda *_args, **_kwargs: None

    MappingPage.update_map_cards(
        page,
        [("a", "/map/a.pgm", "old"), ("b", "/map/b.pgm", "old"), ("d", "/map/d.pgm", "old")],
    )
    first_a = page.map_cards["/map/a.pgm"]

    MappingPage.update_map_cards(
        page,
        [("a2", "/map/a.pgm", "new"), ("c", "/map/c.pgm", "new"), ("e", "/map/e.pgm", "new")],
    )

    assert page.map_cards["/map/a.pgm"] is first_a
    assert page.map_cards["/map/a.pgm"].tooltip == "new"
    assert len(created) == 5

    class FakeBlocker:
        def __init__(self, _target):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

    monkeypatch.setattr("dog_remote_tool.ui.pages.mapping.page.QSignalBlocker", FakeBlocker)

    list_stale = _FakeMappingRefreshPage()
    list_stale.map_list_slot = _FakeSlot(output=None)

    assert MappingPage.map_list_finished(list_stale, list_stale.map_list_slot.process, exit_code=0, request_id=41) is False

    list_failed = _FakeMappingRefreshPage()
    list_failed.force_latest_after_list = True
    list_failed.force_preview_after_list = True
    list_failed.map_list_slot = _FakeSlot(output="ssh failed")

    assert MappingPage.map_list_finished(list_failed, list_failed.map_list_slot.process, exit_code=1, request_id=42) is True
    assert list_failed.force_latest_after_list is False
    assert list_failed.force_preview_after_list is False
    assert list_failed.preview_status.text() == "历史列表读取失败"

    list_ok = _FakeMappingRefreshPage(selected_map="")
    list_ok.map_list_slot = _FakeSlot(output="1700000000\t2026-05-25 09:30:11\t2048\t/opt/data/.robot/map/history_map/a/map.pgm\n")

    assert MappingPage.map_list_finished(list_ok, list_ok.map_list_slot.process, exit_code=0, request_id=43) is True
    assert list_ok.map_entries_signature
    assert list_ok.map_selector.items[0][1] == "/opt/data/.robot/map/history_map/a/map.pgm"
    assert list_ok.preview_autoload_enabled is True
    assert list_ok.selected_map_detail.text() == "updated"


def test_mapping_map_fetch_finished_returns_accept_result():
    stale = _FakeMappingRefreshPage()
    stale.map_fetch_slot = _FakeSlot(output=None)

    assert MappingPage.map_fetch_finished(stale, stale.map_fetch_slot.process, exit_code=0, request_id=44) is False

    changed = _FakeMappingRefreshPage(selected_map="/opt/data/.robot/map/history_map/new/map.pgm")
    changed.fetching_preview_remote_pgm = "/opt/data/.robot/map/history_map/old/map.pgm"
    changed.map_fetch_slot = _FakeSlot(output="ok")

    assert MappingPage.map_fetch_finished(changed, changed.map_fetch_slot.process, exit_code=0, request_id=45) is True
    assert changed.fetching_preview_remote_pgm == ""
    assert changed.fetch_selected_preview_calls == [True]

    failed = _FakeMappingRefreshPage()
    failed.fetching_preview_remote_pgm = failed.selected_remote_map_pgm()
    failed.map_fetch_slot = _FakeSlot(output="permission denied")

    assert MappingPage.map_fetch_finished(failed, failed.map_fetch_slot.process, exit_code=1, request_id=46) is True
    assert failed.preview_status.text() == "map.pgm 拉取失败，请查看执行日志"
    assert failed.preview_status.tooltip == "permission denied"
    assert failed.runner.output_lines[-1] == "[WARN] 地图预览拉取失败：\npermission denied\n"


def test_mapping_map_fetch_finished_loads_preview(monkeypatch):
    class FakePixmap:
        def __init__(self, _path):
            pass

        def isNull(self):
            return False

        def scaled(self, *_args):
            return self

        def width(self):
            return 640

        def height(self):
            return 480

    page = _FakeMappingRefreshPage()
    page.fetching_preview_remote_pgm = page.selected_remote_map_pgm()
    page.preview_file = "/tmp/map.pgm"
    page.map_fetch_slot = _FakeSlot(output="ok")
    monkeypatch.setattr("dog_remote_tool.ui.pages.mapping.page.QPixmap", FakePixmap)

    assert MappingPage.map_fetch_finished(page, page.map_fetch_slot.process, exit_code=0, request_id=47) is True
    assert page.preview_remote_pgm == page.selected_remote_map_pgm()
    assert page.preview_pixmap is not None
    assert page.preview_status.text() == "已加载：640x480"


def test_mapping_map_list_returns_start_result():
    unsupported = _FakeMappingRefreshPage(supported=False)

    assert MappingPage.refresh_map_list(unsupported, silent=False) is False
    assert unsupported.preview_status.text() == "当前设备不支持地图读取"
    assert unsupported.map_selector.cleared is True

    busy = _FakeMappingRefreshPage(list_running=True)

    assert MappingPage.refresh_map_list(busy, silent=False) is False
    assert busy.preview_status.text() == "历史列表正在刷新"
    assert busy.map_list_slot.start_calls == []

    page = _FakeMappingRefreshPage()

    assert MappingPage.refresh_map_list(page, silent=False, force_preview=True, force_latest=True) is True
    assert page.force_preview_after_list is True
    assert page.force_latest_after_list is True
    assert page.map_list_slot.process.started is True
    assert len(page.map_list_slot.start_calls) == 1
    assert "/opt/data/.robot/map" in page.map_list_slot.start_calls[0]


def test_selecting_current_history_map_does_not_refetch_preview():
    page = _FakeMappingRefreshPage()

    assert MappingPage.select_history_map(page, page.selected_remote_map_pgm()) is True

    assert page.fetch_selected_preview_calls == []


def test_mapping_preview_fetch_returns_start_result(monkeypatch):
    disabled = _FakeMappingRefreshPage()
    disabled.preview_autoload_enabled = False

    assert MappingPage.fetch_selected_map_preview(disabled, force=True) is False

    unsupported = _FakeMappingRefreshPage(supported=False)

    assert MappingPage.fetch_map_preview(unsupported, force=True) is False
    assert unsupported.preview_status.text() == "当前设备不支持地图预览"

    busy = _FakeMappingRefreshPage(fetch_running=True)

    assert MappingPage.fetch_map_preview(busy, force=False) is False
    assert busy.preview_status.text() == "map.pgm 正在拉取中"
    assert busy.map_fetch_slot.stop_calls == 0

    no_map = _FakeMappingRefreshPage(selected_map="")
    monkeypatch.setattr(QMessageBox, "information", lambda *args, **kwargs: None)

    assert MappingPage.fetch_map_preview(no_map, force=True) is False
    assert no_map.map_fetch_slot.start_calls == []

    page = _FakeMappingRefreshPage()

    assert MappingPage.fetch_selected_map_preview(page, force=True) is True
    assert page.map_fetch_slot.process.started is True
    assert page.fetching_preview_remote_pgm == "/opt/data/.robot/map/history_map/a/map.pgm"
    assert len(page.map_fetch_slot.start_calls) == 1


def test_mapping_preview_fetch_uses_local_cache_without_remote_fetch(monkeypatch, tmp_path):
    class FakePixmap:
        def __init__(self, _path):
            pass

        def isNull(self):
            return False

        def scaled(self, *_args):
            return self

        def width(self):
            return 640

        def height(self):
            return 480

    (tmp_path / "map.pgm").write_text("P2\n1 1\n255\n0\n")
    (tmp_path / "map.yaml").write_text("image: map.pgm\n")
    page = _FakeMappingRefreshPage()
    page.local_preview_dir = lambda _remote_pgm, _profile: tmp_path
    monkeypatch.setattr("dog_remote_tool.ui.pages.mapping.page.QPixmap", FakePixmap)

    assert MappingPage.fetch_map_preview(page, force=False) is True
    assert page.map_fetch_slot.start_calls == []
    assert page.preview_remote_pgm == page.selected_remote_map_pgm()
    assert page.preview_pixmap is not None
    assert page.preview_status.text() == "已加载本地缓存：640x480"


def test_image_preview_open_returns_display_result(monkeypatch):
    messages = []
    monkeypatch.setattr(QMessageBox, "information", lambda *args, **kwargs: messages.append(args))

    assert image_preview.show_zoomable_pixmap(None, "预览", _FakeNullPixmap(), "/tmp/map.pgm") is False
    assert len(messages) == 1


class _FakeMappingHistoryActionPage:
    def __init__(self):
        self.runner = _FakeRunner(task_id=None)
        self.commands = []
        self.operations = []
        self.preview_status = _FakeLabel()

    def profile(self):
        return PRODUCTS["xg2_s100"]

    def mapping_values(self):
        return (
            "richbeam",
            "/opt/data/.robot/map",
            "/opt/data/.robot/calibration.yaml",
            "/opt/data/.robot/arc.yaml",
        )

    def selected_remote_map_pgm(self):
        return "/opt/data/.robot/map/history_map/2026_05_25_09_30_00/map.pgm"

    def set_command(self, spec):
        self.commands.append(spec)
        return False

    def set_mapping_operation(self, text, state="idle"):
        self.operations.append((text, state))


def test_mapping_delete_selected_map_marks_not_started_when_runner_rejects_start(monkeypatch):
    page = _FakeMappingHistoryActionPage()
    confirmations = []
    monkeypatch.setattr(
        mapping_transfer_actions,
        "confirm_dangerous_action",
        lambda parent, title, detail, **kwargs: confirmations.append((title, detail, kwargs)) or True,
    )
    monkeypatch.setattr(
        mapping,
        "delete_history_map_command",
        lambda profile, remote_pgm, save_map_path: CommandSpec("删除地图", f"delete {remote_pgm} {save_map_path}"),
    )

    started = MappingPage.make_delete_selected_map(page)

    assert started is False
    assert confirmations
    assert confirmations[0][0] == "确认删除地图"
    assert "2026_05_25_09_30_00" in confirmations[0][1]
    assert "/opt/data/.robot/map/history_map" not in confirmations[0][1]
    assert [command.title for command in page.commands] == ["删除地图"]
    assert page.commands[0].command == (
        "delete /opt/data/.robot/map/history_map/2026_05_25_09_30_00/map.pgm /opt/data/.robot/map"
    )
    assert page.operations == [("任务未启动", "blocked")]
    assert page.preview_status.text() == "地图删除未启动，当前有任务运行，请稍后再试。"


class _FakeTimer:
    def __init__(self):
        self.stopped = False
        self.started = False
        self.start_count = 0
        self.stop_count = 0

    def stop(self):
        self.stopped = True
        self.stop_count += 1

    def start(self):
        self.started = True
        self.start_count += 1


def test_navigation_helper_output_dir_strips_history_map_layer(tmp_path):
    local_root = tmp_path / "maps"
    target = navigation_helpers.local_map_directory(
        "/opt/data/.robot/map/history_map/2026_05_27_09_39_34/map.pgm",
        "/opt/data/.robot/map",
        str(local_root),
    )

    assert target == local_root / "2026_05_27_09_39_34"


def test_mapping_probe_exports_keep_status_entrypoints():
    profile = PRODUCTS["xg2_s100"]

    probe_command = mapping.probe_status_command(profile, "/opt/data/.robot/map")

    assert "MAP_COUNT=" in probe_command
    assert "LATEST_MAP_AGE=" in probe_command
    assert "LOOP_STATUS" not in probe_command
    assert not hasattr(mapping, "status_command")


def test_mapping_status_probe_fails_without_alg_status_fallback():
    profile = PRODUCTS["xg2_s100"]

    probe_command = mapping.probe_status_command(profile, "/opt/data/.robot/map")

    assert "get_mapping_status" in probe_command
    assert "|| exit $?" in probe_command
    assert "MAPPING_APP_STATUS_RC=$?" not in probe_command
    assert "系统应用通道占用" not in probe_command
    assert "echo STATUS=unknown" not in probe_command
    assert probe_command.index("get_mapping_status") < probe_command.index("MAP_COUNT=")


def test_start_mapping_command_uses_alg_app_ws_by_default():
    profile = PRODUCTS["xg2_s100"]

    spec = mapping.start_mapping_command(
        profile,
        mapping.default_sensor_type(profile),
        mapping.default_save_map_path(profile),
        mapping.default_calibration_file_path(profile),
        mapping.default_arc_calibration_file_path(profile),
    )

    assert spec.title == "开始建图"
    assert spec.display_command == "执行：alg 开始建图"
    assert spec.concurrency == "parallel"
    assert spec.locks == ("mapping", "app_ws")
    assert "start_mapping" in spec.command
    assert "get_mapping_status" in spec.command
    assert "ALG_MAPPING_STATUS=" in spec.command
    assert "建图已开始，请移动机器人采集环境。" in spec.command
    assert "robots_dog_msgs/srv/MapState" not in spec.command
    assert "SLAM_CODE_MODE" not in spec.command
    assert "robot-launch stop robot-alg-manager" not in spec.command


def test_medium_dog_s100_mapping_defaults_use_zg_calibration():
    profile = PRODUCTS["zg_surround_s100"]

    assert mapping.default_sensor_type(profile) == "nx_zg"
    assert mapping.default_save_map_path(profile) == "/ota/alg_data/map"
    assert mapping.default_map_pcd_path(profile) == "/ota/alg_data/map/map.pcd"
    assert mapping.default_calibration_file_path(profile) == "/ota/calibration_results.yaml"


def test_l2_s100_mapping_default_uses_available_calibration_results():
    profile = PRODUCTS["xg2_s100"]

    assert mapping.default_save_map_path(profile) == "/ota/alg_data/map"
    assert mapping.default_map_pcd_path(profile) == "/ota/alg_data/map/map.pcd"
    assert mapping.default_calibration_file_path(profile) == "/ota/calibration_results.yaml"


def test_start_mapping_quotes_calibration_path_in_status_message():
    profile = PRODUCTS["xg2_s100"]
    calibration_path = "/opt/data/calib/a'calib.yaml"

    spec = mapping.start_mapping_command(
        profile,
        mapping.default_sensor_type(profile),
        mapping.default_save_map_path(profile),
        calibration_path,
        mapping.default_arc_calibration_file_path(profile),
    )
    remote_command = _remote_command(spec, profile.target)

    assert f"[ ! -f {quote(calibration_path)} ]" in remote_command
    assert quote(f"[ERROR] calibration file missing: {calibration_path}") in remote_command
    assert "echo '[ERROR] calibration file missing:" not in remote_command


def test_localization_probe_exports_keep_status_entrypoints():
    profile = PRODUCTS["xg2_s100"]

    assert localization.probe_status_command is localization_probe.probe_status_command

    probe_command = localization.probe_status_command(profile)
    status_spec = localization.status_command(profile)
    status_remote = _remote_command(status_spec, profile.target)

    assert "get_loc_status" in probe_command
    assert "|| exit $?" in probe_command
    assert "/load_map_service" not in probe_command
    assert "ALG_LOC_STATUS" in probe_command
    assert "robot_slam" not in probe_command
    assert "/robot_slam/localization_state" not in probe_command
    assert "/localization_info" not in probe_command
    assert "dog_remote_cleanup_stale_app_ws" in status_remote
    assert "alg_loc_status_inner" not in status_remote
    assert "ALG_LOC_OUTPUT=$(" in probe_command
    assert "ALG_LOC_OUTPUT=$(" + localization_alg.alg_loc_status_inner() + " || true)" not in probe_command
    assert status_spec.title == "查看定位状态"
    assert status_spec.concurrency == "parallel"


def test_localization_runtime_exports_keep_command_entrypoints():
    assert localization.REMOTE_POSE_RECORD == localization_runtime.REMOTE_POSE_RECORD
    assert localization.start_localization_command is localization_runtime.start_localization_command
    assert localization.test_localization_once_command is localization_runtime.test_localization_once_command
    assert localization.stop_localization_command is localization_runtime.stop_localization_command


def test_localization_map_list_requires_pcd_for_selectable_maps():
    profile = PRODUCTS["xg2_s100"]

    command = localization.list_localization_map_pgm_command(profile, "/opt/data/.robot/map")

    assert "map.pgm" in command
    assert "map.yaml" in command
    assert "map.pcd" in command
    assert "SKIP\\tmissing_pcd" in command


def test_mapping_map_list_only_returns_history_maps():
    profile = PRODUCTS["xg2_s100"]

    command = mapping.list_map_pgm_command(profile, "/opt/data/.robot/map")

    assert "/opt/data/.robot/map/map.pgm" not in command
    assert "/opt/data/.robot/map/map.yaml" not in command
    assert "history_map" in command


def test_mapping_delete_root_map_preserves_history_directory():
    profile = PRODUCTS["xg2_s100"]

    spec = mapping.delete_history_map_command(profile, "/opt/data/.robot/map/map.pgm", "/opt/data/.robot/map")

    assert 'DELETE_MODE=root' in spec.command
    assert 'sudo_run rm -f -- "$TARGET_DIR/map.pgm"' in spec.command
    assert 'sudo_run rm -rf -- "$TARGET_DIR/map.static"' in spec.command
    assert 'sudo_run rm -rf -- "$TARGET_DIR"' in spec.command
    assert "DOG_REMOTE_SUDO_PASS" in spec.command
    assert "delete failed, files still exist" in spec.command
    assert "delete failed, directory still exists" in spec.command
    assert 'if [ -e "$TARGET_DIR" ]; then' in spec.command


def test_localization_map_fetch_uses_rsync_with_retry_instead_of_scp():
    profile = PRODUCTS["xg2_s100"]

    command = localization.fetch_map_files_command(
        profile,
        "/opt/data/.robot/map/history_map/a/map.pgm",
        "/tmp/loc/map.pgm",
        "/tmp/loc/map.yaml",
    )

    assert " rsync -a " in command
    assert " scp " not in command
    assert "ConnectTimeout=20" in command
    assert "fetch_required()" in command
    assert "map.pgm" in command
    assert "map.yaml" in command
    assert "map.txt" in command
    assert "192.168.168.0/24" not in command
    assert "ProxyCommand=" in command


def test_localization_pose_record_fetch_uses_rsync_with_retry_instead_of_scp():
    profile = PRODUCTS["xg2_s100"]

    spec = localization.fetch_pose_record_command(profile, "/tmp/loc/pose_xyz_20260526.txt")

    assert spec.title == "回传定位 pose 记录"
    assert " rsync -a " in spec.command
    assert " scp " not in spec.command
    assert "ConnectTimeout=20" in spec.command
    assert "fetch_required()" in spec.command
    assert "192.168.168.0/24" not in spec.command
    assert "ProxyCommand=" in spec.command


def test_localization_pose_record_fetch_quotes_local_paths_in_status_messages():
    profile = PRODUCTS["xg2_s100"]
    local_file = "/tmp/loc/pose'xyz.txt"
    local_latest = "/tmp/loc/pose_xyz.txt"

    spec = localization.fetch_pose_record_command(profile, local_file)

    assert quote(f"[INFO] 定位 pose 记录已回传: {local_file}") in spec.command
    assert quote(f"[INFO] 最新副本: {local_latest}") in spec.command
    assert "echo '[INFO] 定位 pose 记录已回传:" not in spec.command
    assert "echo '[INFO] 最新副本:" not in spec.command


def test_localization_pose_record_filters_non_csv_log_lines():
    profile = PRODUCTS["xg2_s100"]

    command = localization_pose_record.start_pose_record_inner(
        profile,
        "/home/robot/pose_xyz.txt",
        "/tmp/dog_remote_tool_pose_xyz.pid",
        "/tmp/dog_remote_tool_pose_xyz.log",
    )

    assert "ros2 topic echo /odom/localization_odom --field pose.pose.position --csv --no-daemon" in command
    assert "awk -F," in command
    assert "NF>=3" in command
    assert "fflush()" in command
    assert "2>> /tmp/dog_remote_tool_pose_xyz.log" in command


def test_localization_pose_record_start_quotes_remote_path_in_status_message():
    profile = PRODUCTS["xg2_s100"]
    remote_path = "/home/robot/pose'xyz.txt"

    command = localization_pose_record.start_pose_record_inner(
        profile,
        remote_path,
        "/tmp/dog_remote_tool_pose_xyz.pid",
        "/tmp/dog_remote_tool_pose_xyz.log",
    )

    assert f"rm -f {quote(remote_path)}" in command
    assert quote(f"[INFO] 定位 pose 记录已启动: {remote_path}") in command
    assert "echo '[INFO] 定位 pose 记录已启动:" not in command


def test_localization_once_command_uses_alg_without_robot_localization_launch():
    profile = PRODUCTS["xg2_s100"]

    spec = localization.test_localization_once_command(
        profile,
        "rslidar",
        "/opt/data/.robot/map",
        "/ota/calibration_results.yaml",
        "/opt/robot/robot_arc/install/apriltag_localization/config/apriltag_localization_pc_config.yaml",
        "/opt/data/.robot/map/history_map/test/map.pcd",
    )

    assert "loc_load_map" in spec.command
    assert "get_loc_status" in spec.command
    assert "系统定位流程完成" in spec.command
    assert "ros2 pkg executables localization" not in spec.command
    assert "sudo_run mkdir -p /tmp/log/localization-LOG" not in spec.command
    assert "sudo_run chown -R \"$(id -u):$(id -g)\" /tmp/log/localization-LOG" not in spec.command
    assert "command -v sudo" not in spec.command
    assert "ros2 launch localization localization_zg.launch.py" not in spec.command
    assert "ros2 run robot_slam robot_localization" not in spec.command
    assert "stop_robot_localization" not in spec.command
    assert "[DOG_REMOTE_FINAL_POSE]" in spec.command
    assert "emit_final_pose" in spec.command
    assert "printf '%s\\n' \"$LOAD_RESP\";" not in spec.command
    assert "定位状态 source=" not in spec.command
    assert "/robot_slam/localization_state" not in spec.command
    assert "/localization_info" not in spec.command
    assert "[SUCCESS] 定位成功" in spec.command
    assert "清理本次定位测试资源" in spec.command


def test_localization_alg_load_inner_uses_app_channel_and_map_id():
    profile = PRODUCTS["zg_lidar_nx"]
    map_path = "/ota/alg_data/map/history_map/2026_06_11_22_14_49/map.pcd"

    command = localization_alg.alg_localization_load_inner(profile, map_path)

    assert "dog_remote_alg_localization_load()" in command
    assert "loc_load_map" in command
    assert "get_loc_status" in command
    assert "reset_loc" not in command
    assert "state does not allow load map" not in command
    assert "alg定位地图加载重试" not in command
    assert "DOG_REMOTE_LOC_MAP_MARKER" in command
    assert "当前地图已连续定位，跳过重复 loc_load_map" in command
    assert "continuousloc" in command
    assert "2026_06_11_22_14_49" in command
    assert "/ota/alg_data/map/history_map/2026_06_11_22_14_49/map.yaml" in command
    assert "robot_localization 已启动" not in command
    assert "ros2 launch localization" not in command


def test_localization_alg_load_inner_resolves_current_map_copy_to_history_id():
    profile = PRODUCTS["zg_lidar_nx"]

    command = localization_alg.alg_localization_load_inner(profile, "/ota/alg_data/map/map.pcd")

    assert "DOG_REMOTE_LOC_MAP_ID" in command
    assert "history_map" in command
    assert "basename \"$DOG_REMOTE_LOC_HISTORY_DIR\"" in command
    assert "python3 -c" in command
    assert "{quote(map_id)}" not in command


def test_localization_runtime_uses_alg_without_legacy_fallback():
    profile = PRODUCTS["zg_lidar_nx"]

    spec = localization.start_localization_command(
        profile,
        "nx_zg",
        "/ota/alg_data/map",
        "/ota/calibration_results.yaml",
        "/opt/robot/robot_arc/install/apriltag_localization/config/apriltag_localization_pc_config.yaml",
        "/ota/alg_data/map/history_map/2026_06_11_22_14_49/map.pcd",
    )
    remote_command = _remote_command(spec, profile.target)

    assert "loc_load_map" in remote_command
    assert "get_loc_status" in remote_command
    assert "系统定位流程完成" in remote_command
    assert "; ;" not in remote_command
    assert "回退旧定位服务流程" not in remote_command
    assert "robot_localization 已启动" not in remote_command
    assert "/load_map_service" not in remote_command
    assert "/robot_slam/localization_state_service" not in remote_command


def test_localization_start_command_uses_alg_only_after_stable_remote_smoke():
    profile = PRODUCTS["xg2_s100"]

    spec = localization.start_localization_command(
        profile,
        "rslidar",
        "/opt/data/.robot/map",
        "/ota/calibration_results.yaml",
        "/opt/robot/robot_arc/install/apriltag_localization/config/apriltag_localization_pc_config.yaml",
        "/opt/data/.robot/map/history_map/test/map.pcd",
        record_pose=True,
    )
    remote_command = _remote_command(spec, profile.target)

    assert "loc_load_map" in remote_command
    assert "get_loc_status" in remote_command
    assert "系统定位流程完成" in remote_command
    assert "; ;" not in remote_command
    assert "LOAD_RESP_FILE=$(mktemp /tmp/dog_remote_load_map_resp" not in remote_command
    assert "ros2 service call /load_map_service" not in remote_command
    assert "/robot_slam/localization_state_service" not in remote_command
    assert "robot_slam_0_5" not in remote_command
    assert "SLAM_VERSION=$(dpkg-query" not in remote_command
    assert "Set IDLE state" not in remote_command
    assert "dog_remote_load_map_failure_state_snapshot" not in remote_command
    assert "已通过 robot_slam 定位状态服务触发加载" not in remote_command
    assert "dog_remote_load_map_response_lost_ok" not in remote_command
    assert "定位地图已加载" in remote_command
    assert "定位地图加载请求已发送，日志" not in remote_command
    assert "tail -80" not in remote_command


def test_stop_localization_command_only_cleans_tool_helpers():
    profile = PRODUCTS["zg_lidar_nx"]

    spec = localization.stop_localization_command(profile)
    remote_command = _remote_command(spec, profile.target)

    assert "清理定位辅助任务" in remote_command
    assert "dog_remote_tool_pose_xyz.pid" in remote_command
    assert "dog_remote_tool_odom_current_pose_bridge.pid" in remote_command
    assert "stop_robot_localization" not in remote_command
    assert "robot_localization 已停止" not in remote_command


def test_start_mapping_uses_alg_app_ws_and_does_not_embed_state_code_flow():
    spec = mapping.start_mapping_command(
        PRODUCTS["xg2_s100"],
        "nx_xg_rs",
        "/opt/data/.robot/map",
        "/ota/l2_new.yaml",
        "/tmp/arc.yaml",
    )

    assert "start_mapping" in spec.command
    assert "get_mapping_status" in spec.command
    assert "当前已在建图中，无需重复开始。" in spec.command
    assert "建图状态：" in spec.command
    assert "|| exit $?" in spec.command
    assert "SLAM_ACTIVE=1" not in spec.command
    assert "START_READY_STATES=" not in spec.command
    assert "{mapping_type: 0, data: 0}" not in spec.command
    assert "robots_dog_msgs/srv/MapState" not in spec.command


def test_mapping_status_uses_alg_states_only():
    profile = PRODUCTS["zg_lidar_nx"]

    assert mapping.mapping_status_from_alg_status(profile, "MappingReady") == ("ready", "已就绪")
    assert mapping.mapping_status_from_alg_status(profile, "MappingRunning") == ("mapping", "建图中")
    assert mapping.mapping_status_from_alg_status(profile, "MappingSaving") == ("saving", "保存中")
    assert mapping.mapping_status_from_alg_status(profile, "MappingSaved") == ("success", "保存完成")
    assert mapping.mapping_status_from_alg_status(profile, "MappingError") == ("error", "MappingError")
    assert mapping.mapping_status_from_alg_status(profile, "5") == ("unknown", "未知状态：5")
    assert mapping.is_mapping_alg_status(profile, "MappingRunning") is True
    assert mapping.is_mapping_active_alg_status(profile, "MappingReady") is False


def test_finish_mapping_releases_app_channel_after_save_begins_then_waits_for_saved_map():
    profile = PRODUCTS["zg_lidar_nx"]
    spec = mapping.finish_mapping_command(profile, "/ota/alg_data/map")
    remote_command = _remote_command(spec, profile.target)

    assert spec.concurrency == "parallel"
    assert spec.locks == ("mapping", "app_ws")
    assert "stop_mapping" in spec.command
    assert '"finish": 1' in spec.command
    assert "get_mapping_status" in spec.command
    assert "MappingSaved" in spec.command
    assert '"finish": SAVING | READY | SUCCESS' in spec.command
    assert "ALG_MAPPING_STATUS=" in spec.command
    assert "{mapping_type: 0, data: 110}" not in spec.command
    assert "robots_dog_msgs/srv/GetSlamState" not in spec.command
    assert "awk -v start=\"$START_TS\" '$1 >= start {print}'" in remote_command
    assert "未找到本次新落盘的 map.pgm" in remote_command
    assert "历史最新地图仍是" in remote_command


def test_cancel_mapping_uses_alg_cancel_mapping_by_default():
    spec = mapping.cancel_mapping_command(PRODUCTS["zg_lidar_nx"])

    assert spec.dangerous is True
    assert spec.concurrency == "parallel"
    assert spec.locks == ("mapping", "app_ws")
    assert "cancel_mapping" in spec.command
    assert "get_mapping_status" in spec.command
    assert "ALG_MAPPING_STATUS=" in spec.command
    assert "{mapping_type: 0, data: 0}" not in spec.command
    assert "MAPPING_STATES=100" not in spec.command
    assert "robots_dog_msgs/srv/GetSlamState" not in spec.command


def test_localization_once_quotes_preflight_paths_in_status_messages():
    profile = PRODUCTS["xg2_s100"]
    calibration_path = "/tmp/a'calib.yaml"
    map_path = "/tmp/a'map.pcd"

    spec = localization.test_localization_once_command(
        profile,
        mapping.default_sensor_type(profile),
        mapping.default_save_map_path(profile),
        calibration_path,
        mapping.default_arc_calibration_file_path(profile),
        map_path,
    )
    remote_command = _remote_command(spec, profile.target)

    assert quote(f"[ERROR] calibration file missing: {calibration_path}") in remote_command
    assert quote(f"[ERROR] map pcd missing: {map_path}") in remote_command
    assert "echo '[ERROR] calibration file missing:" not in remote_command
    assert "echo '[ERROR] map pcd missing:" not in remote_command


def test_map_preview_fetch_uses_rsync_instead_of_scp():
    profile = PRODUCTS["xg2_s100"]

    command = mapping.fetch_map_preview_files_command(
        profile,
        "/opt/data/.robot/map/history_map/a/map.pgm",
        "/tmp/preview",
    )

    assert " rsync -a " in command
    assert " scp " not in command
    assert "ConnectTimeout=20" in command
    assert "fetch_required()" in command
    assert "第 ${attempt} 次" in command
    assert "map.pgm" in command
    assert "map.yaml" in command
    assert "map.txt" in command
    assert "map.static/static_map.txt" in command
    assert "192.168.168.0/24" not in command
    assert "ProxyCommand=" in command
