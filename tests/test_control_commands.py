import os
import sys

from dog_remote_tool.core.parsers import parse_key_values
from dog_remote_tool.core.profiles import get_product
from dog_remote_tool.modules import control
from dog_remote_tool.modules.control import video as control_video
from dog_remote_tool.modules.control import l1 as control_l1
from dog_remote_tool.modules.control import l1_actions as control_l1_actions
from dog_remote_tool.modules.control import l1_setup as control_l1_setup
from dog_remote_tool.modules.control import mc_mode as control_mc_mode
from dog_remote_tool.modules.control import shared as control_shared
from dog_remote_tool.modules.control import speed_l2 as control_speed_l2
from dog_remote_tool.modules.control.robot_remote import actions as robot_remote_actions
from dog_remote_tool.modules.control.robot_remote import client as robot_remote_client
from dog_remote_tool.modules.control.robot_remote import codec as robot_remote_codec
from dog_remote_tool.modules.control.robot_remote import commands as robot_remote_commands
from dog_remote_tool.modules.control.robot_remote import protocol as robot_remote_protocol
from dog_remote_tool.modules.control.robot_remote import stream as robot_remote_stream
from dog_remote_tool.ui.pages.control import helpers as control_helpers


def test_control_key_value_parser_reuses_core_key_values():
    assert control_helpers.parse_key_value_lines is parse_key_values


def test_control_profile_mapping_keeps_l2_pairing():
    assert control.l2_control_profile(get_product("xg2_s100")).key == "xg2_3588"
    assert control.l2_control_profile(get_product("xg2_3588")).key == "xg2_3588"
    assert control.l2_control_profile(get_product("xg3588")) is None


def test_control_stdin_ssh_uses_route_repair_for_wired_targets(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path))

    command = control_shared.ssh_bash_stdin_command(get_product("xg2_3588"), "echo ok")

    assert command.index("192.168.234.0/24") < command.index("sshpass -f")
    assert "DOG_REMOTE_L2_NAV_SCRIPT" in command


def test_robot_sdk_control_profile_maps_medium_dog_body_controller():
    assert control.robot_sdk_control_profile(get_product("zg3588")).key == "zg3588"
    assert control.robot_sdk_control_profile(get_product("zg_surround_3588")).key == "zg_surround_3588"
    assert control.robot_sdk_control_profile(get_product("zg_surround_s100")).key == "zg3588"
    assert control.robot_sdk_control_profile(get_product("zg_lidar_nx")).key == "zg3588"
    assert control.robot_sdk_control_profile(get_product("xg2_s100")) is None


def test_robot_remote_control_profile_maps_l2_and_medium_dog_body_controller():
    assert control.robot_remote_control_profile(get_product("xg2_s100")).key == "xg2_3588"
    assert control.robot_remote_control_profile(get_product("xg2_3588")).key == "xg2_3588"
    assert control.robot_remote_control_profile(get_product("zg3588")).key == "zg3588"
    assert control.robot_remote_control_profile(get_product("zg_surround_s100")).key == "zg3588"
    assert control.robot_remote_control_profile(get_product("xg3588")) is None


def test_robot_remote_codec_round_trips_zskj_packets():
    payload = {"head": {"type": 1000, "src": 1}, "data": {"model": "xg"}}

    packet = robot_remote_codec.build_packet(payload, frame_id=7)

    assert packet.startswith(b"ZSKJ")
    assert robot_remote_codec.decode_packet(packet) == payload
    try:
        robot_remote_codec.decode_packet(b"bad")
    except ValueError as exc:
        assert "非 ZSKJ" in str(exc)
    else:
        raise AssertionError("invalid packet should fail")


def test_robot_remote_stream_values_convert_ui_axis_signs():
    values = robot_remote_protocol._stream_values(
        {"forward": -60, "strafe": -20, "turn": -30, "pitch": -10},
        axis_limit=50,
    )

    assert values == (0.2, 0.5, 0.3, 0.1)


