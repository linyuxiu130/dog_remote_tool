import os
import subprocess

import pytest

from dog_remote_tool.core.profiles import get_product
from dog_remote_tool.modules import bag
from dog_remote_tool.modules.bag import calibration as bag_calibration
from dog_remote_tool.modules.bag import finalize as bag_finalize
from dog_remote_tool.modules.bag import logs as bag_logs
from dog_remote_tool.modules.bag import recording_control as bag_recording_control
from dog_remote_tool.modules.bag import recording_remote as bag_recording_remote
from dog_remote_tool.modules.bag import transfer as bag_transfer


def test_transfer_state_marker_toggles_complete_and_incomplete(tmp_path):
    bag_transfer.write_transfer_state_marker(str(tmp_path), complete=False)
    assert (tmp_path / bag_transfer.TRANSFER_INCOMPLETE_MARKER).exists()
    assert not bag_transfer.is_transfer_complete_directory(str(tmp_path))

    bag_transfer.write_transfer_state_marker(str(tmp_path), complete=True)
    assert (tmp_path / bag_transfer.TRANSFER_COMPLETE_MARKER).exists()
    assert not (tmp_path / bag_transfer.TRANSFER_INCOMPLETE_MARKER).exists()
    assert bag_transfer.is_transfer_complete_directory(str(tmp_path))


def test_unique_directory_path_uses_numbered_suffix(tmp_path):
    base = tmp_path / "dataset"
    base.mkdir()
    (tmp_path / "dataset_02").mkdir()

    assert bag_transfer.unique_directory_path(str(base)) == str(tmp_path / "dataset_03")


def test_find_reusable_transfer_directory_prefers_larger_unfinished_candidate(tmp_path):
    remote_path = "/tmp/rosbag2_l2_20260525_093001"
    small = tmp_path / "small" / "L2_20260525_093001"
    large = tmp_path / "large" / "L2_20260525_093001"
    complete = tmp_path / "complete" / "L2_20260525_093001"
    small.mkdir(parents=True)
    large.mkdir(parents=True)
    complete.mkdir(parents=True)
    (small / "data.mcap").write_bytes(b"1")
    (large / "data.mcap").write_bytes(b"12345")
    bag_transfer.write_transfer_state_marker(str(complete.parent), complete=True)

    assert bag_transfer.find_reusable_transfer_directory(str(tmp_path), [remote_path]) == str(large.parent)


def test_transfer_target_directory_reports_reuse_message(tmp_path):
    remote_path = "/tmp/rosbag2_l2_20260525_093001"
    existing_bag = tmp_path / "L2_20260525_093001" / "L2_20260525_093001"
    existing_bag.mkdir(parents=True)

    target, message = bag_transfer.transfer_target_directory(str(tmp_path), "L2_20260525_093001", [remote_path], True)

    assert target == str(existing_bag.parent)
    assert "复用已有未完成目录" in message


def test_transfer_target_directory_avoids_existing_file(tmp_path):
    remote_path = "/tmp/rosbag2_l2_20260525_093001"
    (tmp_path / "L2_20260525_093001").write_text("not a directory", encoding="utf-8")

    target, message = bag_transfer.transfer_target_directory(str(tmp_path), "L2_20260525_093001", [remote_path], True)

    assert target == str(tmp_path / "L2_20260525_093001_02")
    assert message == ""


def test_transfer_locks_block_same_remote_until_released(tmp_path):
    handles = bag_transfer.acquire_transfer_locks(str(tmp_path), ["/tmp/rosbag2_l2_20260525_093001"])
    try:
        with pytest.raises(RuntimeError):
            bag_transfer.acquire_transfer_locks(str(tmp_path), ["/tmp/rosbag2_l2_20260525_093001"])
    finally:
        bag_transfer.release_transfer_locks(handles)

    second = bag_transfer.acquire_transfer_locks(str(tmp_path), ["/tmp/rosbag2_l2_20260525_093001"])
    bag_transfer.release_transfer_locks(second)


