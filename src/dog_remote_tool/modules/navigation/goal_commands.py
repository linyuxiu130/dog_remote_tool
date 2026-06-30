from __future__ import annotations

import json
import os
import tempfile
import textwrap
from dog_remote_tool.core.profiles import ProductProfile
from dog_remote_tool.core.network_routes import with_route_repair
from dog_remote_tool.core.shell import CommandSpec, echo_message, quote, remote_env, ssh_prefix_command
from dog_remote_tool.modules.body_navigation_bridge import ensure_body_navigation_bridge_command
from dog_remote_tool.modules.arc_app_ws import common_arc_app_ws_python
from dog_remote_tool.modules.navigation import route_network
from dog_remote_tool.modules.navigation.helper_commands import (
    _navigation_start_ssh_command,
)
from dog_remote_tool.modules.navigation.helper_control import NAVIGATION_LOOP_LOG, NAVIGATION_LOOP_PID
from dog_remote_tool.modules.navigation.map_commands import (
    _fast_navigation_header,
    _navigation_2d_map_gate_inner,
)
from dog_remote_tool.modules.navigation.payloads import (
    alg_manager_start_nav_payload,
    alg_manager_start_multi_nav_by_points_payload,
    alg_manager_start_multi_nav_task_route_value,
    map_id_from_map_path,
)

NAVIGATION_LOOP_BATCH_ROUNDS = 20
NAVIGATION_COMMAND_LOCKS = ("navigation-command",)


def _route_goal_inputs(
    route_geojson_path: str,
    x: float,
    y: float,
    yaw: float,
    points: list[tuple[float, float, float]] | None,
) -> tuple[str, list[tuple[float, float, float]]]:
    route_path = route_geojson_path or route_network.DEFAULT_REMOTE_ROUTE_FILE
    return route_path, list(points or [(x, y, yaw)])


def _route_goal_checks_inner(
    profile: ProductProfile,
    map_pcd_path: str,
    route_path: str,
) -> str:
    return (
        f"{_fast_navigation_header(profile)}"
        f"if [ ! -s {quote(map_pcd_path)} ]; then {echo_message(f'[ERROR] 地图 PCD 不存在或为空: {map_pcd_path}')}; exit 2; fi; "
        f"{_navigation_map_id_inner(map_pcd_path)}"
        f"if [ ! -s {quote(route_path)} ]; then {echo_message(f'[ERROR] 路网文件不存在或为空: {route_path}')}; exit 2; fi; "
    )


def _navigation_task_spec(
    title: str,
    command: str,
    *,
    description: str,
    display_command: str,
) -> CommandSpec:
    return CommandSpec(
        title,
        command,
        dangerous=True,
        description=description,
        display_command=display_command,
        concurrency="parallel",
        locks=NAVIGATION_COMMAND_LOCKS,
    )


def _navigation_task_start_command(profile: ProductProfile, inner: str) -> str:
    return _navigation_start_ssh_command(profile, inner, require_control_switch=True)


def _navigation_task_start_stdin_command(profile: ProductProfile, inner: str) -> str:
    script_dir = os.path.join(tempfile.gettempdir(), "dog_remote_nav_scripts")
    os.makedirs(script_dir, mode=0o700, exist_ok=True)
    fd, script_path = tempfile.mkstemp(prefix="route_nav_", suffix=".sh", dir=script_dir, text=True)
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        handle.write("set -e\n")
        handle.write(remote_env(profile))
        handle.write("; ")
        handle.write(inner)
        handle.write("\n")
    os.chmod(script_path, 0o600)
    command = f"{ssh_prefix_command(profile)} bash -s < {quote(script_path)}"
    command = with_route_repair(profile, command)
    cleanup = f"rc=$?; rm -f {quote(script_path)}; exit $rc"
    bridge_command = ensure_body_navigation_bridge_command(profile, require_control_switch=True)
    if not bridge_command:
        return f"( {command} ); {cleanup}"
    return (
        "if [ \"${DOG_REMOTE_DISABLE_BODY_NAV_BRIDGE:-0}\" = 1 ]; then "
        "echo '[INFO] 已跳过导航准备检查'; "
        f"( {command} ); {cleanup}; "
        "else "
        f"( {bridge_command} ) && ( {command} ); {cleanup}; "
        "fi"
    )


