from __future__ import annotations

from dog_remote_tool.core.profiles import ProductProfile
from dog_remote_tool.core.shell import CommandSpec, quote, remote_env, ssh_command
import dog_remote_tool.modules.control.l1 as _control_l1
import dog_remote_tool.modules.control.mc_mode as _control_mc_mode
import dog_remote_tool.modules.control.robot_remote.commands as _robot_remote_commands
import dog_remote_tool.modules.control.shared as _control_shared
import dog_remote_tool.modules.control.speed as _control_speed
import dog_remote_tool.modules.control.video as _control_video

arc_charging_guard_command = _control_shared.arc_charging_guard_command
l1_control_profile = _control_shared.l1_control_profile
l2_control_profile = _control_shared.l2_control_profile
l2_s100_profile = _control_shared.l2_s100_profile
robot_sdk_control_profile = _control_shared.robot_sdk_control_profile
robot_remote_control_profile = _control_shared.robot_remote_control_profile
robot_remote_restore_occupancy_command = _control_shared.robot_remote_restore_occupancy_command
tool_cli = _control_shared.tool_cli
speed_override_command = _control_speed.speed_override_command
l2_nav_speed_status_command = _control_speed.l2_nav_speed_status_command
l2_nav_speed_override_command = _control_speed.l2_nav_speed_override_command
navigation_mc_mode_command = _control_mc_mode.navigation_mc_mode_command

ROBOT_REMOTE_COMMANDS = _robot_remote_commands.ROBOT_REMOTE_COMMANDS
L1_LOCAL_SDK_PATH = _control_l1.L1_LOCAL_SDK_PATH
L1_DEFAULT_REMOTE_SDK_PATH = _control_l1.L1_DEFAULT_REMOTE_SDK_PATH
L1_SDK_MODES = _control_l1.L1_SDK_MODES
L1_SDK_ACTIONS = _control_l1.L1_SDK_ACTIONS
l1_sdk_mode = _control_l1.l1_sdk_mode
l1_sdk_status_command = _control_l1.l1_sdk_status_command
l1_sdk_prepare_command = _control_l1.l1_sdk_prepare_command
l1_sdk_prepare_auto_command = _control_l1.l1_sdk_prepare_auto_command
l1_sdk_deploy_command = _control_l1.l1_sdk_deploy_command
l1_sdk_action_command = _control_l1.l1_sdk_action_command
l1_sdk_basic_action_command = _control_l1.l1_sdk_basic_action_command
l1_sdk_move_command = _control_l1.l1_sdk_move_command
l1_sdk_stream_command = _control_l1.l1_sdk_stream_command

def ros_move_command(profile: ProductProfile, vx: float, vy: float, yaw: float, duration: float) -> CommandSpec:
    payload = f"{{vx: {vx:.3f}, vy: {vy:.3f}, yaw_rate: {yaw:.3f}, duration: {duration:.2f}}}"
    inner = (
        f"{remote_env(profile)}; "
        "echo '发送短时速度命令'; "
        f"timeout {duration + 1:.1f}s ros2 topic pub --once /robot_control_server/move std_msgs/msg/String {quote(payload)}"
    )
    return CommandSpec("短时移动", ssh_command(profile, inner), dangerous=True)


control_video_stream_command = _control_video.video_stream_command
control_video_rtsp_host = _control_video.rtsp_host
control_video_rtsp_path = _control_video.rtsp_path
control_video_rtsp_service_profile = _control_video.rtsp_service_profile
control_video_rtsp_url = _control_video.rtsp_url



def action_command(profile: ProductProfile, action: str) -> CommandSpec:
    inner = (
        f"{remote_env(profile)}; "
        f"ros2 service call /robot_control_server/{quote(action)} std_srvs/srv/Trigger '{{}}' "
        "|| echo '当前设备可能不支持该动作服务'"
    )
    return CommandSpec(f"动作: {action}", ssh_command(profile, inner), dangerous=action in {"estop"})


robot_remote_probe_command = _robot_remote_commands.robot_remote_probe_command
robot_remote_posture_command = _robot_remote_commands.robot_remote_posture_command
robot_sdk_posture_command = _robot_remote_commands.robot_sdk_posture_command
robot_sdk_stream_command = _robot_remote_commands.robot_sdk_stream_command
body_realtime_stream_command = _robot_remote_commands.body_realtime_stream_command
robot_sdk_body_telemetry_stream_command = _robot_remote_commands.robot_sdk_body_telemetry_stream_command