def test_bag_backend_transfer_methods_delegate_to_transfer_helpers(tmp_path):
    backend = bag.BagBackend(get_product("xg2_s100"))
    target = backend.transfer_target_directory(str(tmp_path), "dataset", [], include_bag=False)

    assert os.path.basename(target) == "dataset"
    backend.write_transfer_state_marker(target, True)
    assert backend.is_transfer_complete_directory(target)


def test_recording_control_start_and_stop_use_injected_ssh_runner():
    calls = []
    messages = []

    def ssh_bash_command(remote_cmd, timeout=15, *, login_shell=True):
        calls.append((remote_cmd, timeout, login_shell))
        if len(calls) == 1:
            return subprocess.CompletedProcess([], 0, stdout="__DOG_REMOTE_RECORD_STARTED__ pid=12 log=/tmp/record.log\n", stderr="")
        return subprocess.CompletedProcess([], 0, stdout="remote ros2 bag record stopped after SIGINT\n", stderr="")

    ok, error = bag_recording_control.start_remote_recording(
        ["/tmp/zsibot/bag/rosbag2_l2_20260525_093001"],
        "ros2 bag record -o /tmp/zsibot/bag/rosbag2_l2_20260525_093001 /foo",
        ssh_bash_command,
        messages.append,
    )

    assert (ok, error) == (True, "")
    assert bag_recording_control.stop_remote_recording(
        ["/tmp/zsibot/bag/rosbag2_l2_20260525_093001"],
        ssh_bash_command,
        messages.append,
    )
    assert [call[1:] for call in calls] == [(20, False), (220, False)]
    assert any("远端后台录制已启动" in message for message in messages)
    assert any("远端停止" in message for message in messages)


def test_recording_remote_wrapper_matches_output_option_variants():
    path = "/tmp/zsibot/bag/rosbag2_l2_20260525_093001"

    start_command = bag_recording_remote.start_recording_wrapper_command("ros2 bag record --output=/tmp/a /foo", [path])
    stop_command = bag_recording_remote.stop_recording_command([path])

    for command in (start_command, stop_command):
        assert "ps -eww -o pid=,cmd=" in command
        assert "--output=" in command
        assert "--output " in command
        assert "-o=" in command
        assert 'index($0, "DOG_REMOTE_RECORD_SCRIPT") > 0 { next }' in command


def test_pull_multiple_bags_uses_batch_finalize_fast_path(tmp_path):
    paths = [
        "/tmp/zsibot/bag/rosbag2_l2_20260525_093001",
        "/tmp/zsibot/bag/rosbag2_l2_20260525_093101",
    ]

    class FakeBackend(bag.BagBackend):
        def __init__(self):
            super().__init__(get_product("xg2_s100"))
            self.batch_waits = []
            self.single_waits = []

        def wait_remote_bags_finalized_paths(self, remote_bag_paths, timeout=180):
            self.batch_waits.append((remote_bag_paths[:], timeout))
            return set(remote_bag_paths)

        def wait_remote_bags_finalized(self, remote_bag_paths, timeout=180):
            self.single_waits.append((remote_bag_paths[:], timeout))
            return True

        def build_rsync_command(self, remote_path, local_path, rsync_args=None, excludes=None):
            return ["true"]

        def run_rsync_with_progress(self, cmd, label, idle_timeout, progress=None, progress_prefix=""):
            return True

        def validate_pulled_recording(self, target_dir, bag_success, log_success, expected_topics):
            return {"ok": True, "summary": "ok", "details": []}

        def write_record_summary(self, **kwargs):
            return ""

    backend = FakeBackend()

    result = backend.pull_bag_and_log(paths, str(tmp_path), [], include_bag=True, include_log=False)

    assert result["bag_success"] is True
    assert result["calibration_attempted"] is True
    assert result["calibration_success"] is True
    assert backend.batch_waits == [(paths, 180)]
    assert backend.single_waits == []