def _fast_dispatch_status_inner() -> str:
    return (
        "if ps -eo args= 2>/dev/null | grep -E -- '(^|[ /])robot_alg_manager([[:space:]]|$)' | grep -v grep >/dev/null; then "
        "echo '[INFO] 导航服务已就绪，使用快速下发'; "
        "else "
        "echo '[WARN] 快速下发不可用，使用兼容下发'; "
        "fi; "
    )


def _navigation_map_id_inner(map_pcd_path: str) -> str:
    map_id = map_id_from_map_path(map_pcd_path)
    return (
        f"DOG_REMOTE_NAV_MAP_ID={quote(map_id)}; "
        "if [ \"$DOG_REMOTE_NAV_MAP_ID\" = map ] && [ -d /ota/alg_data/map/history_map ]; then "
        "DOG_REMOTE_NAV_HISTORY_DIR=$(find /ota/alg_data/map/history_map -mindepth 1 -maxdepth 1 -type d "
        "\\( -name '20*' -o -name '19*' \\) -exec test -s '{}/map.pcd' ';' -exec test -s '{}/map.yaml' ';' -print "
        "2>/dev/null | sort | tail -1); "
        "if [ -n \"$DOG_REMOTE_NAV_HISTORY_DIR\" ]; then DOG_REMOTE_NAV_MAP_ID=$(basename \"$DOG_REMOTE_NAV_HISTORY_DIR\"); fi; "
        "fi; "
    )


def _multi_nav_value_env_inner(value_json: str) -> str:
    return (
        "DOG_REMOTE_MULTI_NAV_VALUE=$(python3 - <<'PY'\n"
        "import json, os\n"
        f"value = {value_json!r}\n"
        "value = json.loads(value)\n"
        "value[0] = os.environ.get('DOG_REMOTE_NAV_MAP_ID') or value[0]\n"
        "print(json.dumps(value, ensure_ascii=False, separators=(',', ':')))\n"
        "PY\n"
        "); "
    )


def _multi_nav_value_json(map_pcd_path: str, points: list[tuple[float, float, float]]) -> str:
    payload = alg_manager_start_multi_nav_by_points_payload(map_id_from_map_path(map_pcd_path), points, 1)
    value = json.loads(payload)["data"]["req_func"]["start_multi_nav_by_points"]
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _route_nav_value_json(
    map_pcd_path: str,
    route_path: str,
    points: list[tuple[float, float, float]],
    speed: float,
    tolerance: float,
) -> str:
    value = alg_manager_start_multi_nav_task_route_value(
        map_id_from_map_path(map_pcd_path),
        route_path,
        points,
        speed,
        tolerance,
    )
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _route_nav_value_env_inner(value_json: str) -> str:
    return (
        "DOG_REMOTE_ROUTE_NAV_VALUE=$(python3 - <<'PY'\n"
        "import json, os\n"
        f"value = {value_json!r}\n"
        "value = json.loads(value)\n"
        "value['map_id'] = os.environ.get('DOG_REMOTE_NAV_MAP_ID') or value['map_id']\n"
        "print(json.dumps(value, ensure_ascii=False, separators=(',', ':')))\n"
        "PY\n"
        "); "
    )


