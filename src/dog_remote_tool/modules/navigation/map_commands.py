from __future__ import annotations

from dog_remote_tool.core.profiles import ProductProfile
from dog_remote_tool.core.quoting import yaml_string
from dog_remote_tool.core.shell import CommandSpec, echo_message, quote, remote_env, ssh_command
from dog_remote_tool.modules.navigation import map_localization
from dog_remote_tool.modules.navigation import probe as _probe
from dog_remote_tool.modules.navigation import route_network
from dog_remote_tool.modules.navigation.helper_commands import (
    _mode_switch_inner,
    _publish_start_navigation_payload_inner,
    _release_navigation_control_inner,
)
from dog_remote_tool.modules.navigation.payloads import _initialize_payload, _navigation_2d_map_path


NAVIGATION_IDLE_TERMINAL_STATES = "0|1|4|5|6|7|200|201|202"
NAVIGATION_MAP_LOCKS = ("navigation-map",)


def load_map_command(profile: ProductProfile, map_pcd_path: str) -> CommandSpec:
    nav_map_path = _navigation_2d_map_path(map_pcd_path)
    inner = (
        f"{remote_env(profile)}; "
        "source /opt/robot/robot_nav/install/setup.bash >/dev/null 2>&1 || true; "
        "source /opt/robot/robot_slam/install/setup.bash >/dev/null 2>&1 || true; "
        f"{_load_navigation_map_inner(profile, map_pcd_path)}"
        f"{_navigation_2d_map_gate_inner(map_pcd_path)}"
        f"{_publish_navigation_initialize_inner(nav_map_path, 1)}"
    )
    return CommandSpec(
        "加载导航地图",
        ssh_command(profile, inner),
        display_command="执行：加载导航地图",
        concurrency="parallel",
        locks=NAVIGATION_MAP_LOCKS,
    )


def prepare_map_command(profile: ProductProfile, map_pcd_path: str) -> CommandSpec:
    nav_map_path = _navigation_2d_map_path(map_pcd_path)
    inner = (
        "MAP_PREP_START_MS=$(date +%s%3N 2>/dev/null || echo 0); "
        f"{remote_env(profile)}; "
        "source /opt/robot/robot_nav/install/setup.bash >/dev/null 2>&1 || true; "
        "source /opt/robot/robot_slam/install/setup.bash >/dev/null 2>&1 || true; "
        f"{_load_navigation_map_inner(profile, map_pcd_path)}"
        f"{_navigation_2d_map_gate_inner(map_pcd_path)}"
        f"{_publish_navigation_initialize_inner(nav_map_path, 1)}"
        "echo MAP_PREP_NAV_READY=1; "
        "MAP_PREP_END_MS=$(date +%s%3N 2>/dev/null || echo 0); "
        "if [ \"$MAP_PREP_START_MS\" -gt 0 ] 2>/dev/null && [ \"$MAP_PREP_END_MS\" -ge \"$MAP_PREP_START_MS\" ] 2>/dev/null; then "
        "awk -v start=\"$MAP_PREP_START_MS\" -v end=\"$MAP_PREP_END_MS\" 'BEGIN {printf \"MAP_PREP_SECONDS=%.3f\\n\", (end-start)/1000}'; "
        "fi; "
        "echo '[INFO] 选中地图导航初始化已下发'; "
    )
    return CommandSpec(
        "准备导航地图",
        ssh_command(profile, inner),
        display_command="执行：准备导航地图",
        concurrency="parallel",
        locks=NAVIGATION_MAP_LOCKS,
    )


def _load_navigation_map_inner(profile: ProductProfile, map_pcd_path: str) -> str:
    return map_localization.load_navigation_map_inner(profile, map_pcd_path)


def _load_localization_map_once_inner(profile: ProductProfile, map_pcd_path: str, timeout_seconds: int = 45) -> str:
    return map_localization.load_localization_map_once_inner(profile, map_pcd_path, timeout_seconds)


def _navigation_2d_map_gate_inner(map_pcd_path: str) -> str:
    nav_map_path = _navigation_2d_map_path(map_pcd_path)
    if nav_map_path == map_pcd_path:
        return ""
    return (
        f"if [ ! -s {quote(nav_map_path)} ]; then "
        f"{echo_message(f'[ERROR] 导航地图文件不存在或为空: {nav_map_path}；请确认地图目录包含 map.yaml')}; "
        "exit 2; "
        "fi; "
        ""
    )


