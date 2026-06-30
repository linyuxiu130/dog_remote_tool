from __future__ import annotations

from dog_remote_tool.core.profiles import ProductProfile
from dog_remote_tool.core.ros_shell import service_exists, topic_publisher_count, topic_subscription_count
from dog_remote_tool.core.shell import CommandSpec, quote, remote_env, ssh_command
from dog_remote_tool.modules.arc_app_ws import common_arc_app_ws_python
from dog_remote_tool.modules.mapping import arc_status as mapping_arc_status
import dog_remote_tool.modules.localization.alg as _localization_alg
from dog_remote_tool.modules.navigation import probe_graph
from dog_remote_tool.modules.navigation import probe_motion


NAVIGATION_LOG = "/tmp/log/alg_data/navigation_with_setup.log"


def navigation_process_filter() -> str:
    return (
        "ps -eo pid=,args= | awk -v self=$$ '"
        "$1 != self && $0 !~ /awk -v self/ && "
        "($0 ~ /robot_alg_manager/ || $0 ~ /navigation_bringup\\.launch\\.py/ || "
        "$0 ~ /navigo_waypoint_follower/ || $0 ~ /navigo_bt_navigator/) {print $0; found=1} "
        "END {exit !found}'"
    )


def app_nav_status_probe_shell() -> str:
    python = common_arc_app_ws_python() + "\n" + r'''
import json, time
request = {
    "head": {"type": "app_req", "time_stamp": int(time.time() * 1000), "source": "app", "frame_count": 1},
    "data": {"req_func": "get_nav_status"},
}
try:
    client = AppWsBrokerClient()
    for message in client.request(request, "get_nav_status", 2):
        parsed = parse_app_response(message)
        if isinstance(parsed, dict) and parsed.get("kind") == "app_resp" and parsed.get("func") == "get_nav_status":
            print(str(parsed.get("data") or ""))
            raise SystemExit(0)
except Exception:
    pass
print("")
'''.strip()
    return f"APP_NAV_STATUS=$(python3 -c {quote(python)} 2>/dev/null | tail -1); echo APP_NAV_STATUS=$APP_NAV_STATUS; "


def topic_count_assignments(topic: str, key: str, timeout: int | float = 2) -> str:
    return probe_motion.topic_count_assignments(topic, key, timeout)


def localization_state_probe_shell(profile: ProductProfile, require_nav_accepted_status: bool = False) -> str:
    del profile, require_nav_accepted_status
    return (
        f"ALG_LOC_OUTPUT=$({_localization_alg.alg_loc_status_inner()} || true); "
        "printf '%s\\n' \"$ALG_LOC_OUTPUT\"; "
        "LOC_CODE=$(printf '%s\\n' \"$ALG_LOC_OUTPUT\" | awk -F= '/^ALG_LOC_STATUS=/ {value=$2} END {print value}'); "
        "LOC_CODE_FIELD=alg; LOC_RATE=; LOC_DESC=$LOC_CODE; "
        "echo ROBOT_LOCALIZATION_PUBLISHERS=; "
        "echo LEGACY_LOCALIZATION_PUBLISHERS=; "
        "echo LOCALIZATION_TOPIC=alg:get_loc_status; "
        "echo LOCALIZATION_CODE=${LOC_CODE:-}; "
        "echo LOCALIZATION_CODE_FIELD=${LOC_CODE_FIELD:-}; "
        "echo LOCALIZATION_RATE=${LOC_RATE:-}; "
        "echo LOCALIZATION_DESC=${LOC_DESC:-}; "
        "case \"$LOC_CODE\" in ContinuousLoc|continuousloc|LocOk|InitLocOk) LOCALIZATION_READY=1 ;; *) LOCALIZATION_READY=0 ;; esac; "
        "echo LOCALIZATION_READY=$LOCALIZATION_READY"
    )


