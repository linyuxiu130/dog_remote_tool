import subprocess
from dataclasses import replace
from datetime import datetime

from dog_remote_tool.core.paths import resource_dir
from dog_remote_tool.core.profiles import get_product
from dog_remote_tool.modules import bag
from dog_remote_tool.modules.bag import backend as bag_backend
from dog_remote_tool.modules.bag import backend_transfer as bag_backend_transfer
from dog_remote_tool.modules.bag import local as bag_local
from dog_remote_tool.modules.bag import metadata as bag_metadata
from dog_remote_tool.modules.bag import remote_files as bag_remote_files
from dog_remote_tool.modules.bag import topic_storage as bag_topic_storage
from dog_remote_tool.modules.bag import topics as bag_topics


def test_safe_filename_component_normalizes_invalid_chars():
    assert bag.safe_filename_component("  a/b  c中文  ") == "a_b_c"
    assert bag.safe_filename_component("///", "fallback") == "fallback"


def test_standard_names_use_profile_prefix_and_timestamp():
    profile = get_product("xg2_s100")
    stamp = datetime(2026, 5, 25, 9, 30, 1)

    assert bag.standard_remote_bag_name("nxl2", profile, stamp) == "rosbag2_l2_20260525_093001"
    assert bag.standard_dataset_name("nxl2", profile, stamp) == "L2_20260525_093001"


def test_medium_dog_standard_names_use_zg_prefix():
    stamp = datetime(2026, 6, 17, 14, 30, 1)

    assert bag.standard_remote_bag_name("zg", get_product("zg3588"), stamp) == "rosbag2_zg_20260617_143001"
    assert bag.standard_dataset_name("zg", get_product("zg3588"), stamp) == "ZG_20260617_143001"
    assert bag.standard_remote_bag_name("zgnx", get_product("zg_surround_s100"), stamp) == "rosbag2_zg_20260617_143001"
    assert bag.standard_dataset_name("zgnx", get_product("zg_lidar_nx"), stamp) == "ZG_20260617_143001"


def test_dataset_name_from_remote_bags_handles_rosbag_names():
    assert bag.dataset_name_from_remote_bags(["/tmp/rosbag2_l2_20260525_093001"]) == "L2_20260525_093001"
    assert bag.dataset_name_from_remote_bags(["/tmp/a", "/tmp/b"]) == "multi_a_b"


def test_recording_storage_for_profile_uses_profile_override():
    assert bag.recording_storage_for_profile(get_product("xg3588")) == "sqlite3"
    assert bag.recording_storage_for_profile(get_product("xg2_s100")) == "sqlite3"


def test_record_plan_repairs_remote_save_directory_permissions():
    profile = get_product("xg2_s100")
    plan = bag_backend.BagBackend(profile, product="nxl2").build_record_plan(
        "/opt/data",
        "sqlite3",
        1,
        bag.TopicPlan(normal_topics=["/robot/sensor"], zstd_topics=[], all_topics=["/robot/sensor"]),
    )

    assert "sudo_run mkdir -p -- /opt/data" in plan.command
    assert 'sudo_run chown "$(id -u):$(id -g)" -- /opt/data' in plan.command
    assert "[ -w /opt/data ]" in plan.command
    assert "[ERROR] Bag保存目录不可写: /opt/data" in plan.command
    assert "ros2 bag record -o /opt/data/rosbag2_l2_" in plan.command


def test_bag_backend_ssh_options_use_connection_reuse(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path))
    backend = bag.BagBackend(get_product("xg2_s100"))

    options = backend.ssh_options(connect_timeout=30)
    joined = " ".join(options)

    assert "ConnectTimeout=30" in options
    assert "ServerAliveInterval=15" in options
    assert "ServerAliveCountMax=8" in options
    assert "ControlMaster=auto" not in options
    assert "ControlPersist=10m" not in options
    assert not any(item.startswith("ControlPath=") for item in options)
    assert "ProxyCommand=" in joined
    assert "sshpass -p" not in joined


def test_bag_backend_rsync_quotes_profile_ssh_options(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path))
    backend = bag.BagBackend(get_product("xg2_s100"))

    command = backend.build_rsync_command("/tmp/a", "/tmp/b")
    ssh_command = command[command.index("-e") + 1]

    assert "ProxyCommand=" in ssh_command
    assert "'ProxyCommand=" in ssh_command
    assert "ControlMaster=auto" not in ssh_command


def test_bag_backend_ssh_command_does_not_log_metric_to_user_log(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path))
    calls = []

    def fake_run(cmd, **kwargs):
        calls.append((cmd, kwargs))
        return subprocess.CompletedProcess(cmd, 0, stdout="ok", stderr="")

    monkeypatch.setattr(bag_backend.subprocess, "run", fake_run)
    logs = []
    profile = replace(get_product("xg2_s100"), password="secret-password")
    backend = bag.BagBackend(profile, log=logs.append)

    result = backend.ssh_bash_command("echo secret", timeout=7)

    assert result.stdout == "ok"
    assert logs == []
    assert calls[0][1]["timeout"] == 7
    assert calls[0][1]["input"] == "secret-password\n"


def test_resolve_remote_log_paths_batches_candidate_probe():
    class FakeBackend(bag.BagBackend):
        def __init__(self):
            super().__init__(get_product("xg2_s100"), product="nx")
            self.commands = []

        def ssh_bash_command(self, remote_cmd: str, timeout: int = 15, *, login_shell: bool = True):
            self.commands.append(remote_cmd)
            return subprocess.CompletedProcess([], 0, stdout="/tmp/log/alg_data\n/home/robot/.ros/log\n", stderr="")

    backend = FakeBackend()

    assert backend.resolve_remote_log_paths() == ["/tmp/log/alg_data", "/home/robot/.ros/log"]
    assert len(backend.commands) == 1


