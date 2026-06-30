import subprocess

from dog_remote_tool.core.profiles import get_product
from dog_remote_tool.modules import bag
from dog_remote_tool.modules.bag import remote_delete as bag_remote_delete
from dog_remote_tool.modules.bag import remote_files as bag_remote_files


def test_parse_remote_bag_status_defaults_bad_values_to_zero():
    status = bag_remote_files.parse_remote_bag_status("exists=1 active=bad meta=1 size=4096 ignored=9")

    assert status == {"exists": 1, "active": 0, "meta": 1, "size": 4096}


def test_remote_bag_status_command_quotes_path():
    command = bag_remote_files.remote_bag_status_command("/tmp/zsibot/bag/rosbag2_l2_20260525_093001")

    assert "metadata.yaml" in command
    assert "ros2 bag record" in command
    assert "ps -eww -o pid=,cmd=" in command
    assert "--output=" in command
    assert "path=/tmp/zsibot/bag/rosbag2_l2_20260525_093001" in command


def test_record_process_match_awk_accepts_ros2_output_option_variants():
    path = "/tmp/zsibot/bag/rosbag2_l2_20260525_093001"
    script = """
path=%s
printf '%%s\\n' \
  ' 101 /opt/ros/humble/bin/ros2 bag record -o /tmp/zsibot/bag/rosbag2_l2_20260525_093001 /foo' \
  ' 102 /opt/ros/humble/bin/ros2 bag record -o=/tmp/zsibot/bag/rosbag2_l2_20260525_093001 /foo' \
  ' 103 /opt/ros/humble/bin/ros2 bag record --output /tmp/zsibot/bag/rosbag2_l2_20260525_093001 /foo' \
  ' 104 /opt/ros/humble/bin/ros2 bag record --output=/tmp/zsibot/bag/rosbag2_l2_20260525_093001 /foo' \
  ' 105 /opt/ros/humble/bin/ros2 bag record -o /tmp/zsibot/bag/rosbag2_l2_20260525_093001_extra /foo' \
  ' 106 /opt/ros/humble/bin/ros2 topic echo /tmp/zsibot/bag/rosbag2_l2_20260525_093001' |
awk -v path="$path" '%s
index($0, "ros2 bag record") > 0 && has_output_path($0, path) {count++}
END {print count+0}'
""" % (subprocess.list2cmdline([path]), bag_remote_files.record_process_match_awk_functions())

    result = subprocess.run(["bash", "-lc", script], capture_output=True, text=True, timeout=5)

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "4"


def test_remote_bag_statuses_batch_paths_and_parse_output():
    command = bag_remote_files.remote_bag_statuses_command(["/tmp/a", "/tmp/b space"])

    assert "for path in /tmp/a '/tmp/b space'" in command
    assert "metadata.yaml" in command

    statuses = bag_remote_files.parse_remote_bag_statuses(
        "/tmp/a\texists=1 active=0 meta=1 size=12\n"
        "/tmp/b space\texists=1 active=1 meta=0 size=4096\n"
    )

    assert statuses == {
        "/tmp/a": {"exists": 1, "active": 0, "meta": 1, "size": 12},
        "/tmp/b space": {"exists": 1, "active": 1, "meta": 0, "size": 4096},
    }


def test_remote_bag_topic_counts_command_and_parser():
    command = bag_remote_files.remote_bag_topic_counts_command(["/tmp/a", "/tmp/b space"])

    assert "for path in /tmp/a '/tmp/b space'" in command
    assert "metadata.yaml" in command
    assert "message_count" in command

    counts, errors = bag_remote_files.parse_remote_bag_topic_counts(
        "TOPIC\t/tmp/a\t/cmd_vel\t3\n"
        "TOPIC\t/tmp/b\t/cmd_vel\t2\n"
        "TOPIC\t/tmp/b\t/odom\t0\n"
        "ERROR\t/tmp/c\t缺少 metadata.yaml\n"
    )

    assert counts == {"/cmd_vel": 5, "/odom": 0}
    assert errors == ["c: 缺少 metadata.yaml"]


def test_parse_remote_bag_scan_output_reads_disk_and_items():
    output = "\n".join(
        [
            "__DISK__\t1024\t4096\t/tmp",
            "1770000000.5\t2026-02-02 03:04\t2048\t1\t/tmp/zsibot/bag/rosbag2_l2_20260202_030400",
            "bad\t2026-02-02 03:05\tbad\t0\t/tmp/zsibot/bag/rosbag2_l2_20260202_030500",
            "__DISK_ERROR__\t/missing",
        ]
    )

    items, disk = bag_remote_files.parse_remote_bag_scan_output(output)

    assert disk == {"available": 1024, "total": 4096, "mount": "/tmp"}
    assert items == [
        {
            "epoch": 1770000000.5,
            "mtime": "2026-02-02 03:04",
            "size": 2048,
            "active": 1,
            "path": "/tmp/zsibot/bag/rosbag2_l2_20260202_030400",
            "name": "rosbag2_l2_20260202_030400",
        }
    ]


