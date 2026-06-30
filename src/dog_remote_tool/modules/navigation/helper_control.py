from __future__ import annotations

from dog_remote_tool.core.shell import quote
from dog_remote_tool.modules.body_navigation_bridge import (
    body_navigation_bridge_profile as _body_navigation_bridge_profile,
)
from dog_remote_tool.modules.body_navigation_bridge import (
    ensure_body_navigation_bridge_command as _ensure_body_navigation_bridge_command,
)
from dog_remote_tool.modules.body_navigation_bridge import (
    navigation_start_ssh_command as _navigation_start_ssh_command,
)
from dog_remote_tool.modules.arc_app_ws import common_arc_app_ws_python
from dog_remote_tool.modules.navigation.helper_scripts import (
    MODE_SWITCH_STATE_PID,
    MODE_SWITCH_TOPIC,
)


# 201 can appear while the navigation BT is still waiting/recovering after a
# blocked route. Only the pre-start cleanup treats it as idle; the background
# release watcher must not turn that intermediate state into a cancellation.
NAVIGATION_RELEASE_TERMINAL_STATES = "0|1|4|5|6|7|200|202"
NAVIGATION_LOOP_PID = "/tmp/dog_remote_nav_loop.pid"
NAVIGATION_LOOP_LOG = "/tmp/dog_remote_nav_loop.log"


def _app_ws_request_python() -> str:
    return common_arc_app_ws_python() + "\n" + r'''
def connect():
    return AppWsBrokerClient()

def request(client, frame, func, value=None, wait=3.0, aliases=()):
    expected = {func, *aliases}
    req_func = func if value is None else {func: value}
    obj = {"head": {"type": "app_req", "time_stamp": int(time.time() * 1000), "source": "app", "frame_count": frame}, "data": {"req_func": req_func}}
    messages = client.request(obj, "", wait)
    for msg in messages:
        parsed = parse_app_response(msg)
        if not isinstance(parsed, dict) or parsed.get("kind") != "app_resp":
            continue
        if parsed.get("func") in expected:
            if parsed.get("status") not in (None, "ok"):
                raise RuntimeError(parsed)
            return parsed
    raise TimeoutError(func)
'''.strip()


def _current_task_status_awk(message_var: str = "NAV_MSG", idx_var: str = "NAV_CURRENT_TASK_IDX") -> str:
    return (
        f"printf '%s\\n' \"${message_var}\" | awk -v idx=\"${{{idx_var}:-0}}\" '"
        "BEGIN {in_list=0; current=-1} "
        "/^task_status_list:/ {in_list=1; next} "
        "in_list && /^-/ {current++} "
        "in_list && /task_status:/ {if (current < 0) current=0; if (current == idx) {print $NF; exit}} "
        "in_list && /^[^[:space:]-]/ {in_list=0}'"
    )


def _body_navigation_right_inner(enabled: bool, timeout_seconds: float = 1.2) -> str:
    cmd = 180 if enabled else 170
    action = "申请" if enabled else "释放"
    python = f"""
import json
import os
import socket
import time

host = os.environ.get("DOG_REMOTE_BODY_NAV_HOST", "192.168.234.1")
port = int(os.environ.get("DOG_REMOTE_BODY_NAV_PORT", "8081"))
local_port = int(os.environ.get("DOG_REMOTE_BODY_NAV_LOCAL_PORT", "8080"))
target = (host, port)
heartbeat = {{"role": "remote", "type": "heartbeat"}}
command = {{"cmd": {cmd}, "type": "cmd"}}

sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
sock.settimeout(0.2)
try:
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
except Exception:
    pass
try:
    sock.bind(("", local_port))
    source = str(local_port)
except OSError as exc:
    sock.bind(("", 0))
    source = f"random({{exc}})"

def send(payload):
    body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    sock.sendto(body, target)

send(heartbeat)
time.sleep(0.05)
send(command)
deadline = time.monotonic() + 0.45
while time.monotonic() < deadline:
    time.sleep(0.10)
    send(heartbeat)
sock.close()
""".strip()
    return (
        f"timeout {timeout_seconds:.1f}s python3 -c {quote(python)} || "
        f"echo '[WARN] body UDP 导航控制权发送失败或超时: cmd={cmd}'; "
    )


