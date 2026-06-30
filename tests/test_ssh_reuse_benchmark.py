from __future__ import annotations

import importlib.util
import subprocess
from pathlib import Path

from dog_remote_tool.core.profiles import get_product


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "ssh_reuse_benchmark.py"
SPEC = importlib.util.spec_from_file_location("ssh_reuse_benchmark", SCRIPT)
ssh_reuse_benchmark = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(ssh_reuse_benchmark)


def test_connection_command_reflects_ssh_control_env(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path))
    profile = get_product("xg2_3588")

    previous = ssh_reuse_benchmark.set_ssh_control(False)
    try:
        disabled = ssh_reuse_benchmark.build_shell_command(profile, "connection", "/tmp/map.pcd")
    finally:
        ssh_reuse_benchmark.restore_ssh_control(previous)

    previous = ssh_reuse_benchmark.set_ssh_control(True)
    try:
        enabled = ssh_reuse_benchmark.build_shell_command(profile, "connection", "/tmp/map.pcd")
    finally:
        ssh_reuse_benchmark.restore_ssh_control(previous)

    assert "ControlMaster=auto" not in disabled
    assert "ControlMaster=auto" in enabled
    assert "ProxyCommand=" not in enabled


def test_jump_connection_command_disables_control_reuse_by_default(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path))
    profile = get_product("xg2_s100")

    previous = ssh_reuse_benchmark.set_ssh_control(True)
    try:
        command = ssh_reuse_benchmark.build_shell_command(profile, "connection", "/tmp/map.pcd")
    finally:
        ssh_reuse_benchmark.restore_ssh_control(previous)

    assert "ProxyCommand=" in command
    assert "ControlMaster=auto" not in command


def test_navigation_status_command_uses_existing_probe(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path))
    profile = get_product("xg2_s100")

    command = ssh_reuse_benchmark.build_shell_command(profile, "navigation-status", "/ota/alg_data/map/map.pcd")

    assert "MAP_PCD=/ota/alg_data/map/map.pcd" in command
    assert "ros2" in command
    assert "ControlMaster=auto" not in command
    assert "ros2 topic echo --once \"$topic\" --no-daemon" in command
    assert "dog_remote_nav_graph_probe" not in command
    assert "NAVIGATION_CMD_PUBLISHERS" not in command
    assert "LASER_SCAN_STAMP_AGE_MS" not in command


def test_device_status_command_uses_dashboard_probe(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path))
    profile = get_product("xg2_s100")

    command = ssh_reuse_benchmark.build_shell_command(profile, "device-status", "/tmp/map.pcd")

    assert "DOG_REMOTE_STATUS_BEGIN" in command
    assert "robot-launch list" in command
    assert "ControlMaster=auto" not in command


def test_pose_stream_command_uses_existing_localization_stream(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path))
    profile = get_product("xg2_s100")

    command = ssh_reuse_benchmark.build_shell_command(profile, "pose-stream", "/tmp/map.pcd")

    assert "dog_remote_tool_pose_stream" in command
    assert "/odom/current_pose" in command
    assert "ControlMaster=auto" not in command


def test_run_stream_until_output_returns_after_first_line():
    assert ssh_reuse_benchmark.run_stream_until_output("printf 'ready\\n'; sleep 5", timeout=2) == 0


def test_bag_topic_probe_reuses_existing_topic_check(monkeypatch):
    commands = []

    class FakeBackend:
        def __init__(self, _profile):
            pass

        def _topic_probe_env_lines(self):
            return ["source /opt/ros/humble/setup.bash"]

        def ssh_bash_command(self, command, timeout=15):
            commands.append((command, timeout))
            return subprocess.CompletedProcess([], 0, stdout="Publisher count: 1\n---\ndata: 1\n", stderr="")

    monkeypatch.setattr(ssh_reuse_benchmark.bag, "BagBackend", FakeBackend)

    assert ssh_reuse_benchmark.run_bag_topic_probe(get_product("xg2_s100"), ["/odom/current_pose"], timeout=9) == 0
    assert "ros2 topic info /odom/current_pose --no-daemon -v" in commands[0][0]
    assert "ros2 topic echo /odom/current_pose --once --no-daemon" in commands[0][0]
    assert commands[0][1] == 9


def test_summarize_reports_average_median_and_best():
    assert ssh_reuse_benchmark.summarize([30, 10, 20]) == (20, 20, 10)


def test_comparison_summary_reports_saved_time():
    summary = ssh_reuse_benchmark.comparison_summary((1000.0, 900.0, 800), (600.0, 500.0, 450), (2, 3), (3, 3))

    assert summary == "avg_delta=400.0;p50_delta=400.0;best_delta=350;avg_saved_pct=40.0;off_ok=2/3;on_ok=3/3"


def test_run_benchmark_prints_compare_rows(monkeypatch, capsys):
    values = iter([(1000, 0), (800, 1), (500, 0), (400, 0)])
    monkeypatch.setattr(ssh_reuse_benchmark, "measure_once", lambda *_args: next(values))

    exit_code = ssh_reuse_benchmark.run_benchmark(
        get_product("xg2_s100"),
        ["connection"],
        "/tmp/map.pcd",
        repeats=2,
        timeout=3,
        topics=["/odom/current_pose"],
    )

    output = capsys.readouterr().out
    assert exit_code == 1
    assert "connection,off,summary,avg=900.0;p50=900.0;best=800;ok=1/2,-" in output
    assert "connection,on,summary,avg=450.0;p50=450.0;best=400;ok=2/2,-" in output
    assert "connection,compare,summary,avg_delta=450.0;p50_delta=450.0;best_delta=400;avg_saved_pct=50.0;off_ok=1/2;on_ok=2/2,-" in output