def test_remote_bag_scan_command_uses_all_dirs():
    command = bag_remote_files.remote_bag_scan_command(["/tmp/zsibot/bag", "/home/robot/bags"])

    assert "base_dir=/tmp/zsibot/bag" in command
    assert "for dir in /tmp/zsibot/bag /home/robot/bags" in command
    assert "head -100" in command


def test_remote_bag_reindex_command_selects_storage_and_quotes_path():
    command = bag_remote_files.remote_bag_reindex_command("/tmp/zsibot/bag/rosbag2_l2_20260525_093001")

    assert "ros2 bag reindex $storage_arg \"$path\"" in command
    assert "name '*.mcap'" in command
    assert "name '*.db3'" in command
    assert "path=/tmp/zsibot/bag/rosbag2_l2_20260525_093001" in command


def test_delete_remote_bag_command_quotes_and_checks_result():
    command = bag_remote_files.delete_remote_bag_command("/tmp/zsibot/bag/rosbag2_l2_20260525_093001")

    assert command == (
        "test -d /tmp/zsibot/bag/rosbag2_l2_20260525_093001 && "
        "rm -rf -- /tmp/zsibot/bag/rosbag2_l2_20260525_093001 && "
        "test ! -e /tmp/zsibot/bag/rosbag2_l2_20260525_093001"
    )


def test_delete_remote_bags_command_batches_and_parses_results():
    command = bag_remote_files.delete_remote_bags_command(
        [
            "/tmp/zsibot/bag/rosbag2_l2_20260525_093001",
            "/tmp/zsibot/bag/rosbag2_l2_20260525_093001",
            "/tmp/zsibot/bag/rosbag2_l2_20260525_093101",
        ]
    )

    assert command.count("/tmp/zsibot/bag/rosbag2_l2_20260525_093001") == 1
    assert command.count("/tmp/zsibot/bag/rosbag2_l2_20260525_093101") == 1
    assert "OK\\t%s" in command
    assert "FAIL\\t%s\\t%s" in command
    assert bag_remote_files.parse_delete_remote_bags_output("OK\t/a\nFAIL\t/b\tmissing\nnoise\n") == (
        ["/a"],
        {"/b": "missing"},
    )


def test_is_safe_remote_bag_path_accepts_only_expected_bag_directories():
    profile = get_product("xg2_s100")

    assert bag_remote_files.is_safe_remote_bag_path("/tmp/zsibot/bag/rosbag2_l2_20260525_093001")
    assert bag_remote_files.is_safe_remote_bag_path("/opt/data/l2_20260525_093001", profile)
    assert bag_remote_files.is_safe_remote_bag_path("/home/robot/bags/zg_20260525_093001", profile)
    assert bag_remote_files.is_safe_remote_bag_path("/home/robot/bags/air_20260525_093001", profile)
    assert not bag_remote_files.is_safe_remote_bag_path("/home/robot/bags/not_a_bag", profile)
    assert not bag_remote_files.is_safe_remote_bag_path("/home/robot")
    assert not bag_remote_files.is_safe_remote_bag_path("relative/rosbag2_l2_20260525_093001", profile)


def test_bag_backend_safe_path_wrapper_uses_remote_file_helper():
    profile = get_product("xg2_s100")

    assert bag.BagBackend.is_safe_remote_bag_path("/opt/data/l2_20260525_093001", profile)


def test_bag_backend_delete_remote_bags_batches_safe_paths(monkeypatch):
    profile = get_product("xg2_s100")
    messages = []
    calls = []
    first = "/opt/data/l2_20260525_093001"
    second = "/opt/data/l2_20260525_093101"

    def fake_run(cmd, stdout=None, stderr=None, text=None, timeout=None):
        calls.append(cmd)
        return subprocess.CompletedProcess(cmd, 1, stdout=f"OK\t{first}\nFAIL\t{second}\tmissing\n", stderr="")

    monkeypatch.setattr(bag_remote_delete.subprocess, "run", fake_run)
    backend = bag.BagBackend(profile, log=messages.append)

    deleted, failed = backend.delete_remote_bags([first, "/home/robot", second], auto_delete=True)

    assert len(calls) == 1
    assert first in calls[0][-1]
    assert second in calls[0][-1]
    assert deleted == [first]
    assert failed == ["/home/robot", second]
    assert any("拒绝删除非录包安全路径" in message for message in messages)
    assert any("远端Bag已删除" in message and first in message for message in messages)
    assert any("远端Bag删除失败" in message and second in message for message in messages)