def _stop_navigation_loop_inner() -> str:
    return (
        f"NAV_LOOP_PID_FILE={quote(NAVIGATION_LOOP_PID)}; "
        f"NAV_LOOP_LOG={quote(NAVIGATION_LOOP_LOG)}; "
        "NAV_LOOP_PID=$(cat \"$NAV_LOOP_PID_FILE\" 2>/dev/null || true); "
        "if [ -n \"$NAV_LOOP_PID\" ] && kill -0 \"$NAV_LOOP_PID\" 2>/dev/null; then "
        "echo '[INFO] 已停止远端导航循环任务'; "
        "kill \"$NAV_LOOP_PID\" 2>/dev/null || true; sleep 0.3; "
        "if kill -0 \"$NAV_LOOP_PID\" 2>/dev/null; then kill -9 \"$NAV_LOOP_PID\" 2>/dev/null || true; fi; "
        "else "
        "true; "
        "fi; "
        "rm -f \"$NAV_LOOP_PID_FILE\" 2>/dev/null || true; "
    )


def _mode_switch_inner(enabled: bool, timeout_seconds: float | None = None) -> str:
    if timeout_seconds is None:
        timeout_seconds = 0.8 if enabled else 0.3
    value = "true" if enabled else "false"
    payload = "{data: " + value + "}"
    control_pid = quote(MODE_SWITCH_STATE_PID)
    state_start = (
        f"OLD_NAV_CONTROL_PID=$(cat {control_pid} 2>/dev/null || true); "
        "if [ -n \"$OLD_NAV_CONTROL_PID\" ] && kill -0 \"$OLD_NAV_CONTROL_PID\" 2>/dev/null; then true; else "
        f"nohup ros2 topic pub -r 10 {quote(MODE_SWITCH_TOPIC)} std_msgs/msg/Bool {quote(payload)} "
        ">/tmp/dog_remote_nav_control_state_pub.log 2>&1 & "
        f"echo $! > {control_pid}; "
        "fi; "
    )
    state_stop = (
        f"OLD_NAV_CONTROL_PID=$(cat {control_pid} 2>/dev/null || true); "
        "if [ -n \"$OLD_NAV_CONTROL_PID\" ]; then kill \"$OLD_NAV_CONTROL_PID\" 2>/dev/null || true; fi; "
        f"rm -f {control_pid}; "
        f"timeout {timeout_seconds:.2f}s ros2 topic pub -r 20 {quote(MODE_SWITCH_TOPIC)} std_msgs/msg/Bool {quote(payload)} >/dev/null 2>&1 || true; "
    )
    return (state_start if enabled else state_stop) + _body_navigation_right_inner(enabled)


def _alg_manager_stop_nav_inner(timeout_seconds: float = 3.0, fail_on_error: bool = False) -> str:
    python = _app_ws_request_python() + "\n" + r'''
alg_client = connect()
try:
    request(alg_client, 1, "stop_nav", wait=2)
    print("[INFO] 已提交停止导航请求")
finally:
    alg_client.close()
'''.strip()
    failure_cmd = "exit 7" if fail_on_error else "true"
    return (
        "if ps -eo args= 2>/dev/null | grep -E -- '(^|[ /])robot_alg_manager([[:space:]]|$)' | grep -v grep >/dev/null; then "
        f"if timeout {timeout_seconds:.1f}s python3 -c {quote(python)}; then "
        "NAV_ALG_RELEASE_OK=1; "
        "else "
        f"NAV_ALG_RELEASE_OK=0; {failure_cmd}; "
        "fi; "
        "else true; "
        "fi; "
    )


def _alg_manager_nav_request_inner(func: str, timeout_seconds: float = 3.0, fail_on_error: bool = False) -> str:
    python = _app_ws_request_python() + "\n" + r'''
FUNC = sys.argv[1]
client = connect()
try:
    request(client, 1, FUNC, wait=2)
finally:
    client.close()
'''.strip()
    failure_cmd = "exit 7" if fail_on_error else "true"
    return (
        f"timeout {timeout_seconds:.1f}s python3 -c {quote(python)} {quote(func)} || {failure_cmd}; "
    )


def _alg_manager_control_owner_inner(owner: str, timeout_seconds: float = 2.0) -> str:
    python = _app_ws_request_python() + "\n" + r'''
OWNER = sys.argv[1]
client = connect()
try:
    request(client, 1, "change_control_right_to", {"owner": OWNER}, wait=2)
finally:
    client.close()
'''.strip()
    return (
        "if ps -eo args= 2>/dev/null | grep -E -- '(^|[ /])robot_alg_manager([[:space:]]|$)' | grep -v grep >/dev/null; then "
        f"timeout {timeout_seconds:.1f}s python3 -c {quote(python)} {quote(owner)} || true; "
        "else true; "
        "fi; "
    )