def _navigation_controller_defaults_inner() -> str:
    return (
        "timeout 0.6s ros2 param set /controller_server current_goal_checker general_goal_checker >/dev/null 2>&1 || true; "
        "timeout 0.6s ros2 param set /controller_server current_progress_checker progress_checker >/dev/null 2>&1 || true; "
    )


def _publish_navigation_initialize_inner(map_path: str, map_type: int = 1) -> str:
    payload = _initialize_payload(map_path, map_type)
    return (
        f"{_publish_start_navigation_payload_inner(payload, '[INFO] 地图初始化已发送', '[ERROR] 导航地图初始化命令发送失败')}"
    )


def _publish_navigation_task_inner(payload: str, success_message: str, failure_message: str, timeout_seconds: int = 4) -> str:
    return (
        f"{_navigation_controller_defaults_inner()}"
        f"{_publish_start_navigation_payload_inner(payload, success_message, failure_message, timeout_seconds)}"
    )


def _wait_navigation_active_after_start_inner(timeout_seconds: int = 22) -> str:
    return (
        "NAV_START_OK=0; NAV_START_FAILED=0; NAV_START_LAST_STATE=; NAV_START_LAST_TASK=; "
        "NAV_START_LAST_ERROR=; NAV_START_DEADLINE=$(( $(date +%s) + "
        f"{int(timeout_seconds)}"
        " )); "
        "while [ \"$(date +%s)\" -lt \"$NAV_START_DEADLINE\" ]; do "
        "NAV_START_MSG=$(timeout 2s ros2 topic echo --once /navigation_state --no-daemon 2>/dev/null || true); "
        "NAV_START_STATE=$(printf '%s\\n' \"$NAV_START_MSG\" | awk '/^state:/ {print $2; exit}'); "
        "NAV_START_TASK=$(printf '%s\\n' \"$NAV_START_MSG\" | awk -v idx=\"${NAV_START_CURRENT_TASK_IDX:-0}\" '"
        "BEGIN {in_list=0; current=-1} "
        "/^current_task_idx:/ {idx=$2} "
        "/^task_status_list:/ {in_list=1; next} "
        "in_list && /^-/ {current++} "
        "in_list && /task_status:/ {if (current < 0) current=0; if (current == idx) {print $NF; exit}} "
        "in_list && /^[^[:space:]-]/ {in_list=0}'"
        "); "
        "[ -n \"$NAV_START_TASK\" ] || NAV_START_TASK=$(printf '%s\\n' \"$NAV_START_MSG\" | awk '/task_status:/ {print $NF; exit}'); "
        "NAV_START_ERROR=$(printf '%s\\n' \"$NAV_START_MSG\" | sed -n 's/^[[:space:]]*message:[[:space:]]*//p' | head -1 | sed \"s/^'//;s/'$//\"); "
        "if [ -n \"$NAV_START_STATE\" ]; then NAV_START_LAST_STATE=\"$NAV_START_STATE\"; fi; "
        "if [ -n \"$NAV_START_TASK\" ]; then NAV_START_LAST_TASK=\"$NAV_START_TASK\"; fi; "
        "if [ -n \"$NAV_START_ERROR\" ]; then NAV_START_LAST_ERROR=\"$NAV_START_ERROR\"; fi; "
        "case \"$NAV_START_TASK\" in 2|3|5) NAV_START_OK=1; break ;; 6) NAV_START_FAILED=1; break ;; esac; "
        "case \"$NAV_START_STATE\" in 2|100|200) NAV_START_OK=1; break ;; 4|6|201|202) NAV_START_FAILED=1; break ;; esac; "
        "sleep 0.5; "
        "done; "
        "if [ \"$NAV_START_OK\" = 1 ]; then "
        "echo '[INFO] 导航任务已开始'; "
        "else "
        "if [ \"$NAV_START_FAILED\" = 1 ]; then "
        "echo '[ERROR] 导航目标指令已提交，但任务进入失败状态：state='\"${NAV_START_LAST_STATE:---}\"' task='\"${NAV_START_LAST_TASK:---}\"' error='\"${NAV_START_LAST_ERROR:---}\"; "
        "else "
        "echo '[ERROR] 导航目标指令已提交，但未观察到进入执行状态：state='\"${NAV_START_LAST_STATE:---}\"' task='\"${NAV_START_LAST_TASK:---}\"' error='\"${NAV_START_LAST_ERROR:---}\"; "
        "fi; "
        f"{_release_navigation_control_inner()}"
        "exit 10; "
        "fi; "
    )