def test_finalize_batch_wait_deduplicates_remote_paths():
    calls = []
    remote_path = "/tmp/zsibot/bag/rosbag2_l2_20260525_093001"

    def statuses(paths):
        calls.append(paths[:])
        return {remote_path: {"exists": 1, "active": 0, "meta": 1, "size": 1024}}

    ready = bag_finalize.wait_remote_bags_finalized_paths(
        [remote_path, remote_path],
        statuses,
        lambda _path: {},
        lambda _path: False,
        lambda _message: None,
        timeout=1,
        sleep_interval=0,
    )

    assert ready == {remote_path}
    assert calls == [[remote_path], [remote_path]]


def test_pull_log_failure_does_not_probe_remote_logs_twice(tmp_path):
    class FakeBackend(bag.BagBackend):
        def __init__(self):
            self.messages = []
            super().__init__(get_product("xg2_s100"), product="nx", log=self.messages.append)
            self.resolve_calls = 0

        def resolve_remote_log_paths(self, log_kind="all"):
            self.resolve_calls += 1
            return []

        def resolve_remote_log_path(self):
            raise AssertionError("fallback log path should not trigger another remote probe")

        def write_record_summary(self, **kwargs):
            return ""

    backend = FakeBackend()

    result = backend.pull_bag_and_log([], str(tmp_path), [], include_bag=False, include_log=True)

    assert result["log_success"] is False
    assert backend.resolve_calls == 1
    assert any("/tmp/log/alg_data" in message for message in backend.messages)


def test_log_candidates_split_runtime_and_ros_paths():
    assert bag_logs.candidate_log_paths("zgnx", "runtime") == ["/tmp/log/alg_data", "/tmp/zsibot/log"]
    assert bag_logs.candidate_log_paths("zgnx", "ros") == ["/home/robot/.ros/log"]
    assert bag_logs.candidate_log_paths("zg", "runtime") == ["/tmp/zsibot/log"]
    assert bag_logs.candidate_log_paths("zg", "ros") == ["/home/robot/.ros/log"]


def test_download_calibration_files_reports_success(tmp_path, monkeypatch):
    commands = []

    class FakeBackend(bag.BagBackend):
        def __init__(self):
            super().__init__(get_product("xg2_s100"), product="nxl2")

        def build_rsync_command(self, remote_path, local_path, rsync_args=None, excludes=None):
            commands.append((remote_path, local_path))
            return ["rsync", remote_path, local_path]

    def fake_run(cmd, stdout=None, stderr=None, text=None, timeout=None):
        return subprocess.CompletedProcess(cmd, 0, stdout="ok", stderr="")

    monkeypatch.setattr(bag_calibration.subprocess, "run", fake_run)

    assert FakeBackend().download_calibration_files(str(tmp_path)) is True
    assert commands == [
        ("/ota/calibration_results.yaml", str(tmp_path) + os.sep),
        ("/ota/l2_new.yaml", str(tmp_path) + os.sep),
    ]
    assert bag.REMOTE_CALIBRATION_FILES is bag_calibration.REMOTE_CALIBRATION_FILES


def test_download_calibration_files_does_not_probe_l2_file_for_zgnx(tmp_path, monkeypatch):
    commands = []

    class FakeBackend(bag.BagBackend):
        def __init__(self):
            super().__init__(get_product("zg_lidar_nx"), product="zgnx")

        def build_rsync_command(self, remote_path, local_path, rsync_args=None, excludes=None):
            commands.append((remote_path, local_path))
            return ["rsync", remote_path, local_path]

    def fake_run(cmd, stdout=None, stderr=None, text=None, timeout=None):
        return subprocess.CompletedProcess(cmd, 0, stdout="ok", stderr="")

    monkeypatch.setattr(bag_calibration.subprocess, "run", fake_run)

    assert FakeBackend().download_calibration_files(str(tmp_path)) is True
    assert commands == [("/ota/calibration_results.yaml", str(tmp_path) + os.sep)]