def _alg_manager_nav_task_inner(kind: str, request_json_arg: str, timeout_seconds: int) -> str:
    task_blocks = {
        "single": r'''
request(2, "start_nav", REQUEST_VALUE, wait=5)
print("[INFO] 导航目标已提交", flush=True)
wait_done(20)
'''.strip(),
        "multi": r'''
request(2, "start_multi_nav_by_points", REQUEST_VALUE, wait=6, expected_func="start_multi_nav")
print("[INFO] 多点导航任务已提交", flush=True)
wait_done(20)
'''.strip(),
        "route": r'''
request(2, "start_multi_nav_task", REQUEST_VALUE, wait=6)
print("[INFO] 路网导航目标已提交，执行状态以后续导航状态为准", flush=True)
wait_done(20)
'''.strip(),
        "loop": r'''
loop_index = 1
while True:
    print(f"[INFO] 多点循环开始第 {loop_index} 批", flush=True)
    request(1000 + loop_index, "start_multi_nav_by_points", REQUEST_VALUE, wait=6, expected_func="start_multi_nav")
    print("[INFO] 多点循环任务已提交", flush=True)
    wait_done(2000 + loop_index * 100)
    reset_nav_state(8000 + loop_index * 100)
    loop_index += 1
    time.sleep(0.5)
'''.strip(),
        "route_loop": r'''
loop_index = 1
while True:
    print(f"[INFO] 路网循环开始第 {loop_index} 批", flush=True)
    request(1000 + loop_index, "start_multi_nav_task", REQUEST_VALUE, wait=6)
    print("[INFO] 路网循环任务已提交", flush=True)
    wait_done(2000 + loop_index * 100)
    reset_nav_state(8000 + loop_index * 100)
    loop_index += 1
    time.sleep(0.5)
'''.strip(),
    }
    if kind not in task_blocks:
        raise ValueError(f"unsupported nav task kind: {kind}")
    task_code = "\n" + textwrap.indent(task_blocks[kind], "    ") + "\n"
    python = common_arc_app_ws_python() + "\n" + r'''
import json, os, signal, socket, subprocess, sys, time

REQUEST_VALUE = json.loads(sys.argv[1])
TIMEOUT_SECONDS = float(sys.argv[2])
MODE_TOPIC = "/robot_roamerx/is_in_nav_control"

CLIENT = AppWsBrokerClient()

def request(frame, func, value=None, wait=5.0, expected_func=None):
    expected = expected_func or func
    req_func = func if value is None else {func: value}
    obj = {"head": {"type": "app_req", "time_stamp": int(time.time() * 1000), "source": "app", "frame_count": frame}, "data": {"req_func": req_func}}
    messages = CLIENT.request(obj, expected, wait)
    for msg in messages:
        parsed = parse_app_response(msg)
        if not isinstance(parsed, dict) or parsed.get("kind") != "app_resp":
            continue
        if parsed.get("func") == expected:
            if parsed.get("status") not in (None, "ok"):
                raise RuntimeError(parsed)
            return parsed
    raise TimeoutError(expected)

def body_cmd(cmd):
    host = os.environ.get("DOG_REMOTE_BODY_NAV_HOST", "192.168.234.1")
    port = int(os.environ.get("DOG_REMOTE_BODY_NAV_PORT", "8081"))
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.settimeout(0.2)
    payloads = ({"role": "remote", "type": "heartbeat"}, {"cmd": cmd, "type": "cmd"})
    try:
        for payload in payloads:
            sock.sendto(json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode(), (host, port))
            time.sleep(0.05)
    finally:
        sock.close()

def start_mode_topic():
    return subprocess.Popen(
        ["ros2", "topic", "pub", "-r", "10", MODE_TOPIC, "std_msgs/msg/Bool", "{data: true}"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

def stop_mode_topic(proc):
    if proc and proc.poll() is None:
        proc.terminate()
        try:
            proc.wait(timeout=1)
        except subprocess.TimeoutExpired:
            proc.kill()
    subprocess.run(
        ["timeout", "0.5s", "ros2", "topic", "pub", "-r", "20", MODE_TOPIC, "std_msgs/msg/Bool", "{data: false}"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )

def nav_status(frame):
    app = request(frame, "get_nav_status")
    return str(app.get("data") or "")

def emit_nav_status(status):
    print(f"APP_NAV_STATUS={status}", flush=True)

def wait_done(frame_start):
    start = time.time()
    seen_running = False
    frame = frame_start
    last = ""
    while time.time() - start < TIMEOUT_SECONDS:
        frame += 1
        status = nav_status(frame)
        should_print = seen_running or status not in {"Stopped", "StandBy"}
        if status != last and should_print:
            emit_nav_status(status)
            print(f"[INFO] 导航状态: {status}", flush=True)
            last = status
        if status in {"Running", "Active", "Naving"}:
            seen_running = True
        elif status in {"Error", "NavError", "LocError", "Failed"}:
            raise RuntimeError(f"导航失败: {status}")
        elif status in {"Canceled", "Cancel", "Idle"}:
            raise RuntimeError(f"导航被取消: {status}")
        elif status == "Succeeded" and seen_running:
            print("[INFO] 导航结束", flush=True)
            return
        elif status in {"Stopped", "StandBy"} and seen_running:
            raise RuntimeError(f"导航未成功结束: {status}")
        elif status in {"Stopped", "StandBy"} and time.time() - start > 30:
            raise RuntimeError(f"导航未进入执行态: {status}")
        time.sleep(1)
    raise TimeoutError("导航等待超时")

def reset_nav_state(frame_start):
    frame = frame_start
    status = nav_status(frame)
    if status in {"Stopped", "StandBy"}:
        return
    request(frame_start, "stop_nav", wait=2)
    deadline = time.time() + 8
    last = ""
    standby_requested = False
    while time.time() < deadline:
        frame += 1
        status = nav_status(frame)
        if status != last:
            emit_nav_status(status)
            print(f"[INFO] 导航状态: {status}", flush=True)
            last = status
        if status in {"Stopped", "StandBy"}:
            return
        if status in {"Canceled", "Cancel", "Idle"} and not standby_requested:
            standby_requested = True
            request(frame + 100, "standby_nav", wait=2)
        time.sleep(0.5)
    raise RuntimeError(f"启动前导航状态未回空闲: {last or status or 'unknown'}")

topic_proc = None
cleaning_up = False

def cleanup():
    global cleaning_up
    if cleaning_up:
        return
    cleaning_up = True
    try:
        request(9001, "stop_nav")
    except Exception as exc:
        print(f"[WARN] 停止导航请求未确认: {exc}", flush=True)
    try:
        request(9002, "change_control_right_to", {"owner": "app"})
    except Exception as exc:
        print(f"[WARN] app控制权释放未确认: {exc}", flush=True)
    CLIENT.close()
    body_cmd(170)
    stop_mode_topic(topic_proc)

def handle_signal(signum, _frame):
    cleanup()
    raise SystemExit(128 + signum)

for sig in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP):
    signal.signal(sig, handle_signal)

try:
    topic_proc = start_mode_topic()
    time.sleep(0.3)
    body_cmd(180)
    request(1, "change_control_right_to", {"owner": "alg"}, wait=3)
    reset_nav_state(10)
''' + task_code + r'''
finally:
    cleanup()
'''.strip()
    return (
        "python3 -c "
        f"{quote(python)} "
        f"{request_json_arg} "
        f"{quote(str(timeout_seconds))}"
    )