def _pre_start_navigation_mode_inner() -> str:
    return _mode_switch_inner(True)


def _navigation_standby_probe_python(timeout_seconds: int) -> str:
    script = f"""import subprocess
import time

def emit(key, value):
    print(f"{{key}}={{value}}", flush=True)

try:
    import rclpy
    from robots_dog_msgs.msg import NavigationState

    def nav_version():
        try:
            return subprocess.check_output(
                ["dpkg-query", "-W", "-f=${{Version}}", "navigation"],
                text=True,
                stderr=subprocess.DEVNULL,
                timeout=1,
            ).strip()
        except Exception:
            return ""

    def const_text(name):
        value = getattr(NavigationState, name, "")
        return str(value) if value != "" else ""

    version = nav_version()
    is_nav_070 = version.startswith("0.7.0")
    if is_nav_070:
        standby_states = {{"0"}}
        failed_states = {{"6", "202"}}
    else:
        standby_states = {{const_text("STATE_STANDBY"), "0", "1", "7"}}
        failed_states = {{const_text("STATE_FAILED"), "6", "202"}}
    standby_states.discard("")
    failed_states.discard("")
    active_task_statuses = {{"1", "2", "3"}}

    state = {{"value": "", "task": "", "done": False}}

    def current_task_status(msg):
        tasks = getattr(msg, "task_status_list", None) or []
        if not tasks:
            return ""
        try:
            idx = int(getattr(msg, "current_task_idx", 0) or 0)
        except Exception:
            idx = 0
        if idx < 0 or idx >= len(tasks):
            idx = 0
        return str(getattr(tasks[idx], "task_status", "") or "")

    def on_message(msg):
        nav_state = str(getattr(msg, "state", "") or "")
        task_status = current_task_status(msg)
        state["value"] = nav_state
        state["task"] = task_status
        task_active = task_status in active_task_statuses
        if (nav_state in standby_states and not task_active) or nav_state in failed_states or task_status == "6":
            state["done"] = True

    rclpy.init()
    node = rclpy.create_node("dog_remote_nav_standby_wait")
    node.create_subscription(NavigationState, "/navigation_state", on_message, 10)
    deadline = time.monotonic() + {int(timeout_seconds)}
    while time.monotonic() < deadline and not state["done"]:
        rclpy.spin_once(node, timeout_sec=0.2)
    emit("NAV_STANDBY_STATE", state["value"])
    emit("NAV_STANDBY_TASK", state["task"])
    node.destroy_node()
    rclpy.shutdown()
except Exception as exc:
    emit("NAV_STANDBY_ERROR", f"{{type(exc).__name__}}: {{exc}}")
    emit("NAV_STANDBY_STATE", "")
    emit("NAV_STANDBY_TASK", "")
"""
    return f"timeout {int(timeout_seconds) + 3}s python3 -c {quote(script)}"