def _release_navigation_control_inner(
    fail_on_error: bool = False,
    *,
    alg_timeout_seconds: float = 3.0,
    mode_timeout_seconds: float = 0.3,
) -> str:
    failure_exit = "if [ \"${NAV_RELEASE_FAILED:-0}\" = 1 ]; then exit 7; fi; " if fail_on_error else ""
    return (
        "NAV_RELEASE_FAILED=0; "
        "NAV_ALG_RELEASE_OK=0; "
        f"{_alg_manager_stop_nav_inner(timeout_seconds=alg_timeout_seconds, fail_on_error=False)}"
        "if [ \"$NAV_ALG_RELEASE_OK\" = 1 ]; then "
        "echo '[INFO] 停止导航请求已确认'; "
        "else "
        "NAV_RELEASE_FAILED=1; "
        "fi; "
        f"{_mode_switch_inner(False, mode_timeout_seconds)}"
        f"{_alg_manager_control_owner_inner('app', timeout_seconds=1.0)}"
        f"{failure_exit}"
    )


def _release_navigation_control_when_done_inner(
    timeout_seconds: int = 300,
    *,
    stop_navigation: bool = True,
    release_app_owner: bool = True,
) -> str:
    terminal_states = NAVIGATION_RELEASE_TERMINAL_STATES
    release_log = "/tmp/dog_remote_nav_release_watch.log"
    release_body_control = _mode_switch_inner(False, 0.2)
    stop_nav = _alg_manager_stop_nav_inner(timeout_seconds=1.5, fail_on_error=False) if stop_navigation else ""
    release_owner = _alg_manager_control_owner_inner("app", timeout_seconds=1.0) if release_app_owner else ""
    stop_after_success = (
        "printf '[%s] release terminal detected state=%s task=%s remaining=%s\\n' "
        "\"$(date '+%F %T')\" \"${NAV_STATE:---}\" \"${NAV_TASK_STATUS:---}\" \"${NAV_REMAINING:---}\"; "
        f"{stop_nav}"
        f"{release_body_control}"
        f"{release_owner}"
    )
    watcher = (
        "if [ -f /opt/runtime/env.bash ]; then source /opt/runtime/env.bash >/dev/null 2>&1 || true; fi; "
        "source /opt/robot/robot_nav/install/setup.bash >/dev/null 2>&1 || true; "
        "WATCH_START_TS=$(date +%s); "
        "printf '[%s] release watcher started pid=%s timeout=%s\\n' \"$(date '+%F %T')\" \"$$\" "
        f"{quote(str(timeout_seconds))}; "
        "SEEN_NAV_ACTIVE=0; "
        "NAV_REACHED_COUNT=0; "
        "while true; do "
        "NAV_MSG=$(timeout 2s ros2 topic echo --once /navigation_state --no-daemon 2>/dev/null || true); "
        "NAV_STATE=$(printf '%s\\n' \"$NAV_MSG\" | awk '/^state:/ {print $2; exit}'); "
        "NAV_CURRENT_TASK_IDX=$(printf '%s\\n' \"$NAV_MSG\" | awk '/^current_task_idx:/ {print $2; exit}'); "
        f"NAV_TASK_STATUS=$({_current_task_status_awk()}); "
        "[ -n \"$NAV_TASK_STATUS\" ] || NAV_TASK_STATUS=$(printf '%s\\n' \"$NAV_MSG\" | awk '/task_status:/ {print $NF; exit}'); "
        "NAV_REMAINING=$(printf '%s\\n' \"$NAV_MSG\" | awk '/^estimated_distance_remaining:/ {print $2; exit}'); "
        "NAV_TASK_STATUS_LIST=$(printf '%s\\n' \"$NAV_MSG\" | awk '/^task_status_list:/ {in_list=1; next} in_list && /^[[:space:]]*-[[:space:]]*task_status:/ {print $NF; next} in_list && /task_status:/ {print $NF; next} in_list && /^[^[:space:]-]/ {in_list=0}'); "
        "case \"$NAV_STATE\" in 2|3|100|140|141) SEEN_NAV_ACTIVE=1 ;; esac; "
        "case \"$NAV_TASK_STATUS\" in 1|2|3) SEEN_NAV_ACTIVE=1 ;; esac; "
        "case \"$NAV_TASK_STATUS\" in 1|2|3) NAV_TASK_ACTIVE=1 ;; *) NAV_TASK_ACTIVE=0 ;; esac; "
        "NAV_TASK_COUNT=$(printf '%s\\n' \"$NAV_TASK_STATUS_LIST\" | awk 'NF {count++} END {print count+0}'); "
        "NAV_TASK_RUNNING_COUNT=$(printf '%s\\n' \"$NAV_TASK_STATUS_LIST\" | awk '$1 ~ /^(1|2|3)$/ {count++} END {print count+0}'); "
        "NAV_TASK_PENDING_COUNT=$(printf '%s\\n' \"$NAV_TASK_STATUS_LIST\" | awk '$1 == 0 {count++} END {print count+0}'); "
        "NAV_TASK_TERMINAL_COUNT=$(printf '%s\\n' \"$NAV_TASK_STATUS_LIST\" | awk '$1 ~ /^(4|5|6)$/ {count++} END {print count+0}'); "
        "NAV_TASK_SUCCEEDED_COUNT=$(printf '%s\\n' \"$NAV_TASK_STATUS_LIST\" | awk '$1 == 5 {count++} END {print count+0}'); "
        "NAV_ALL_TASKS_TERMINAL=0; "
        "if [ \"$NAV_TASK_COUNT\" -gt 0 ] && [ \"$NAV_TASK_TERMINAL_COUNT\" -eq \"$NAV_TASK_COUNT\" ]; then NAV_ALL_TASKS_TERMINAL=1; fi; "
        "NAV_FAST_TERMINAL=0; "
        "case \"$NAV_STATE:$NAV_TASK_STATUS\" in 5:*|200:*|*:5) NAV_FAST_TERMINAL=1 ;; esac; "
        "if [ \"$NAV_ALL_TASKS_TERMINAL\" = 1 ] && [ \"$NAV_TASK_SUCCEEDED_COUNT\" -gt 0 ]; then NAV_FAST_TERMINAL=1; fi; "
        "if [ \"$SEEN_NAV_ACTIVE\" = 1 ] && awk 'BEGIN {exit !(ARGV[1] != \"\" && ARGV[1] <= 0.05)}' \"$NAV_REMAINING\" 2>/dev/null; then NAV_REACHED_COUNT=$((NAV_REACHED_COUNT + 1)); else NAV_REACHED_COUNT=0; fi; "
        "if [ \"$NAV_REACHED_COUNT\" -ge 3 ]; then NAV_FAST_TERMINAL=1; NAV_TASK_ACTIVE=0; fi; "
        "if [ \"$NAV_FAST_TERMINAL\" != 1 ] && [ \"$NAV_TASK_RUNNING_COUNT\" -gt 0 ]; then NAV_TASK_ACTIVE=1; fi; "
        "if [ \"$NAV_FAST_TERMINAL\" = 1 ] && [ \"$SEEN_NAV_ACTIVE\" = 1 ]; then "
        f"{stop_after_success}"
        "true; exit 0; "
        "fi; "
        "case \"$NAV_STATE\" in "
        f"{terminal_states}) "
        "if [ \"$NAV_TASK_ACTIVE\" = 1 ] || [ \"$NAV_TASK_PENDING_COUNT\" -gt 0 ]; then sleep 1; continue; fi; "
        "if [ \"$NAV_FAST_TERMINAL\" = 1 ]; then "
        f"{stop_after_success}"
        "true; "
        "exit 0; "
        "fi; "
        "if [ \"$SEEN_NAV_ACTIVE\" != 1 ]; then "
        "true; "
        "sleep 1; continue; "
        "fi; "
        "if [ \"$NAV_TASK_COUNT\" -gt 0 ] && [ \"$NAV_ALL_TASKS_TERMINAL\" != 1 ]; then sleep 1; continue; fi; "
        f"{release_body_control}"
        f"{release_owner}"
        "true; "
        "exit 0 ;; "
        "esac; "
        f"if [ $(( $(date +%s) - WATCH_START_TS )) -ge {timeout_seconds} ]; then "
        "printf '[%s] release watcher timeout state=%s task=%s remaining=%s\\n' "
        "\"$(date '+%F %T')\" \"${NAV_STATE:---}\" \"${NAV_TASK_STATUS:---}\" \"${NAV_REMAINING:---}\"; "
        f"{release_body_control}"
        f"{release_owner}"
        "true; exit 0; "
        "fi; "
        "sleep 1; "
        "done; "
    )
    return (
        f"RELEASE_WATCH_LOG={quote(release_log)}; "
        "ps -eo pid=,args= 2>/dev/null | awk -v self=$$ -v marker=\"$RELEASE_WATCH_LOG\" "
        "'$1 != self && index($0, marker) {print $1}' | xargs -r kill 2>/dev/null || true; "
        f"nohup bash -lc {quote(watcher)} >> \"$RELEASE_WATCH_LOG\" 2>&1 & "
        "true; "
    )