def test_robot_remote_stream_values_keep_forward_and_strafe_separate():
    assert robot_remote_protocol._stream_values({"forward": -60}, axis_limit=100) == (-0.0, 0.6, -0.0, -0.0)
    assert robot_remote_protocol._stream_values({"strafe": -60}, axis_limit=100) == (0.6, -0.0, -0.0, -0.0)


def test_robot_remote_stream_values_support_velocity_payloads():
    values = robot_remote_protocol._stream_values(
        {
            "forward": -0.6,
            "strafe": -0.6,
            "turn": -1.0,
            "linear_speed": 0.6,
            "angular_speed": 1.0,
            "linear_limit_mps": 3.0,
            "angular_limit_radps": 3.0,
        },
        axis_limit=100,
    )

    assert values == (0.6, 0.6, 1.0, -0.0)


def test_robot_remote_stream_drains_queued_keyboard_updates_before_send(monkeypatch):
    class FakeClient:
        instances = []

        def __init__(self, host, port, timeout):
            self.host = host
            self.port = port
            self.timeout = timeout
            self.remotes = []
            FakeClient.instances.append(self)

        def connect(self):
            return None

        def close(self):
            return None

        def handshake(self):
            return {"data": {}}

        def heartbeat(self):
            return {"data": {}}

        def send_heartbeat(self):
            return None

        def take_control(self):
            return {"data": {}}

        def release_control(self):
            return {"data": {}}

        def command(self, command_name):
            return {"data": {"cmd": command_name}}

        def remote(self, *values):
            self.remotes.append(values)

    read_fd, write_fd = os.pipe()
    os.write(
        write_fd,
        (
            '{"cmd":"set","forward":-60,"strafe":0,"turn":0,"pitch":0}\n'
            '{"cmd":"set","forward":0,"strafe":0,"turn":0,"pitch":0}\n'
        ).encode("utf-8"),
    )
    os.close(write_fd)

    monkeypatch.setattr(robot_remote_protocol, "RobotRemoteClient", FakeClient)
    with os.fdopen(read_fd, "r", encoding="utf-8") as reader:
        monkeypatch.setattr(sys, "stdin", reader)
        assert robot_remote_protocol.run_stream("127.0.0.1", 8081, 0.1, 100, 0.02) == 0

    remotes = FakeClient.instances[0].remotes
    assert remotes
    assert all(values == (0.0, 0.0, 0.0, 0.0) for values in remotes)


def test_robot_remote_stream_does_not_wait_for_heartbeat_ack(monkeypatch):
    class FakeClient:
        instances = []

        def __init__(self, host, port, timeout):
            self.events = []
            FakeClient.instances.append(self)

        def connect(self):
            self.events.append("connect")

        def close(self):
            self.events.append("close")

        def handshake(self):
            self.events.append("handshake")
            return {"data": {}}

        def heartbeat(self):
            raise TimeoutError("timed out")

        def send_heartbeat(self):
            self.events.append("send_heartbeat")

        def take_control(self):
            self.events.append("take_control")
            return {"data": {}}

        def release_control(self):
            self.events.append("release_control")
            return {"data": {}}

        def command(self, command_name):
            self.events.append(command_name)
            return {"data": {"cmd": command_name}}

        def remote(self, *values):
            self.events.append(("remote", values))

    read_fd, write_fd = os.pipe()
    os.write(write_fd, b'{"cmd":"quit"}\n')
    os.close(write_fd)

    monkeypatch.setattr(robot_remote_protocol, "RobotRemoteClient", FakeClient)
    with os.fdopen(read_fd, "r", encoding="utf-8") as reader:
        monkeypatch.setattr(sys, "stdin", reader)
        assert robot_remote_protocol.run_stream("127.0.0.1", 8081, 0.1, 100, 0.02) == 0

    events = FakeClient.instances[0].events
    assert "send_heartbeat" in events
    assert "take_control" in events
    assert "timed out" not in events