def fast_localization_state_probe_shell(profile: ProductProfile) -> str:
    return localization_state_probe_shell(profile)


def navigation_graph_status_probe_shell() -> str:
    return probe_graph.navigation_graph_status_probe_shell()


def topic_stamp_age_probe_shell(topic: str, key: str, timeout: int | float = 3) -> str:
    return (
        f"{key}_STAMP_AGE_MS=; {key}_STAMP_SEC=; {key}_STAMP_NSEC=; "
        f"if printf '%s\\n' \"$TOPIC_LIST\" | grep -Fx -- {quote(topic)} >/dev/null; then "
        f"{key}_STAMP_MSG=$(timeout {timeout}s ros2 topic echo --once {quote(topic)} --no-daemon 2>/dev/null || true); "
        f"{key}_STAMP_PAIR=$(printf '%s\\n' \"${key}_STAMP_MSG\" | awk "
        "'/sec:/ && sec==\"\" {sec=$2} /nanosec:/ && sec!=\"\" {print sec, $2; exit}'); "
        f"{key}_STAMP_SEC=$(printf '%s\\n' \"${key}_STAMP_PAIR\" | awk '{{print $1}}'); "
        f"{key}_STAMP_NSEC=$(printf '%s\\n' \"${key}_STAMP_PAIR\" | awk '{{print $2}}'); "
        f"if [ -n \"${key}_STAMP_SEC\" ] && [ -n \"${key}_STAMP_NSEC\" ]; then "
        f"{key}_NOW_NS=$(date +%s%N); "
        f"{key}_STAMP_NS=$(( {key}_STAMP_SEC * 1000000000 + {key}_STAMP_NSEC )); "
        f"{key}_STAMP_AGE_MS=$(( ( {key}_NOW_NS - {key}_STAMP_NS ) / 1000000 )); "
        "fi; "
        "fi; "
        f"echo {key}_STAMP_AGE_MS=${key}_STAMP_AGE_MS; "
        f"echo {key}_STAMP_SEC=${key}_STAMP_SEC"
    )


def navigation_state_probe_shell(timeout: int | float = 2) -> str:
    return (
        "if printf '%s\\n' \"$TOPIC_LIST\" | grep -Fx -- /navigation_state >/dev/null; then NAV_STATE_PUBLISHERS=1; else NAV_STATE_PUBLISHERS=0; fi; echo NAV_STATE_PUBLISHERS=$NAV_STATE_PUBLISHERS; "
        f"if [ \"$NAV_STATE_PUBLISHERS\" -gt 0 ]; then NAV_MSG=$(timeout {timeout}s ros2 topic echo --once /navigation_state --no-daemon 2>/dev/null || true); else NAV_MSG=; fi; "
        "NAV_STATE=$(printf '%s\\n' \"$NAV_MSG\" | awk '/^state:/ {print $2; exit}'); "
        "NAV_CURRENT_TASK_IDX=$(printf '%s\\n' \"$NAV_MSG\" | awk '/^current_task_idx:/ {print $2; exit}'); "
        "NAV_SUBSTATE=$(printf '%s\\n' \"$NAV_MSG\" | awk '/^active_substate:/ {print $2; exit}'); "
        "NAV_TASK_STATUS=$(printf '%s\\n' \"$NAV_MSG\" | awk -v idx=\"${NAV_CURRENT_TASK_IDX:-0}\" '"
        "BEGIN {in_list=0; current=-1} "
        "/^task_status_list:/ {in_list=1; next} "
        "in_list && /^-/ {current++} "
        "in_list && /task_status:/ {if (current < 0) current=0; if (current == idx) {print $NF; exit}} "
        "in_list && /^[^[:space:]-]/ {in_list=0}'"
        "); "
        "[ -n \"$NAV_TASK_STATUS\" ] || NAV_TASK_STATUS=$(printf '%s\\n' \"$NAV_MSG\" | awk '/task_status:/ {print $NF; exit}'); "
        "NAV_DISTANCE_FROM_START=$(printf '%s\\n' \"$NAV_MSG\" | awk '/^distance_from_start:/ {print $2; exit}'); "
        "NAV_ESTIMATED_DISTANCE_REMAINING=$(printf '%s\\n' \"$NAV_MSG\" | awk '/^estimated_distance_remaining:/ {print $2; exit}'); "
        "NAV_ESTIMATED_TIME_REMAINING_SEC=$(printf '%s\\n' \"$NAV_MSG\" | awk '"
        "BEGIN {section=0} "
        "/^estimated_time_remaining:/ {section=1; next} "
        "section && /^[[:space:]]*sec:/ {print $2; exit} "
        "section && /^[^[:space:]]/ {section=0}'"
        "); "
        "NAV_ERROR=$(printf '%s\\n' \"$NAV_MSG\" | sed -n 's/^[[:space:]]*message:[[:space:]]*//p' | head -1 | sed \"s/^'//;s/'$//\"); "
        "echo NAV_STATE=${NAV_STATE:-}; "
        "echo NAV_ACTIVE_SUBSTATE=${NAV_SUBSTATE:-}; "
        "echo NAV_TASK_STATUS=${NAV_TASK_STATUS:-}; "
        "echo NAV_CURRENT_TASK_IDX=${NAV_CURRENT_TASK_IDX:-}; "
        "echo NAV_DISTANCE_FROM_START=${NAV_DISTANCE_FROM_START:-}; "
        "echo NAV_ESTIMATED_DISTANCE_REMAINING=${NAV_ESTIMATED_DISTANCE_REMAINING:-}; "
        "echo NAV_ESTIMATED_TIME_REMAINING_SEC=${NAV_ESTIMATED_TIME_REMAINING_SEC:-}; "
        "echo NAV_ERROR=${NAV_ERROR:-}"
    )