def test_format_size():
    assert bag.format_size(512) == "512 B"
    assert bag.format_size(1536) == "1.5 KB"


def test_remote_bags_size_helpers_batch_paths():
    command = bag_remote_files.remote_bags_size_command(["/tmp/a", "/tmp/b space"])

    assert "/tmp/dog_remote_bag_helper.py sizes" in command
    assert "/tmp/a" in command
    assert "/tmp/b space" in command
    assert "find " not in command
    assert bag_remote_files.parse_remote_bags_size("noise\n4096\n") == 4096
    assert bag_remote_files.parse_remote_bags_size("missing") == 0


def test_topic_helpers_remain_available_from_bag_module():
    assert bag.TopicPlan is bag_topics.TopicPlan
    assert bag.custom_preset_key("巡检") == "custom_preset::巡检"
    assert bag.custom_preset_name_from_key("custom_preset::巡检") == "巡检"

    plan = bag.selected_topic_plan(
        {
            "nav": {"topics": ["/cmd_vel", "odom"], "zstd_topics": ["/cmd_vel"]},
            "loc": {"topics": ["/scan"]},
        },
        ["nav", "loc"],
    )

    assert plan.normal_topics == ["/cmd_vel", "/odom", "/scan"]
    assert plan.zstd_topics == []
    assert plan.all_topics == ["/cmd_vel", "/odom", "/scan"]


def test_bag_topic_resources_dir_reuses_core_resource_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("DOG_REMOTE_TOOL_ROOT", str(tmp_path))

    assert bag.resources_dir() == resource_dir("record_bag")
    assert bag.resources_dir(tmp_path / "app") == tmp_path / "app" / "resources" / "record_bag"


def test_custom_presets_load_legacy_and_current_yaml_shapes(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    config_path = bag.config_dir() / "custom_topic_presets.yaml"
    config_path.parent.mkdir(parents=True)

    config_path.write_text("presets:\n  nav:\n    - cmd_vel\n    - /cmd_vel\n    - 123\n", encoding="utf-8")
    assert bag.load_custom_presets() == {"nav": ["/cmd_vel"]}

    config_path.write_text("nav:\n  - odom\n", encoding="utf-8")
    assert bag.load_custom_presets() == {"nav": ["/odom"]}


def test_add_topic_suggestions_enriches_failed_topics():
    result = bag.add_topic_suggestions(
        ["/rs_rgb_img/compressed: 无发布者"],
        [{"topic": "/rs_rgb_img/compressedDepth"}, {"topic": "/front_lidar"}],
    )

    assert len(result) == 1
    assert "可能是:" in result[0]
    assert "/rs_rgb_img/compressedDepth" in result[0]


def test_bag_local_metadata_helpers(tmp_path):
    bag_dir = tmp_path / "rosbag2_l2_20260525_093001"
    bag_dir.mkdir()
    (bag_dir / "data_0.mcap").write_bytes(b"data")
    (bag_dir / "metadata.yaml").write_text(
        """
rosbag2_bagfile_information:
  duration:
    nanoseconds: 2500000000
  starting_time:
    nanoseconds_since_epoch: 1767225600000000000
  relative_file_paths:
    - data_0.mcap
  topics_with_message_count:
    - topic_metadata:
        name: /cmd_vel
      message_count: 3
""",
        encoding="utf-8",
    )

    assert bag.load_bag_metadata(str(bag_dir))[1] == []
    assert bag_local.local_bag_paths(str(tmp_path)) == [str(bag_dir)]
    assert bag_local.directory_size(str(bag_dir)) > 0
    assert bag_local.metadata_duration_seconds(str(tmp_path)) == 2.5
    assert bag_local.metadata_topics(str(tmp_path)) == ["/cmd_vel"]
    assert bag_local.format_duration(3661) == "01:01:01"


def test_bag_local_validate_pulled_recording(tmp_path):
    bag_dir = tmp_path / "rosbag2_l2_20260525_093001"
    bag_dir.mkdir()
    (bag_dir / "data_0.mcap").write_bytes(b"data")
    (bag_dir / "metadata.yaml").write_text(
        """
rosbag2_bagfile_information:
  relative_file_paths:
    - data_0.mcap
  topics_with_message_count:
    - topic_metadata:
        name: /cmd_vel
      message_count: 2
""",
        encoding="utf-8",
    )
    (tmp_path / "log").mkdir()
    topic_units = [{"label": "/cmd_vel", "topics": ["/cmd_vel"], "is_group": False}]

    result = bag_local.validate_pulled_recording(str(tmp_path), True, True, ["/cmd_vel"], topic_units)

    assert result["ok"] is True
    assert "正常，1/1 个Bag目录完整" in result["summary"]
    assert "log 目录已拉取" in result["details"]


def test_bag_local_validate_topic_counts_reports_missing_and_empty_topics():
    units = [
        {"label": "/cmd_vel", "topics": ["/cmd_vel"], "is_group": False},
        {"label": "/odom", "topics": ["/odom"], "is_group": False},
        {"label": "/scan", "topics": ["/scan"], "is_group": False},
    ]

    result = bag_local.validate_topic_counts({"/cmd_vel": 3, "/odom": 0}, ["/cmd_vel", "/odom", "/scan"], units)

    assert result["ok"] is False
    assert result["summary"] == "话题部分异常，1/3 个目标Topic有数据"
    assert "空数据Topic: /odom" in result["details"]
    assert "缺失Topic: /scan" in result["details"]
