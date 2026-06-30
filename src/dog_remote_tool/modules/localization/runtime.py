from __future__ import annotations

from dog_remote_tool.core.profiles import ProductProfile
from dog_remote_tool.core.shell import (
    CommandSpec,
    echo_message,
    quote,
    remote_env,
    ssh_command,
)
import dog_remote_tool.modules.localization.pose_record as _pose_record
import dog_remote_tool.modules.localization.alg as _localization_alg
import dog_remote_tool.modules.localization.odom_bridge as _odom_bridge


REMOTE_POSE_RECORD = "/home/robot/pose_xyz.txt"
REMOTE_POSE_RECORD_PID = "/tmp/dog_remote_tool_pose_xyz.pid"
REMOTE_POSE_RECORD_LOG = "/tmp/dog_remote_tool_pose_xyz.log"


def _emit_final_pose_inner() -> str:
    pose_parser = (
        "awk '"
        "BEGIN{inpos=0; inori=0} "
        "/^    position:/{inpos=1; inori=0; next} "
        "/^    orientation:/{inpos=0; inori=1; next} "
        "/^  covariance:/{inpos=0; inori=0; next} "
        "inpos && /^      x:/{px=$2; next} "
        "inpos && /^      y:/{py=$2; next} "
        "inori && /^      x:/{ox=$2; next} "
        "inori && /^      y:/{oy=$2; next} "
        "inori && /^      z:/{oz=$2; next} "
        "inori && /^      w:/{ow=$2; next} "
        "END{"
        "if(px==\"\" || py==\"\"){exit 1} "
        "yaw=atan2(2*(ow*oz+ox*oy), 1-2*(oy*oy+oz*oz)); "
        "printf \"[DOG_REMOTE_FINAL_POSE] X=%s Y=%s YAW=%s\\n\", px, py, yaw"
        "}'"
    )
    return (
        "emit_final_pose() { "
        "POSE_MSG=; "
        "for pose_topic in /odom/current_pose /odom/localization_odom; do "
        "CANDIDATE=$(timeout 2s ros2 topic echo --once \"$pose_topic\" --no-daemon 2>/dev/null || true); "
        "if printf '%s\\n' \"$CANDIDATE\" | grep -q 'position:'; then POSE_MSG=\"$CANDIDATE\"; break; fi; "
        "done; "
        f"printf '%s\\n' \"$POSE_MSG\" | {pose_parser} || true; "
        "}; "
    )


def _alg_localization_load_inner(profile: ProductProfile, map_pcd_path: str, timeout_seconds: int = 45) -> str:
    alg_load = _localization_alg.alg_localization_load_inner(profile, map_pcd_path, timeout_seconds)
    return (
        f"{alg_load}; "
        "ALG_LOCALIZATION_RC=$?; "
        "if [ \"$ALG_LOCALIZATION_RC\" -ne 0 ]; then exit \"$ALG_LOCALIZATION_RC\"; fi; "
        "echo '[INFO] 系统定位流程完成'; "
    )


def start_localization_command(
    profile: ProductProfile,
    sensor_type: str,
    save_map_path: str,
    calibration_file_path: str,
    arc_calibration_file_path: str,
    map_pcd_path: str,
    record_pose: bool = False,
    ensure_current_pose_bridge: bool = False,
) -> CommandSpec:
    del sensor_type, save_map_path, calibration_file_path, arc_calibration_file_path
    pose_record_start = _pose_record.start_pose_record_inner(profile, REMOTE_POSE_RECORD, REMOTE_POSE_RECORD_PID, REMOTE_POSE_RECORD_LOG) if record_pose else "true"
    current_pose_bridge = _odom_bridge.ensure_current_pose_bridge_inner() if ensure_current_pose_bridge else "true; "
    localization_load = _alg_localization_load_inner(profile, map_pcd_path, 45)
    inner = (
        f"{localization_load}"
        f"{pose_record_start}; "
        f"{current_pose_bridge}"
        "echo '[INFO] 定位地图已加载'"
    )
    return CommandSpec("开始定位", ssh_command(profile, inner))


def test_localization_once_command(
    profile: ProductProfile,
    sensor_type: str,
    save_map_path: str,
    calibration_file_path: str,
    arc_calibration_file_path: str,
    map_pcd_path: str,
    record_pose: bool = False,
) -> CommandSpec:
    del sensor_type, save_map_path, arc_calibration_file_path
    pose_record_start = _pose_record.start_pose_record_inner(profile, REMOTE_POSE_RECORD, REMOTE_POSE_RECORD_PID, REMOTE_POSE_RECORD_LOG) if record_pose else "true"
    pose_record_stop = _pose_record.stop_pose_record_inner(REMOTE_POSE_RECORD_PID) if record_pose else "true"
    localization_load = _alg_localization_load_inner(profile, map_pcd_path, 45)
    inner = (
        f"{remote_env(profile)}; "
        "source /opt/robot/robot_nav/install/setup.bash >/dev/null 2>&1 || true; "
        "source /opt/robot/robot_slam/install/setup.bash >/dev/null 2>&1 || true; "
        f"{_emit_final_pose_inner()}"
        f"if [ ! -f {quote(calibration_file_path)} ]; then {echo_message(f'[ERROR] calibration file missing: {calibration_file_path}')}; exit 2; fi; "
        f"if [ ! -f {quote(map_pcd_path)} ]; then {echo_message(f'[ERROR] map pcd missing: {map_pcd_path}')}; exit 2; fi; "
        "cleanup() { "
        f"{pose_record_stop}; "
        "echo '[INFO] 单次测试结束，清理本次定位测试资源'; "
        "}; "
        "trap cleanup EXIT; "
        f"{pose_record_start}; "
        f"{localization_load}"
        "echo '[INFO] 定位地图已加载，alg已进入连续定位'; "
        "emit_final_pose; "
        "echo '[SUCCESS] 定位成功'"
    )
    return CommandSpec("测试定位", ssh_command(profile, inner))


def stop_localization_command(profile: ProductProfile) -> CommandSpec:
    inner = (
        "echo '[INFO] 清理定位辅助任务'; "
        f"{_pose_record.stop_pose_record_inner(REMOTE_POSE_RECORD_PID)}; "
        f"{_odom_bridge.stop_current_pose_bridge_inner()}; "
        "echo '[INFO] 定位辅助任务已清理；系统定位由 alg_manager 管理'"
    )
    return CommandSpec("关闭定位", ssh_command(profile, inner))