def test_robot_remote_stream_drains_server_messages(monkeypatch):
    class FakeClient:
        instances = []

        def __init__(self, host, port, timeout):
            self.events = []
            FakeClient.instances.append(self)

        def connect(self):
            self.events.append("connect")

        def close(self):
            self.events.append("close")

        def handshake(self):
            self.events.append("handshake")
            return {"data": {}}

        def send_heartbeat(self):
            self.events.append("send_heartbeat")

        def take_control(self):
            self.events.append("take_control")
            return {"data": {}}

        def release_control(self):
            self.events.append("release_control")
            return {"data": {}}

        def command(self, command_name):
            self.events.append(command_name)
            return {"data": {"cmd": command_name}}

        def remote(self, *values):
            self.events.append(("remote", values))

        def drain_pending(self):
            self.events.append("drain_pending")
            return 3

    read_fd, write_fd = os.pipe()
    os.write(write_fd, b'{"cmd":"quit"}\n')
    os.close(write_fd)

    monkeypatch.setattr(robot_remote_protocol, "RobotRemoteClient", FakeClient)
    with os.fdopen(read_fd, "r", encoding="utf-8") as reader:
        monkeypatch.setattr(sys, "stdin", reader)
        assert robot_remote_protocol.run_stream("127.0.0.1", 8081, 0.1, 100, 0.02) == 0

    assert "drain_pending" in FakeClient.instances[0].events


def test_robot_sdk_commands_use_robot_remote_endpoint_for_zg():
    probe = control.robot_remote_probe_command(get_product("zg3588"))
    posture = control.robot_sdk_posture_command(get_product("zg_surround_s100"), "stand")
    status = control.robot_sdk_posture_command(get_product("zg_surround_s100"), "status")
    stream = control.robot_sdk_stream_command(get_product("zg_lidar_nx"), axis_limit=100, interval_ms=20)

    assert "192.168.234.1" in probe.command
    assert "--read-only" in probe.command
    assert "/arc/dock_state" in posture.command
    assert "DOG_REMOTE_ARC_BLOCK_CHARGING=1" in posture.command
    assert "/robot_control_server/current_requester_info" in posture.command
    assert "robot-launch stop robot_roamerx" in posture.command
    assert "dog_remote_robot_roamerx_stopped_by_tool" in posture.command
    assert "robot-launch start robot_roamerx" in posture.command
    assert "trap _dog_remote_restore_roamerx EXIT INT TERM" in posture.command
    assert "--cmd action/stand_up" in posture.command
    assert "--robot-remote probe" not in status.command
    assert "/arc/dock_state" not in status.command
    assert "robot-launch stop robot_roamerx" not in status.command
    assert "robot-launch start robot_roamerx" not in status.command
    assert '{"cmd":"neutral"}' in status.command
    assert "--no-general" in status.command
    assert "/arc/dock_state" in stream
    assert "/robot_control_server/current_requester_info" in stream
    assert "robot-launch stop robot_roamerx" in stream
    assert "robot-launch restart robot_remote" in stream
    assert "清理上次未释放的 robot_remote 控制状态" in stream
    assert "another master exists" in stream
    assert "获取控制权.*被拒绝" in stream
    assert "occupied|busy|占用" in stream
    assert "mktemp /tmp/dog_remote_robot_remote_stream" in stream
    assert "_dog_remote_needs_restore_roamerx=0" in stream
    assert stream.index("_dog_remote_run_stream 2>&1") < stream.index("清理上次未释放的 robot_remote 控制状态")
    assert "dog_remote_robot_roamerx_stopped_by_tool" in stream
    assert "robot-launch start robot_roamerx" in stream
    assert "/control_right/test" not in stream
    assert "'{data: true}'" not in stream
    assert "'{data: false}'" not in stream
    assert "/robot_control_server/mc_state" not in stream
    assert "当前不是站立控制态" not in stream
    assert "--timeout 2" in stream
    assert "--robot-remote stream" in stream
    assert "--host 192.168.234.1" in stream