def fast_navigation_state_probe_shell() -> str:
    script = """import time

import rclpy
from robots_dog_msgs.msg import NavigationState

state = {
    "seen": False,
    "nav_state": "",
    "substate": "",
    "task": "",
    "idx": "",
    "distance": "",
    "remaining": "",
    "eta": "",
    "error": "",
}

def emit(key, value):
    print(f"{key}={value}", flush=True)

def on_message(msg):
    state["seen"] = True
    state["nav_state"] = str(getattr(msg, "state", "") or "")
    state["substate"] = str(getattr(msg, "active_substate", "") or "")
    state["idx"] = str(getattr(msg, "current_task_idx", "") or "")
    tasks = getattr(msg, "task_status_list", None) or []
    if tasks:
        try:
            idx = int(getattr(msg, "current_task_idx", 0) or 0)
        except Exception:
            idx = 0
        if idx < 0 or idx >= len(tasks):
            idx = 0
        state["task"] = str(getattr(tasks[idx], "task_status", "") or "")
    state["distance"] = str(getattr(msg, "distance_from_start", "") or "")
    state["remaining"] = str(getattr(msg, "estimated_distance_remaining", "") or "")
    eta = getattr(msg, "estimated_time_remaining", None)
    if eta is not None:
        state["eta"] = str(getattr(eta, "sec", "") or "")
    state["error"] = str(getattr(msg, "message", "") or "")

rclpy.init()
node = rclpy.create_node("dog_remote_fast_nav_state_probe")
node.create_subscription(NavigationState, "/navigation_state", on_message, 10)
deadline = time.monotonic() + 0.8
try:
    while time.monotonic() < deadline and not state["seen"]:
        rclpy.spin_once(node, timeout_sec=0.05)
finally:
    node.destroy_node()
    rclpy.shutdown()

emit("NAV_STATE", state["nav_state"])
emit("NAV_ACTIVE_SUBSTATE", state["substate"])
emit("NAV_TASK_STATUS", state["task"])
emit("NAV_CURRENT_TASK_IDX", state["idx"])
emit("NAV_DISTANCE_FROM_START", state["distance"])
emit("NAV_ESTIMATED_DISTANCE_REMAINING", state["remaining"])
emit("NAV_ESTIMATED_TIME_REMAINING_SEC", state["eta"])
emit("NAV_ERROR", state["error"])
"""
    return (
        "if printf '%s\\n' \"$TOPIC_LIST\" | grep -Fx -- /navigation_state >/dev/null; then NAV_STATE_PUBLISHERS=1; else NAV_STATE_PUBLISHERS=0; fi; echo NAV_STATE_PUBLISHERS=$NAV_STATE_PUBLISHERS; "
        "if [ \"$NAV_STATE_PUBLISHERS\" -gt 0 ]; then "
        f"timeout 2s python3 -c {quote(script)} 2>/dev/null || "
        "(echo NAV_STATE=; echo NAV_ACTIVE_SUBSTATE=; echo NAV_TASK_STATUS=; echo NAV_CURRENT_TASK_IDX=; echo NAV_DISTANCE_FROM_START=; echo NAV_ESTIMATED_DISTANCE_REMAINING=; echo NAV_ESTIMATED_TIME_REMAINING_SEC=; echo NAV_ERROR=); "
        "else "
        "echo NAV_STATE=; echo NAV_ACTIVE_SUBSTATE=; echo NAV_TASK_STATUS=; echo NAV_CURRENT_TASK_IDX=; "
        "echo NAV_DISTANCE_FROM_START=; echo NAV_ESTIMATED_DISTANCE_REMAINING=; echo NAV_ESTIMATED_TIME_REMAINING_SEC=; echo NAV_ERROR=; "
        "fi"
    )


