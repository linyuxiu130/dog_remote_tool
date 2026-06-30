from __future__ import annotations

from dog_remote_tool.core.profiles import ProductProfile
from dog_remote_tool.core.shell import quote, remote_env, ssh_command
from dog_remote_tool.modules.arc_app_ws import common_arc_app_ws_python
from dog_remote_tool.modules.mapping.arc_common import ARC_DOCK_STATE_TEXT, ARC_STATE_TEXT, arc_runtime_profile


def arc_status_snapshot_inner(profile: ProductProfile) -> str:
    profile = arc_runtime_profile(profile)
    dock_cases = " ".join(f"{key}) echo {quote(value)} ;; " for key, value in ARC_DOCK_STATE_TEXT.items())
    arc_cases = " ".join(f"{key}) echo {quote(value)} ;; " for key, value in ARC_STATE_TEXT.items())
    app_status_python = common_arc_app_ws_python() + r'''
sock = connect_ws()
frame = 1
try:
    for func in ("get_arc_alg_status", "get_arc_dock_status"):
        resp, frame = request_once(sock, frame, func, wait_seconds=2, required=False, log_response=False)
        if resp is None:
            continue
        key = "ARC_APP_ALG_STATUS" if func == "get_arc_alg_status" else "ARC_APP_DOCK_STATUS"
        print(f"{key}={resp.get('data') or ''}", flush=True)
finally:
    try:
        send_close(sock)
    except Exception:
        pass
    try:
        sock.close()
    except Exception:
        pass
'''.strip()
    return (
        f"{remote_env(profile)}; "
        "source /opt/robot/robot_arc/install/setup.bash >/dev/null 2>&1 || true; "
        "dock_msg=$(timeout 2s ros2 topic echo --once /arc/dock_state --no-daemon 2>/dev/null || true); "
        "arc_msg=$(timeout 2s ros2 topic echo --once /arc/arc_state --no-daemon 2>/dev/null || true); "
        "dock_state=$(printf '%s\\n' \"$dock_msg\" | awk '/^state:/ {print $2; exit}'); "
        "dock_tag=$(printf '%s\\n' \"$dock_msg\" | awk '/^tag_id:/ {print $2; exit}'); "
        "dock_error=$(printf '%s\\n' \"$dock_msg\" | awk '/^error_code:/ {print $2; exit}'); "
        "dock_msg_text=$(printf '%s\\n' \"$dock_msg\" | sed -n 's/^error_msg:[[:space:]]*//p' | head -1 | sed \"s/^'//;s/'$//\"); "
        "arc_state=$(printf '%s\\n' \"$arc_msg\" | awk '/^state:/ {print $2; exit}'); "
        "arc_tag=$(printf '%s\\n' \"$arc_msg\" | awk '/^tag_id:/ {print $2; exit}'); "
        "dock_text=$(case \"$dock_state\" in " + dock_cases + "*) echo 未知 ;; esac); "
        "arc_text=$(case \"$arc_state\" in " + arc_cases + "*) echo 未知 ;; esac); "
        "echo ARC_DOCK_STATE=${dock_state:-}; "
        "echo ARC_DOCK_TEXT=${dock_text:-无数据}; "
        "echo ARC_DOCK_TAG=${dock_tag:-}; "
        "echo ARC_DOCK_ERROR=${dock_error:-}; "
        "echo ARC_DOCK_ERROR_MSG=${dock_msg_text:-}; "
        "echo ARC_STATE=${arc_state:-}; "
        "echo ARC_TEXT=${arc_text:-无数据}; "
        "echo ARC_TAG=${arc_tag:-}; "
        "nav_msg=$(timeout 1s ros2 topic echo --once /navigation_state --no-daemon 2>/dev/null || true); "
        "nav_state=$(printf '%s\\n' \"$nav_msg\" | awk '/^state:/ {print $2; exit}'); "
        "nav_task_status=$(printf '%s\\n' \"$nav_msg\" | awk '/task_status_list:/ {in_list=1; next} in_list && /^[[:space:]]*-[[:space:]]*task_status:/ {print $NF; exit} in_list && /task_status:/ {print $NF; exit} in_list && /^[^[:space:]]/ {in_list=0}'); "
        "[ -n \"$nav_task_status\" ] || nav_task_status=$(printf '%s\\n' \"$nav_msg\" | awk '/task_status:/ {print $NF; exit}'); "
        "nav_active=0; "
        "case \"$nav_state\" in 2|3|100|140|141) nav_active=1 ;; esac; "
        "case \"$nav_task_status\" in 1|2|3) nav_active=1 ;; esac; "
        "echo ARC_NAV_STATE=${nav_state:-}; "
        "echo ARC_NAV_TASK_STATUS=${nav_task_status:-}; "
        "dock_pose_msg=$(timeout 1s ros2 topic echo --once /arc/dock_pose --no-daemon 2>/dev/null || true); "
        "perception_pose_msg=$(timeout 1s ros2 topic echo --once /arc/perception_dock_pose --no-daemon 2>/dev/null || true); "
        "mapping_state_msg=$(timeout 1s ros2 topic echo --once /arc_mapping_state --no-daemon 2>/dev/null || true); "
        "dock_detected=0; "
        "if printf '%s\\n%s\\n' \"$dock_pose_msg\" \"$perception_pose_msg\" | grep -q 'current_pose:'; then dock_detected=1; fi; "
        "if printf '%s\\n' \"$mapping_state_msg\" | grep -Eq 'arc_detection_flag:[[:space:]]*(true|True|1)'; then dock_detected=1; fi; "
        "echo ARC_DOCK_DETECTED=$dock_detected; "
        "if [ \"${DOG_REMOTE_SKIP_ARC_APP_STATUS:-0}\" = 1 ]; then "
        "echo ARC_APP_CHANNEL=SKIPPED_BY_CALLER; "
        "elif [ \"$nav_active\" = 1 ]; then "
        "echo ARC_APP_CHANNEL=SKIPPED_NAV_ACTIVE; "
        "else "
        f"timeout 7s python3 -c {quote(app_status_python)} 2>/dev/null || true; "
        "fi"
    )


def arc_status_snapshot_command(profile: ProductProfile) -> str:
    runtime_profile = arc_runtime_profile(profile)
    inner = arc_status_snapshot_inner(runtime_profile)
    return ssh_command(runtime_profile, f"timeout 15s bash -lc {quote(inner)} || true")