def _wait_navigation_standby_after_initialize_inner(
    timeout_seconds: int = 10,
    settle_seconds: float = 0.8,
    allow_unknown: bool = False,
    allow_active_initializing: bool = False,
    allow_initialize_succeeded: bool = False,
) -> str:
    allow_unknown_value = "1" if allow_unknown else "0"
    allow_active_initializing_value = "1" if allow_active_initializing else "0"
    allow_initialize_succeeded_value = "1" if allow_initialize_succeeded else "0"
    return (
        f"sleep {settle_seconds:.1f}; "
        f"NAV_STANDBY_ALLOW_UNKNOWN={allow_unknown_value}; "
        f"NAV_STANDBY_ALLOW_ACTIVE_INITIALIZING={allow_active_initializing_value}; "
        f"NAV_STANDBY_ALLOW_INITIALIZE_SUCCEEDED={allow_initialize_succeeded_value}; "
        "NAV_STANDBY_OK=0; NAV_STANDBY_LAST_STATE=; NAV_STANDBY_LAST_TASK=; "
        "NAV_VERSION=$(dpkg-query -W -f='${Version}' navigation 2>/dev/null || true); "
        f"NAV_STANDBY_PROBE=$({_navigation_standby_probe_python(timeout_seconds)} 2>/dev/null || true); "
        "NAV_STANDBY_STATE=$(printf '%s\\n' \"$NAV_STANDBY_PROBE\" | awk -F= '/^NAV_STANDBY_STATE=/ {print substr($0, index($0, \"=\") + 1); exit}'); "
        "NAV_STANDBY_TASK=$(printf '%s\\n' \"$NAV_STANDBY_PROBE\" | awk -F= '/^NAV_STANDBY_TASK=/ {print substr($0, index($0, \"=\") + 1); exit}'); "
        "NAV_STANDBY_ERROR=$(printf '%s\\n' \"$NAV_STANDBY_PROBE\" | awk -F= '/^NAV_STANDBY_ERROR=/ {print substr($0, index($0, \"=\") + 1); exit}'); "
        "if [ -n \"$NAV_STANDBY_ERROR\" ]; then echo '[WARN] rclpy 读取 /navigation_state 失败，回退 ros2 topic echo：'\"$NAV_STANDBY_ERROR\"; fi; "
        "if [ -z \"$NAV_STANDBY_STATE\" ]; then "
        "NAV_STANDBY_MSG=$(timeout 3s ros2 topic echo --once /navigation_state --no-daemon 2>/dev/null || true); "
        "NAV_STANDBY_STATE=$(printf '%s\\n' \"$NAV_STANDBY_MSG\" | awk '/^state:/ {print $2; exit}'); "
        "NAV_STANDBY_TASK=$(printf '%s\\n' \"$NAV_STANDBY_MSG\" | awk '/task_status_list:/ {in_list=1; next} in_list && /^[[:space:]]*-[[:space:]]*task_status:/ {print $NF; exit} in_list && /task_status:/ {print $NF; exit} in_list && /^[^[:space:]]/ {in_list=0}'); "
        "fi; "
        "if [ -n \"$NAV_STANDBY_STATE\" ]; then NAV_STANDBY_LAST_STATE=\"$NAV_STANDBY_STATE\"; fi; "
        "if [ -n \"$NAV_STANDBY_TASK\" ]; then NAV_STANDBY_LAST_TASK=\"$NAV_STANDBY_TASK\"; fi; "
        "case \"$NAV_STANDBY_TASK\" in 1|2|3) NAV_STANDBY_TASK_ACTIVE=1 ;; *) NAV_STANDBY_TASK_ACTIVE=0 ;; esac; "
        "case \"$NAV_VERSION\" in 0.7.0*) "
        "if [ \"$NAV_STANDBY_STATE\" = 0 ] && [ \"$NAV_STANDBY_TASK_ACTIVE\" != 1 ]; then NAV_STANDBY_OK=1; fi ;; "
        "*) "
        "case \"$NAV_STANDBY_STATE\" in 0|1|7) "
        "if [ \"$NAV_STANDBY_TASK_ACTIVE\" != 1 ]; then NAV_STANDBY_OK=1; fi ;; "
        "esac ;; "
        "esac; "
        "if [ \"$NAV_STANDBY_OK\" != 1 ] && [ \"$NAV_STANDBY_ALLOW_UNKNOWN\" = 1 ] "
        "&& [ -z \"$NAV_STANDBY_LAST_STATE\" ] && [ -z \"$NAV_STANDBY_LAST_TASK\" ]; then "
        "echo '[WARN] 导航状态未及时回读，继续发送目标'; "
        "NAV_STANDBY_OK=1; "
        "fi; "
        "if [ \"$NAV_STANDBY_OK\" != 1 ] && [ \"$NAV_STANDBY_ALLOW_ACTIVE_INITIALIZING\" = 1 ] "
        "&& [ \"$NAV_STANDBY_LAST_STATE\" = 100 ] && [ \"$NAV_STANDBY_LAST_TASK\" = 2 ]; then "
        "echo '[WARN] 导航仍在初始化，继续发送路网目标'; "
        "NAV_STANDBY_OK=1; "
        "fi; "
        "if [ \"$NAV_STANDBY_OK\" != 1 ] && [ \"$NAV_STANDBY_ALLOW_INITIALIZE_SUCCEEDED\" = 1 ] "
        "&& [ \"$NAV_STANDBY_LAST_STATE\" = 200 ] && [ \"$NAV_STANDBY_TASK_ACTIVE\" != 1 ]; then "
        "echo '[INFO] 路网初始化已成功，继续发送目标'; "
        "NAV_STANDBY_OK=1; "
        "fi; "
        "if [ \"$NAV_STANDBY_OK\" != 1 ]; then "
        "echo '[ERROR] 导航初始化后未回到 STANDBY，取消发送目标：state='\"${NAV_STANDBY_LAST_STATE:---}\"' task='\"${NAV_STANDBY_LAST_TASK:---}\"; "
        "exit 9; "
        "fi; "
        "echo '[INFO] 导航已就绪，可发送目标'; "
    )