def navigation_error_probe_shell() -> str:
    return (
        f"NAV_ERRORS_PUBLISHERS=$({topic_publisher_count('/navigo/ea/cmn/intf/nav_errors', timeout=2)}); "
        "echo NAV_ERRORS_PUBLISHERS=$NAV_ERRORS_PUBLISHERS; "
        "if [ \"$NAV_ERRORS_PUBLISHERS\" -gt 0 ]; then "
        "NAV_ERRORS_MSG=$(timeout 2s ros2 topic echo --once /navigo/ea/cmn/intf/nav_errors --no-daemon 2>/dev/null || true); "
        "NAV_ERRORS_SUMMARY=$(printf '%s\\n' \"$NAV_ERRORS_MSG\" | sed '/^[[:space:]]*$/d' | head -20 | tr '\\n' ' ' | sed 's/[[:space:]][[:space:]]*/ /g' | cut -c1-240); "
        "else NAV_ERRORS_SUMMARY=; fi; "
        "echo NAV_ERRORS_SUMMARY=${NAV_ERRORS_SUMMARY:-}"
    )


def motion_velocity_sample_shell(topic: str, key: str) -> str:
    return probe_motion.motion_velocity_sample_shell(topic, key)


def motion_control_chain_probe_shell() -> str:
    return probe_motion.motion_control_chain_probe_shell()


def status_derivation_shell() -> str:
    return (
        "STATUS=; TEXT=; "
        "case \"${APP_NAV_STATUS:-}\" in "
        "Running|Active|Naving) STATUS=active; TEXT=\"$APP_NAV_STATUS\" ;; "
        "Succeeded) STATUS=success; TEXT=\"$APP_NAV_STATUS\" ;; "
        "Error|NavError|LocError|Failed) STATUS=error; TEXT=\"$APP_NAV_STATUS\" ;; "
        "Stopped|StandBy) STATUS=ready; TEXT=\"$APP_NAV_STATUS\" ;; "
        "esac; "
        "if [ -n \"$STATUS\" ]; then :; "
        "elif [ \"$MAP_OK\" != 1 ]; then STATUS=blocked; TEXT='地图缺失'; "
        "elif [ \"$NAV_PROCESS\" != 1 ] || [ \"$START_NAV_SUBSCRIBERS\" -lt 1 ]; then STATUS=blocked; TEXT='导航栈未就绪'; "
        "elif [ \"$LOCALIZATION_READY\" != 1 ]; then STATUS=blocked; TEXT='等待连续定位'; "
        "else STATUS=unknown; TEXT='等待 alg 状态'; "
        "fi; "
        "echo STATUS=$STATUS; echo TEXT=$TEXT"
    )