def test_navigation_mc_mode_command_publishes_zero_velcmd_after_nav_idle_guard():
    spec = control.navigation_mc_mode_command(get_product("zg_lidar_nx"), 1)
    same_knee = control.navigation_mc_mode_command(get_product("zg_lidar_nx"), 3)
    invalid = control.navigation_mc_mode_command(get_product("zg_lidar_nx"), 7)
    unsupported = control.navigation_mc_mode_command(get_product("xg2_s100"), 1)

    assert spec.title == "导航运控模式：对膝 WALK"
    assert spec.dangerous is True
    assert "source /opt/robot/robot_nav/install/setup.bash" in spec.command
    assert "/navigation_state" in spec.command
    assert "拒绝手动切换运控模式" in spec.command
    assert "CMD_TOPIC=/navigo/cs/cmn/intf/cmd_vel_raw" in spec.command
    assert "robots_dog_msgs/msg/VelCmd" in spec.command
    assert 'create_publisher(VelCmd, "/navigo/cs/cmn/intf/cmd_vel_raw", 10)' in spec.command
    assert "sequence = [1]" in spec.command
    assert "mc_mode_cmd = int(mode)" in spec.command
    assert "duration_by_mode = {1: 1.1}" in spec.command
    assert same_knee.title == "导航运控模式：同膝 WALK"
    assert "sequence = [1, 3]" in same_knee.command
    assert "不支持的 mc_mode_cmd: 7" in invalid.command
    assert "当前仅支持中狗 NX/S100" in unsupported.command


def test_body_realtime_stream_command_selects_profile_backend():
    l2_stream = control.body_realtime_stream_command(get_product("xg2_s100"), axis_limit=100, interval_ms=20)
    zg_stream = control.body_realtime_stream_command(get_product("zg_lidar_nx"), axis_limit=100, interval_ms=20)

    assert "/arc/dock_state" in l2_stream
    assert "/robot_control_server/current_requester_info" in l2_stream
    assert "robot-launch stop robot_roamerx" in l2_stream
    assert "robot-launch restart robot_remote" in l2_stream
    assert "robot-launch start robot_roamerx" in l2_stream
    assert "/control_right/test" not in l2_stream
    assert "'{data: true}'" not in l2_stream
    assert "'{data: false}'" not in l2_stream
    assert "dog_remote_gamepad_stream" not in l2_stream
    assert "--robot-remote stream" in l2_stream
    assert "--host 192.168.234.1" in l2_stream
    assert "/arc/dock_state" in zg_stream
    assert "/robot_control_server/current_requester_info" in zg_stream
    assert "robot-launch stop robot_roamerx" in zg_stream
    assert "robot-launch restart robot_remote" in zg_stream
    assert "robot-launch start robot_roamerx" in zg_stream
    assert "/control_right/test" not in zg_stream
    assert "'{data: true}'" not in zg_stream
    assert "'{data: false}'" not in zg_stream
    assert "/robot_control_server/mc_state" not in zg_stream
    assert "当前不是站立控制态" not in zg_stream
    assert "--timeout 2" in zg_stream
    assert "--robot-remote stream" in zg_stream
    assert "--host 192.168.234.1" in zg_stream


def test_l2_realtime_stream_keeps_fast_first_attempt():
    stream = control.body_realtime_stream_command(get_product("xg2_s100"), axis_limit=100, interval_ms=20)

    assert stream.index("_dog_remote_run_stream 2>&1") < stream.index("正在切换导航控制权")


def test_zg_realtime_stream_also_keeps_fast_first_attempt():
    stream = control.body_realtime_stream_command(get_product("zg_lidar_nx"), axis_limit=100, interval_ms=20)

    assert stream.index("_dog_remote_run_stream 2>&1") < stream.index("清理上次未释放的 robot_remote 控制状态")