def _expanded_loop_points(
    points: list[tuple[float, float, float]],
    rounds: int = NAVIGATION_LOOP_BATCH_ROUNDS,
) -> list[tuple[float, float, float]]:
    if rounds < 1:
        raise ValueError("循环展开轮数必须大于 0")
    return list(points) * rounds


def _navigation_loop_wait_function_inner() -> str:
    return (
        "wait_nav_done() { "
        "SEEN_ACTIVE=0; "
        "NAV_LAST_STATE=; NAV_LAST_TASK=; "
        "WAIT_START_TS=$(date +%s); "
        "while true; do "
        "NAV_MSG=$(timeout 2s ros2 topic echo --once /navigation_state --no-daemon 2>/dev/null || true); "
        "NAV_STATE=$(printf '%s\\n' \"$NAV_MSG\" | awk '/^state:/ {print $2; exit}'); "
        "NAV_TASK=$(printf '%s\\n' \"$NAV_MSG\" | awk '/task_status_list:/ {in_list=1; next} in_list && /^[[:space:]]*-[[:space:]]*task_status:/ {print $NF; exit} in_list && /task_status:/ {print $NF; exit} in_list && /^[^[:space:]]/ {in_list=0}'); "
        "if [ -n \"$NAV_STATE\" ]; then NAV_LAST_STATE=\"$NAV_STATE\"; fi; "
        "if [ -n \"$NAV_TASK\" ]; then NAV_LAST_TASK=\"$NAV_TASK\"; fi; "
        "case \"$NAV_STATE\" in 2|3|100|140|141) SEEN_ACTIVE=1 ;; esac; "
        "case \"$NAV_TASK\" in 2|3) SEEN_ACTIVE=1 ;; esac; "
        "case \"$NAV_STATE:$NAV_TASK\" in *:4|*:6|4:*|6:*|7:*|202:*) "
        "echo '[WARN] 导航循环观察到终止/失败状态: state='\"${NAV_LAST_STATE:---}\"' task='\"${NAV_LAST_TASK:---}\"; "
        "return 2 ;; esac; "
        "case \"$NAV_STATE:$NAV_TASK\" in 5:*|200:*|*:5) return 0 ;; esac; "
        "case \"$NAV_STATE\" in 0|1) if [ \"$SEEN_ACTIVE\" = 1 ]; then return 0; fi ;; esac; "
        "if [ \"$SEEN_ACTIVE\" != 1 ] && [ $(( $(date +%s) - WAIT_START_TS )) -gt 30 ]; then "
        "echo '[WARN] 导航循环等待执行超时，未观察到 active: state='\"${NAV_LAST_STATE:---}\"' task='\"${NAV_LAST_TASK:---}\"; "
        "return 3; "
        "fi; "
        "sleep 1; "
        "done; "
        "}; "
    )