def _fast_navigation_header(profile: ProductProfile) -> str:
    return (
        f"{remote_env(profile)}; "
        "source /opt/robot/robot_nav/install/setup.bash >/dev/null 2>&1 || true; "
    )


def _update_route_graph_inner(route_geojson_path: str) -> str:
    payload = "{filepath: " + yaml_string(route_geojson_path) + "}"
    service = route_network.UPDATE_GRAPH_SERVICE
    service_type = route_network.UPDATE_GRAPH_TYPE
    return (
        "DOG_REMOTE_ROUTE_GRAPH_CACHE=/tmp/dog_remote_route_graph_cache; "
        f"ROUTE_GRAPH_FILE={quote(route_geojson_path)}; "
        "ROUTE_GRAPH_STAT=$(stat -c '%n|%s|%Y' \"$ROUTE_GRAPH_FILE\" 2>/dev/null || true); "
        "ROUTE_GRAPH_NAV_CONTAINER_PID=$(ps -eo pid=,comm=,args= 2>/dev/null | "
        "awk '$2 ~ /^component_conta/ && $0 ~ /nav2_container/ {print $1}' | tr '\n' ',' || true); "
        "ROUTE_GRAPH_NAV_LAUNCH_PID=$(ps -eo pid=,comm=,args= 2>/dev/null | "
        "awk '$2==\"ros2\" && $0 ~ /navigation_bringup[.]launch[.]py/ {print $1}' | tr '\n' ',' || true); "
        "ROUTE_GRAPH_CACHE_KEY=\"$ROUTE_GRAPH_STAT|nav_pid=$ROUTE_GRAPH_NAV_CONTAINER_PID$ROUTE_GRAPH_NAV_LAUNCH_PID\"; "
        "ROUTE_GRAPH_CACHED_KEY=$(cat \"$DOG_REMOTE_ROUTE_GRAPH_CACHE\" 2>/dev/null || true); "
        "if [ -n \"$ROUTE_GRAPH_STAT\" ] && [ -n \"$ROUTE_GRAPH_NAV_CONTAINER_PID\" ] && [ \"$ROUTE_GRAPH_CACHE_KEY\" = \"$ROUTE_GRAPH_CACHED_KEY\" ]; then "
        "echo '[INFO] 路网未变化，跳过重复更新'; "
        "else "
        f"if [ -z \"$ROUTE_GRAPH_NAV_CONTAINER_PID\" ]; then echo '[ERROR] 路网更新服务未就绪: {service}；导航栈未运行，请等待恢复后重试'; exit 3; fi; "
        f"{echo_message(f'[INFO] 正在更新路网: {route_geojson_path}')}; "
        f"ROUTE_GRAPH_RSP=$(timeout 12s ros2 service call {quote(service)} {quote(service_type)} {quote(payload)} 2>&1); "
        "ROUTE_GRAPH_RC=$?; "
        "printf '%s\n' \"$ROUTE_GRAPH_RSP\" | sed -n '1,12p'; "
        "if [ \"$ROUTE_GRAPH_RC\" -ne 0 ]; then "
        f"if printf '%s\n' \"$ROUTE_GRAPH_RSP\" | grep -Eqi 'context is invalid|failed to check service availability|service .*not available|timed out'; then "
        f"echo '[ERROR] 路网更新服务未就绪: {service}；请等待导航栈恢复后重试'; "
        "else "
        "echo '[ERROR] 路网更新失败，已取消下发目标'; "
        "fi; "
        "exit 3; "
        "fi; "
        "if ! printf '%s\n' \"$ROUTE_GRAPH_RSP\" | grep -Eq 'success[=:][[:space:]]*(True|true)'; then "
        "echo '[ERROR] 路网未确认加载成功，已取消下发目标'; exit 3; "
        "fi; "
        "printf '%s\n' \"$ROUTE_GRAPH_CACHE_KEY\" > \"$DOG_REMOTE_ROUTE_GRAPH_CACHE\" 2>/dev/null || true; "
        "echo '[INFO] 路网已更新'; "
        "fi; "
    )