def test_l2_posture_action_uses_robot_remote_with_arc_guard():
    command = control.robot_sdk_posture_command(get_product("xg2_s100"), "stand")

    assert "/arc/dock_state" in command.command
    assert "DOG_REMOTE_ARC_BLOCK_CHARGING=1" in command.command
    assert "请先退出充电/回充" in command.command
    assert "--robot-remote posture" in command.command
    assert "--host 192.168.234.1" in command.command
    assert "--cmd action/stand_up" in command.command


def test_control_video_stream_command_prepares_rtsp_media_services():
    command = control.control_video_stream_command(get_product("xg2_s100"), "front", 20, 90)

    assert "准备远端媒体服务" in command
    assert "rtsp://192.168.168.100:8554/front" in command
    assert "robot-launch start" in command
    assert "media_server push_video push_ffmedia push_image" in command
    assert "dog_remote_rtsp_path_ready" in command
    assert "远端路径 /front 未就绪，尝试自动部署桥接" in command
    assert "自动部署 RTSP 桥接: /front_stereo_camera/image_compressed -> /front" in command
    assert "rclpy" in command
    assert "base64" not in command


def test_control_video_stream_command_auto_deploys_s100_surround_sources():
    profile = get_product("xg2_s100")
    expected = {
        "front": "/front_stereo_camera/image_compressed",
        "back": "/rear_fisheye/image_compressed",
        "left": "/left_fisheye/image_compressed",
        "right": "/right_fisheye/image_compressed",
    }

    for source, topic in expected.items():
        command = control.control_video_stream_command(profile, source)
        assert f"自动部署 RTSP 桥接: {topic} -> /{source}" in command
        assert "DOG_REMOTE_RTSP_SOURCES" in command
        assert topic in command
        assert source in command


def test_control_video_stream_command_uploads_bundled_rtsp_debs(tmp_path, monkeypatch):
    deb_dir = tmp_path / "debs"
    deb_dir.mkdir()
    (deb_dir / "python3-gi_1.0_arm64.deb").write_bytes(b"deb")
    monkeypatch.setattr(control_video, "rtsp_bridge_deb_dir", lambda: deb_dir)

    command = control.control_video_stream_command(get_product("xg2_s100"), "front")

    assert "rsync -az --delete" in command
    assert str(deb_dir) + "/" in command
    assert "/tmp/dog_remote_rtsp_debs/" in command
    assert "dpkg-query -W" in command
    assert 'Gst.ElementFactory.find(name)' in command
    assert '"x264enc"' in command
    assert '"rtph264pay"' in command
    assert "sudo_run dpkg --configure -a" in command
    assert "sudo_run dpkg -i $(cat /tmp/dog_remote_rtsp_deps_missing.list)" in command
    assert "tail -80 /tmp/dog_remote_rtsp_deps_install.log" in command
    assert "RTSP 桥接依赖安装失败" in command
    assert "apt-get install" not in command


def test_control_video_stream_command_uses_one_media_prepare_path_for_xg3588():
    profile = get_product("xg3588")
    command = control.control_video_stream_command(profile, "front")

    assert control.control_video_rtsp_url(profile, "front") == "rtsp://192.168.234.1:8554/test"
    assert "rtsp://192.168.234.1:8554/test" in command
    assert "robot-launch stop push_ffmedia" not in command
    assert "for name in media_server push_video push_ffmedia push_image remote-video remote_video" in command
    assert 'robot-launch start "$name"' in command
    assert "DESCRIBE rtsp://" in command
    assert "sleep " not in command


def test_control_video_rtsp_url_maps_topics_without_ros_subscription():
    profile = get_product("xg2_s100")

    assert control.control_video_rtsp_url(profile, "/front_stereo_camera/image_compressed") == "rtsp://192.168.168.100:8554/front"
    assert control.control_video_rtsp_url(profile, "/rear_fisheye/image_compressed") == "rtsp://192.168.168.100:8554/back"
    assert control.control_video_rtsp_url(profile, "left") == "rtsp://192.168.168.100:8554/left"
    assert control.control_video_rtsp_url(profile, "/rs_rgb_img/compressed") == "rtsp://192.168.168.100:8554/front"
    assert control.control_video_rtsp_url(profile, "/rs_ir_left/compressed") == "rtsp://192.168.168.100:8554/depth"
    assert control.control_video_rtsp_url(profile, "/rs_depth_img/compressedDepth") == "rtsp://192.168.168.100:8554/depth"