def probe_status_inner(
    profile: ProductProfile,
    map_pcd_path: str,
    *,
    skip_arc_app_status: bool = False,
    include_motion_chain: bool = True,
) -> str:
    arc_app_skip = "DOG_REMOTE_SKIP_ARC_APP_STATUS=1; export DOG_REMOTE_SKIP_ARC_APP_STATUS; " if skip_arc_app_status else ""
    motion_probe = motion_control_chain_probe_shell() if include_motion_chain else ""
    return (
        f"{remote_env(profile)}; "
        "source /opt/runtime/env.bash >/dev/null 2>&1 || true; "
        "source /opt/robot/robot_nav/install/setup.bash >/dev/null 2>&1 || true; "
        "source /opt/robot/robot_slam/install/setup.bash >/dev/null 2>&1 || true; "
        "SLAM_VERSION=$(dpkg-query -W -f='${Version}' robot-slam 2>/dev/null || true); echo SLAM_VERSION=${SLAM_VERSION:-unknown}; "
        "TOPIC_LIST=$(timeout 3s ros2 topic list --no-daemon 2>/dev/null || true); "
        f"MAP_PCD={quote(map_pcd_path)}; echo MAP_PCD=$MAP_PCD; "
        "[ -s \"$MAP_PCD\" ] && MAP_OK=1 || MAP_OK=0; echo MAP_OK=$MAP_OK; "
        "MAP_YAML=$(dirname \"$MAP_PCD\")/map.yaml; [ -s \"$MAP_YAML\" ] && MAP_YAML_OK=1 || MAP_YAML_OK=0; echo MAP_YAML=$MAP_YAML; echo MAP_YAML_OK=$MAP_YAML_OK; "
        "LOAD_MAP_SERVICE=; echo LOAD_MAP_SERVICE=$LOAD_MAP_SERVICE; "
        f"if {navigation_process_filter()} >/dev/null; then NAV_PROCESS=1; else NAV_PROCESS=0; fi; echo NAV_PROCESS=$NAV_PROCESS; "
        "if printf '%s\\n' \"$TOPIC_LIST\" | grep -Fx -- /start_navigation >/dev/null; then "
        f"START_NAV_SUBSCRIBERS=$( {topic_subscription_count('/start_navigation', timeout=2)} ); else START_NAV_SUBSCRIBERS=0; fi; echo START_NAV_SUBSCRIBERS=$START_NAV_SUBSCRIBERS; "
        f"{localization_state_probe_shell(profile, require_nav_accepted_status=True)}; "
        f"{topic_stamp_age_probe_shell('/laser_scan', 'LASER_SCAN')}; "
        f"{topic_stamp_age_probe_shell('/odom/current_pose', 'CURRENT_POSE')}; "
        f"{navigation_error_probe_shell()}; "
        f"{motion_probe}"
        f"{navigation_state_probe_shell()}; "
        f"{navigation_graph_status_probe_shell()}; "
        f"{arc_app_skip}"
        f"{mapping_arc_status.arc_status_snapshot_inner(profile)}; "
        f"{status_derivation_shell()}"
    )


