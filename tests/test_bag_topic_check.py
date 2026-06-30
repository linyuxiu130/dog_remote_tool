import subprocess

from dog_remote_tool.core.profiles import get_product
from dog_remote_tool.modules import bag
from dog_remote_tool.modules.bag import topic_check as bag_topic_check
from dog_remote_tool.modules.bag import topic_probe as bag_topic_probe


def test_topic_check_units_groups_alternative_camera_topics():
    units = bag_topic_check.topic_check_units(["/cmd_vel", "/rs_rgb_img/compressed", "/rs_ir_left/compressed"])

    assert units == [
        {"label": "/cmd_vel", "topics": ["/cmd_vel"], "is_group": False},
        {
            "label": "/rs_rgb_img/compressed / /rs_ir_left/compressed",
            "topics": ["/rs_rgb_img/compressed", "/rs_ir_left/compressed"],
            "is_group": True,
        },
    ]


def test_build_topic_check_command_quotes_topic_and_includes_hz_probe():
    command = bag_topic_check.build_topic_check_command(
        ["source /opt/ros/humble/setup.bash"],
        "/front lidar",
        {"min_hz": 8.0, "max_hz": 12.0},
    )

    assert "source /opt/ros/humble/setup.bash" in command
    assert "ros2 topic info '/front lidar' --no-daemon -v" in command
    assert "ros2 topic echo '/front lidar' --once --no-daemon" in command
    assert "ros2 topic hz '/front lidar' --window 20" in command


def test_topic_echo_has_message_ignores_warning_only_output():
    assert bag_topic_check.topic_echo_has_message("WARNING: once\n") is False
    assert bag_topic_check.topic_echo_has_message("data: 1\n") is True
    assert bag_topic_check.topic_echo_has_message("---\nheader:\n") is True


def test_parse_topic_check_result_handles_missing_topic_and_frequency():
    missing = subprocess.CompletedProcess([], 1, stdout="", stderr="Unknown topic")
    assert bag_topic_check.parse_topic_check_result("/missing", missing, None) == (
        False,
        "/missing: 不存在",
        "/missing -> Unknown topic",
    )

    ok = subprocess.CompletedProcess(
        [],
        0,
        stdout="Publisher count: 1\n---\ndata: 1\n",
        stderr="average rate: 9.8\n",
    )
    assert bag_topic_check.parse_topic_check_result("/front_lidar", ok, {"min_hz": 8.0, "max_hz": 12.0}) == (
        True,
        "/front_lidar: 正常(9.8Hz)",
        "/front_lidar -> 正常, hz=9.80",
    )

    bad_hz = subprocess.CompletedProcess(
        [],
        0,
        stdout="Publisher count: 1\n---\ndata: 1\n",
        stderr="average rate: 2.0\n",
    )
    assert bag_topic_check.parse_topic_check_result("/front_lidar", bad_hz, {"min_hz": 8.0, "max_hz": 12.0})[1] == "/front_lidar: 频率异常"


def test_bag_backend_topic_helpers_delegate_to_split_module():
    backend = bag.BagBackend(get_product("xg2_s100"))

    assert backend.topic_check_units(["/rs_rgb_img/compressed", "/rs_ir_left/compressed"]) == bag_topic_check.topic_check_units(
        ["/rs_rgb_img/compressed", "/rs_ir_left/compressed"]
    )
    assert backend._topic_probe_env_lines() == bag_topic_probe.topic_probe_env_lines(backend.profile, backend.ros_env_lines())
    assert bag_topic_probe.check_topics([], backend.ros_env_lines(), backend.ssh_bash_command, backend.log) == ([], [])
    assert bag.TOPIC_CHECK_PROFILES is bag_topic_check.TOPIC_CHECK_PROFILES