def _start_navigation_loop_inner(loop_body: str, label: str) -> str:
    return (
        f"NAV_LOOP_PID_FILE={quote(NAVIGATION_LOOP_PID)}; NAV_LOOP_LOG={quote(NAVIGATION_LOOP_LOG)}; "
        "OLD_NAV_LOOP_PID=$(cat \"$NAV_LOOP_PID_FILE\" 2>/dev/null || true); "
        "if [ -n \"$OLD_NAV_LOOP_PID\" ] && kill -0 \"$OLD_NAV_LOOP_PID\" 2>/dev/null; then "
        "echo '[INFO] 停止已有导航循环任务: pid='\"$OLD_NAV_LOOP_PID\"; "
        "kill \"$OLD_NAV_LOOP_PID\" 2>/dev/null || true; sleep 0.3; "
        "if kill -0 \"$OLD_NAV_LOOP_PID\" 2>/dev/null; then kill -9 \"$OLD_NAV_LOOP_PID\" 2>/dev/null || true; fi; "
        "fi; "
        "rm -f \"$NAV_LOOP_PID_FILE\"; "
        ": > \"$NAV_LOOP_LOG\"; "
        f"nohup bash -lc {quote(loop_body)} >> \"$NAV_LOOP_LOG\" 2>&1 & "
        "NAV_LOOP_PID=$!; echo \"$NAV_LOOP_PID\" > \"$NAV_LOOP_PID_FILE\"; "
        "sleep 0.2; "
        "if ! kill -0 \"$NAV_LOOP_PID\" 2>/dev/null; then "
        f"echo '[ERROR] 导航循环任务启动后立即退出: {label}, log='\"$NAV_LOOP_LOG\"; "
        "tail -40 \"$NAV_LOOP_LOG\" 2>/dev/null || true; "
        "rm -f \"$NAV_LOOP_PID_FILE\"; exit 12; "
        "fi; "
        f"echo '[INFO] 已启动远端导航循环任务: {label}, pid='\"$NAV_LOOP_PID\"' log='\"$NAV_LOOP_LOG\"; "
    )


def start_goal_command(
    profile: ProductProfile,
    map_pcd_path: str,
    x: float,
    y: float,
    yaw: float,
    speed: float,
    tolerance: float,
) -> CommandSpec:
    app_payload = alg_manager_start_nav_payload(x, y, yaw)
    app_payload_json = json.dumps(app_payload, ensure_ascii=False, separators=(",", ":"))
    inner = (
        f"{_fast_navigation_header(profile)}"
        f"if [ ! -s {quote(map_pcd_path)} ]; then {echo_message(f'[ERROR] 地图 PCD 不存在或为空: {map_pcd_path}')}; exit 2; fi; "
        f"{_navigation_2d_map_gate_inner(map_pcd_path)}"
        "echo '[INFO] 正在提交导航目标'; "
        f"{_alg_manager_nav_task_inner('single', quote(app_payload_json), 300)}; "
    )
    return _navigation_task_spec(
        "发送导航目标",
        _navigation_task_start_command(profile, inner),
        description="会向导航栈发送目标点，机器人可能开始移动。",
        display_command="执行：发送导航目标",
    )


def start_multipoint_command(
    profile: ProductProfile,
    map_pcd_path: str,
    points: list[tuple[float, float, float]],
    speed: float,
) -> CommandSpec:
    title = "开始多点导航"
    multi_value_json = _multi_nav_value_json(map_pcd_path, points)
    multi_value_arg = '"$DOG_REMOTE_MULTI_NAV_VALUE"'
    inner = (
        f"{_fast_navigation_header(profile)}"
        f"if [ ! -s {quote(map_pcd_path)} ]; then {echo_message(f'[ERROR] 地图 PCD 不存在或为空: {map_pcd_path}')}; exit 2; fi; "
        f"{_navigation_map_id_inner(map_pcd_path)}"
        "echo '[INFO] 正在发送多点导航任务'; "
        f"{_multi_nav_value_env_inner(multi_value_json)}"
        f"{_alg_manager_nav_task_inner('multi', multi_value_arg, 900)}; "
    )
    return _navigation_task_spec(
        title,
        _navigation_task_start_command(profile, inner),
        description="会向导航栈发送路线任务，机器人可能开始移动。",
        display_command=f"执行：{title}",
    )