def test_control_video_rtsp_uses_3588_media_host_for_zg_nx():
    profile = get_product("zg_lidar_nx")
    command = control.control_video_stream_command(profile, "front")

    assert control.control_video_rtsp_url(profile, "front") == "rtsp://192.168.234.1:8554/front"
    assert control.control_video_rtsp_service_profile(profile).key == "zg3588"
    assert "robot@192.168.234.1" in command
    assert "robot@192.168.168.100" not in command


def test_control_video_stream_command_rejects_empty_source():
    command = control.control_video_stream_command(get_product("xg2_s100"), "")

    assert "视频源不能为空" in command
    assert "exit 2" in command


def test_robot_sdk_body_telemetry_uses_medium_dog_controller():
    command = control.robot_sdk_body_telemetry_stream_command(get_product("zg_surround_s100"))

    assert "robot@192.168.234.1" in command
    assert command.index("192.168.234.0/24") < command.index("dog_remote_l2_body_telemetry")
    assert "/robot_control_server/mc_state" in command


def test_robot_sdk_body_telemetry_uses_l2_3588_controller():
    command = control.robot_sdk_body_telemetry_stream_command(get_product("xg2_s100"))

    assert "robot@192.168.234.1" in command
    assert command.index("192.168.234.0/24") < command.index("dog_remote_l2_body_telemetry")
    assert "/robot_control_server/mc_state" in command


def test_l2_nav_speed_status_command_keeps_display_and_parallel_mode():
    assert control.l2_nav_speed_status_command is control_speed_l2.l2_nav_speed_status_command

    spec = control.l2_nav_speed_status_command(get_product("xg2_s100"))

    assert spec.title == "读取 L2 导航速度"
    assert spec.concurrency == "parallel"
    assert "remote_config.yaml" in spec.command
    assert spec.display_command == "执行：读取导航速度"


def test_l1_sdk_prepare_auto_command_keeps_candidate_probe():
    spec = control.l1_sdk_prepare_auto_command(get_product("xg3588"), "")

    assert spec.title == "L1 SDK 准备"
    assert "sdk_auto_candidates=" in spec.command
    assert "mc_sdk_zsl_1_py" in spec.command
    assert "mc_sdk_zsl_1w_py" in spec.command


def test_l1_sdk_move_command_clamps_motion_values():
    spec = control.l1_sdk_move_command(get_product("xg3588"), "zsl-1", "", 99.0, -99.0, 99.0, 10.0)

    assert spec.title == "L1 SDK 短时移动"
    assert spec.dangerous is True
    assert "vx=3.00, vy=-1.00, yaw=3.00, 5.00s" in spec.display_command
    assert "vx = 3.0000" in spec.command
    assert "vy = -1.0000" in spec.command
    assert "yaw = 3.0000" in spec.command
    assert "duration = 5.000" in spec.command


def test_l1_sdk_stream_command_clamps_speed_and_interval():
    command = control.l1_sdk_stream_command(get_product("xg3588"), "", speed_percent=1, interval_ms=999)

    assert command.index("192.168.234.0/24") < command.index("dog_remote_l1_sdk_stream")
    assert "DOG_REMOTE_L1_PERCENT_LIMIT=5" in command
    assert "DOG_REMOTE_L1_INTERVAL=0.1" in command
    assert "dog_remote_l1_sdk_stream" in command
    assert "def iter_pending_commands():" in command
    assert "for command in iter_pending_commands():" in command
    assert '"passive", "crawl"' in command
    assert "app.crawl(0.0, 0.0, 0.0)" in command
    assert "twoLegStand" not in command
    assert "attitudeControl" not in command