def fast_probe_status_inner(profile: ProductProfile, map_pcd_path: str) -> str:
    return (
        f"{remote_env(profile)}; "
        "source /opt/runtime/env.bash >/dev/null 2>&1 || true; "
        "source /opt/robot/robot_nav/install/setup.bash >/dev/null 2>&1 || true; "
        "source /opt/robot/robot_slam/install/setup.bash >/dev/null 2>&1 || true; "
        "TOPIC_LIST=$(timeout 3s ros2 topic list --no-daemon 2>/dev/null || true); "
        f"MAP_PCD={quote(map_pcd_path)}; echo MAP_PCD=$MAP_PCD; "
        "[ -s \"$MAP_PCD\" ] && MAP_OK=1 || MAP_OK=0; echo MAP_OK=$MAP_OK; "
        "LOAD_MAP_SERVICE=; echo LOAD_MAP_SERVICE=$LOAD_MAP_SERVICE; "
        f"if {navigation_process_filter()} >/dev/null; then NAV_PROCESS=1; else NAV_PROCESS=0; fi; echo NAV_PROCESS=$NAV_PROCESS; "
        "if printf '%s\\n' \"$TOPIC_LIST\" | grep -Fx -- /start_navigation >/dev/null; then START_NAV_SUBSCRIBERS=1; else START_NAV_SUBSCRIBERS=0; fi; echo START_NAV_SUBSCRIBERS=$START_NAV_SUBSCRIBERS; "
        f"{fast_localization_state_probe_shell(profile)}; "
        f"{app_nav_status_probe_shell()}"
        f"{fast_navigation_state_probe_shell()}; "
        "DOG_REMOTE_SKIP_ARC_APP_STATUS=1; export DOG_REMOTE_SKIP_ARC_APP_STATUS; "
        "ARC_APP_CHANNEL=SKIPPED_BY_CALLER; echo ARC_APP_CHANNEL=$ARC_APP_CHANNEL; "
        f"{status_derivation_shell()}"
    )


def probe_status_command(
    profile: ProductProfile,
    map_pcd_path: str,
    *,
    skip_arc_app_status: bool = False,
    include_motion_chain: bool = True,
) -> str:
    return ssh_command(
        profile,
        probe_status_inner(
            profile,
            map_pcd_path,
            skip_arc_app_status=skip_arc_app_status,
            include_motion_chain=include_motion_chain,
        ),
    )


def fast_probe_status_command(profile: ProductProfile, map_pcd_path: str) -> str:
    return ssh_command(profile, fast_probe_status_inner(profile, map_pcd_path))


def status_command(profile: ProductProfile, map_pcd_path: str) -> CommandSpec:
    inner = (
        f"{remote_env(profile)}; "
        "source /opt/robot/robot_nav/install/setup.bash >/dev/null 2>&1 || true; "
        "source /opt/robot/robot_slam/install/setup.bash >/dev/null 2>&1 || true; "
        "echo '--- package versions ---'; "
        "for f in /opt/robot/robot_version_manager/navigation/version.yaml "
        "/opt/robot/robot_version_manager/robot-slam/version.yaml "
        "/opt/robot/robot_version_manager/robot-localization/version.yaml; do echo \"### $f\"; cat \"$f\" 2>/dev/null || true; done; "
        "echo '--- process ---'; "
        f"{navigation_process_filter()} || true; "
        "echo '--- topics ---'; "
        "timeout 5s ros2 topic list --no-daemon | grep -E 'start_navigation|navigation_state|navigation_cmd|localization_state|navigo|odom/current_pose' || true; "
        "echo '--- services ---'; "
        "timeout 5s ros2 service list --no-daemon | grep -E 'map_server|get_state|load_map|slam_state' || true; "
        "echo '--- structured status ---'; "
        f"{probe_status_inner(profile, map_pcd_path, skip_arc_app_status=True)}; "
        "echo '--- navigation log tail ---'; "
        f"tail -120 {quote(NAVIGATION_LOG)} 2>/dev/null || true"
    )
    return CommandSpec("解析导航包/状态", ssh_command(profile, inner), concurrency="parallel")