def _clear_busy_navigation_before_goal_inner() -> str:
    terminal_states = NAVIGATION_IDLE_TERMINAL_STATES
    return (
        f"NAV_STATE_PUBLISHERS=$({_probe.topic_publisher_count('/navigation_state', timeout=0.5)}); "
        "if [ \"$NAV_STATE_PUBLISHERS\" -gt 0 ]; then "
        "NAV_PRE_MSG=$(timeout 2s ros2 topic echo --once /navigation_state --no-daemon 2>/dev/null || true); "
        "else NAV_PRE_MSG=; fi; "
        "NAV_PRE_STATE=$(printf '%s\\n' \"$NAV_PRE_MSG\" | awk '/^state:/ {print $2; exit}'); "
        "NAV_PRE_TASK_STATUS=$(printf '%s\\n' \"$NAV_PRE_MSG\" | awk '/task_status_list:/ {in_list=1; next} in_list && /^[[:space:]]*-[[:space:]]*task_status:/ {print $NF; exit} in_list && /task_status:/ {print $NF; exit} in_list && /^[^[:space:]]/ {in_list=0}'); "
        "NAV_PRE_SUBSTATE=$(printf '%s\\n' \"$NAV_PRE_MSG\" | awk '/^active_substate:/ {print $2; exit}'); "
        "NAV_PRE_REMAINING=$(printf '%s\\n' \"$NAV_PRE_MSG\" | awk '/^estimated_distance_remaining:/ {print $2; exit}'); "
        "case \"$NAV_PRE_TASK_STATUS\" in 1|2|3) NAV_PRE_TASK_ACTIVE=1 ;; *) NAV_PRE_TASK_ACTIVE=0 ;; esac; "
        "NAV_PRE_NEEDS_CLEAR=0; "
        "case \"${NAV_PRE_STATE:-0}\" in "
        f"{terminal_states}) if [ \"$NAV_PRE_TASK_ACTIVE\" = 1 ]; then NAV_PRE_NEEDS_CLEAR=1; fi ;; "
        "*) NAV_PRE_NEEDS_CLEAR=1 ;; "
        "esac; "
        "if [ \"$NAV_PRE_NEEDS_CLEAR\" = 1 ]; then "
        "echo '[WARN] 上一导航仍未结束，先停止后再发送新目标'; "
        f"{_release_navigation_control_inner()}"
        "NAV_CLEAR=0; NAV_CLEAR_LAST_STATE=\"$NAV_PRE_STATE\"; NAV_CLEAR_LAST_TASK=\"$NAV_PRE_TASK_STATUS\"; "
        "for _clear_i in 1 2 3 4 5 6; do "
        "sleep 0.4; "
        "NAV_CLEAR_MSG=$(timeout 1s ros2 topic echo --once /navigation_state --no-daemon 2>/dev/null || true); "
        "NAV_CLEAR_STATE=$(printf '%s\\n' \"$NAV_CLEAR_MSG\" | awk '/^state:/ {print $2; exit}'); "
        "NAV_CLEAR_TASK_STATUS=$(printf '%s\\n' \"$NAV_CLEAR_MSG\" | awk '/task_status_list:/ {in_list=1; next} in_list && /^[[:space:]]*-[[:space:]]*task_status:/ {print $NF; exit} in_list && /task_status:/ {print $NF; exit} in_list && /^[^[:space:]]/ {in_list=0}'); "
        "if [ -n \"$NAV_CLEAR_STATE\" ]; then NAV_CLEAR_LAST_STATE=\"$NAV_CLEAR_STATE\"; fi; "
        "if [ -n \"$NAV_CLEAR_TASK_STATUS\" ]; then NAV_CLEAR_LAST_TASK=\"$NAV_CLEAR_TASK_STATUS\"; fi; "
        "case \"$NAV_CLEAR_TASK_STATUS\" in 1|2|3) NAV_CLEAR_TASK_ACTIVE=1 ;; *) NAV_CLEAR_TASK_ACTIVE=0 ;; esac; "
        "case \"$NAV_CLEAR_STATE\" in "
        f"{terminal_states}) if [ \"$NAV_CLEAR_TASK_ACTIVE\" != 1 ]; then NAV_CLEAR=1; break; fi ;; "
        "esac; "
        "done; "
        "if [ \"$NAV_CLEAR\" != 1 ]; then "
        "echo '[ERROR] 上一导航停止后仍未退出执行状态，暂不发送新目标：last_state='\"${NAV_CLEAR_LAST_STATE:---}\"' task='\"${NAV_CLEAR_LAST_TASK:---}\"; "
        "exit 8; "
        "fi; "
        "echo '[INFO] 上一导航已停止，继续发送新目标'; "
        "fi; "
    )