def test_l1_sdk_stream_requires_verified_stand_mode_before_move():
    command = control.l1_sdk_stream_command(get_product("xg3588"), "", speed_percent=100, interval_ms=20)

    assert "ready_ctrl_modes = (1, 3, 18)" in command
    assert '"stand_not_ready"' in command
    assert 'f"{prefix} ctrl_mode=' in command
    assert "standUp 后控制模式仍为" in command
    assert "L1 SDK 连接超时，未建立有效控制会话" in command
    assert "wait_sdk_connected" in command
    assert "未进入站立/移动状态，请先点击站立或按 1" in command
    assert "if vector != last_sent and stand_ready:" in command


def test_l1_sdk_deploy_rejects_unsafe_remote_target_before_local_check():
    spec = control.l1_sdk_deploy_command(get_product("xg3588"), "/definitely/missing", "/tmp'a")

    assert spec.title == "部署 L1 SDK"
    assert spec.dangerous is False
    assert "远端 SDK 目标目录不安全" in spec.command
    assert "echo '[ERROR] 远端 SDK" not in spec.command


def test_l1_sdk_deploy_uses_route_repair_for_wired_targets(tmp_path):
    spec = control.l1_sdk_deploy_command(get_product("xg3588"), str(tmp_path), "/home/firefly/genisom_l1_sdk")

    assert spec.title == "部署 L1 SDK"
    assert spec.dangerous is True
    assert spec.command.index("192.168.234.0/24") < spec.command.index(" rsync -az ")
    assert "--delete" in spec.command
    assert "--exclude __pycache__" in spec.command
    assert "sshpass -p" not in spec.command
    assert "firefly@192.168.234.1:/home/firefly/genisom_l1_sdk/" in spec.command


def test_l1_sdk_basic_actions_include_crawl_and_remove_inplace_mode():
    crawl = control.l1_sdk_basic_action_command(get_product("xg3588"), "", "crawl")
    head = control.l1_sdk_basic_action_command(get_product("xg3588"), "", "head")
    lie = control.l1_sdk_basic_action_command(get_product("xg3588"), "", "lie")
    passive = control.l1_sdk_basic_action_command(get_product("xg3588"), "", "passive")
    stand = control.l1_sdk_basic_action_command(get_product("xg3588"), "", "stand")

    assert crawl.title == "L1 SDK 匍匐"
    assert crawl.dangerous is True
    assert "app.crawl(0.0, 0.0, 0.0)" in crawl.command
    assert "当前 SDK 型号不支持匍匐 crawl" in crawl.command
    assert "L1 SDK 连接超时，未建立有效控制会话" in stand.command
    assert "wait_sdk_connected" in stand.command
    assert head.title == "L1 SDK 动作"
    assert head.dangerous is False
    assert "未知动作" in head.command
    assert "echo '[ERROR] 未知动作" not in head.command
    assert "twoLegStand" not in head.command
    assert "attitudeControl" not in head.command
    assert lie.title == "L1 SDK 低姿态"
    assert "action = 'lieDown'" in lie.command
    assert "getattr(app, action)()" in lie.command
    assert passive.title == "L1 SDK 阻尼趴下"
    assert passive.dangerous is True
    assert "action = 'passive'" in passive.command
    assert "cancelCrawl" in stand.command
    assert "cancelTwoLegStand" in stand.command
    assert "already_stand_ctrl_mode" in stand.command
    assert "current_ctrl_mode()" in stand.command


def test_l2_body_telemetry_stream_has_bounded_document_buffer():
    command = control.robot_sdk_body_telemetry_stream_command(get_product("xg2_s100"))

    assert "DOG_REMOTE_L2_TELEMETRY_MAX_DOC_LINES=400" in command
    assert "drop oversized telemetry document" in command
    assert "proc.wait(timeout=2)" in command