def start_multipoint_loop_command(
    profile: ProductProfile,
    map_pcd_path: str,
    points: list[tuple[float, float, float]],
    speed: float,
) -> CommandSpec:
    batch_points = _expanded_loop_points(points)
    multi_value_json = _multi_nav_value_json(map_pcd_path, batch_points)
    label = f"多点循环 count={len(points)}"
    multi_value_arg = '"$DOG_REMOTE_MULTI_NAV_VALUE"'
    loop_script = (
        f"{_multi_nav_value_env_inner(multi_value_json)}"
        f"exec {_alg_manager_nav_task_inner('loop', multi_value_arg, 900)}"
    )
    inner = (
        f"{_fast_navigation_header(profile)}"
        f"if [ ! -s {quote(map_pcd_path)} ]; then {echo_message(f'[ERROR] 地图 PCD 不存在或为空: {map_pcd_path}')}; exit 2; fi; "
        f"{_navigation_map_id_inner(map_pcd_path)}"
        f"{_start_navigation_loop_inner(loop_script, label)}"
        "echo '[INFO] 多点循环已启动：每批循环发送当前目标点；停止按钮会结束循环并停止当前导航'; "
    )
    return _navigation_task_spec(
        "开始多点循环",
        _navigation_task_start_command(profile, inner),
        description="会循环发送当前多点导航路线，直到点击停止。",
        display_command="执行：开始多点循环",
    )


def start_route_goal_command(
    profile: ProductProfile,
    map_pcd_path: str,
    route_geojson_path: str,
    x: float,
    y: float,
    yaw: float,
    speed: float,
    tolerance: float,
    points: list[tuple[float, float, float]] | None = None,
) -> CommandSpec:
    route_path, route_points = _route_goal_inputs(route_geojson_path, x, y, yaw, points)
    route_value_json = _route_nav_value_json(map_pcd_path, route_path, route_points, speed, tolerance)
    route_value_arg = '"$DOG_REMOTE_ROUTE_NAV_VALUE"'
    inner = (
        f"{_route_goal_checks_inner(profile, map_pcd_path, route_path)}"
        f"{_fast_dispatch_status_inner()}"
        "echo '[INFO] 正在提交路网导航目标'; "
        f"{_route_nav_value_env_inner(route_value_json)}"
        f"{_alg_manager_nav_task_inner('route', route_value_arg, 900)}; "
    )
    return _navigation_task_spec(
        "发送路网导航目标",
        _navigation_task_start_stdin_command(profile, inner),
        description="会向导航栈发送路网目标，机器人可能开始移动。",
        display_command="执行：发送路网导航目标",
    )


def start_route_goal_loop_command(
    profile: ProductProfile,
    map_pcd_path: str,
    route_geojson_path: str,
    x: float,
    y: float,
    yaw: float,
    speed: float,
    tolerance: float,
    points: list[tuple[float, float, float]] | None = None,
) -> CommandSpec:
    route_path, route_points = _route_goal_inputs(route_geojson_path, x, y, yaw, points)
    batch_points = _expanded_loop_points(route_points)
    route_value_json = _route_nav_value_json(map_pcd_path, route_path, batch_points, speed, tolerance)
    label = f"路网循环 count={len(route_points)}"
    route_value_arg = '"$DOG_REMOTE_ROUTE_NAV_VALUE"'
    loop_script = (
        f"{_route_nav_value_env_inner(route_value_json)}"
        f"exec {_alg_manager_nav_task_inner('route_loop', route_value_arg, 900)}"
    )
    inner = (
        f"{_route_goal_checks_inner(profile, map_pcd_path, route_path)}"
        f"{_start_navigation_loop_inner(loop_script, label)}"
        "echo '[INFO] 路网循环已启动；停止按钮会结束循环并停止当前导航'; "
    )
    return _navigation_task_spec(
        "开始路网循环",
        _navigation_task_start_stdin_command(profile, inner),
        description="会循环下发当前路网目标序列，直到点击停止。",
        display_command="执行：开始路网循环",
    )
