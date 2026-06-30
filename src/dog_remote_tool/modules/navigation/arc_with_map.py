from __future__ import annotations

from dog_remote_tool.core.profiles import ProductProfile
from dog_remote_tool.core.shell import CommandSpec, echo_message, quote, remote_env
from dog_remote_tool.modules import mapping
from dog_remote_tool.modules.arc_app_ws import common_arc_app_ws_python, stale_app_ws_cleanup_shell
from dog_remote_tool.modules.navigation import helper_commands as _helper_commands
from dog_remote_tool.modules.navigation import payloads as _payloads


def _arc_with_map_app_ws_python() -> str:
    return common_arc_app_ws_python() + r'''

MAP_ID = sys.argv[1]
MONITOR_SECONDS = int(sys.argv[2])
ARC_ERROR_CODES = set()


def is_explicit_false(value):
    if value is None:
        return False
    return str(value).strip().lower() in {"false", "0", "unmatched", "notmatched", "not_matched"}


def handle_arc_notify(parsed):
    data = parsed.get("data", {}) if isinstance(parsed, dict) else {}
    for item in data.get("items", []) if isinstance(data, dict) else []:
        if str(item.get("severity", "")).lower() != "error":
            continue
        code = str(item.get("code", ""))
        desc = str(item.get("description", ""))
        if code:
            ARC_ERROR_CODES.add(code)
        if desc:
            ARC_ERROR_CODES.add(desc)
    print_arc_notify(parsed)


def mapped_arc_error_seen():
    return bool(ARC_ERROR_CODES)


def mapped_arc_error_text():
    if not ARC_ERROR_CODES:
        return "未知 ARC 错误"
    return "；".join(sorted(ARC_ERROR_CODES))


def mapped_arc_error_hint():
    if "13702" in ARC_ERROR_CODES or "FINE_FAILURE" in ARC_ERROR_CODES:
        return mapped_arc_error_hint_for_fine_failure()
    if "13697" in ARC_ERROR_CODES or "DOCK_NOT_READY" in ARC_ERROR_CODES:
        return "充电桩未就绪：请确认充电桩已上电，并已完成蓝牙/UWB/桩配对。"
    return ""


def mapped_arc_error_hint_for_fine_failure():
    return "精对准失败：对准未完成收敛。请确认桩体识别稳定、地图充电桩标记未偏移，并检查底盘是否进入 ARC 对准控制。"


def prepare_mapped_recharge(sock, frame):
    print("[INFO] 准备有图进桩：确认充电桩匹配和定位。", flush=True)
    match_resp, frame = request_once(sock, frame, "get_arc_match_status", required=True, log_response=False)
    match_value = None if match_resp is None else match_resp.get("data")
    if is_explicit_false(match_value):
        print("[ERROR] 当前系统返回未匹配充电桩，请先完成充电桩匹配。", flush=True)
        raise SystemExit(5)
    _tag_resp, frame = request_once(sock, frame, "get_cur_arc_tagid", required=False, log_response=False)

    _resp, frame = request_once(sock, frame, "loc_load_map", MAP_ID, wait_seconds=8, log_response=False)
    deadline = time.time() + 60
    while time.time() < deadline:
        loc_resp, frame = request_once(
            sock,
            frame,
            "get_loc_status",
            wait_seconds=2,
            required=False,
            log_response=False,
        )
        loc_status = None if loc_resp is None else loc_resp.get("data")
        if is_location_continuous(loc_status):
            print("[INFO] 定位已就绪，开始导航到充电桩。", flush=True)
            return frame
        if str(loc_status).strip().lower() in {"failed", "failure", "locfailed", "error"}:
            print(f"[ERROR] 定位失败: {loc_status}", flush=True)
            raise SystemExit(5)
        time.sleep(1)
    print("[ERROR] 等待定位进入连续定位状态超时。", flush=True)
    raise SystemExit(5)


def ensure_arc_ready(sock, frame, alg, dock):
    if alg != "Passive":
        return frame, alg, dock
    _resp, frame = request_once(sock, frame, "stop_arc", wait_seconds=1, required=False, log_response=False)
    _resp, frame = request_once(sock, frame, "stop_nav", wait_seconds=1, required=False, log_response=False)
    time.sleep(0.5)
    status, frame = query_status(sock, frame)
    alg = str(status.get("get_arc_alg_status") or "")
    dock = str(status.get("get_arc_dock_status") or "")
    return frame, alg, dock


def send_arc_request(sock, frame, func, value=NO_VALUE, label="ARC 请求", wait_seconds=4, expected_funcs=None):
    expected = set(expected_funcs or (func,))
    send_text(sock, request(func, frame, value))
    frame += 1
    deadline = time.time() + wait_seconds
    while time.time() < deadline:
        message = recv_text(sock)
        if not message:
            continue
        if "app_sub_topic" in message and "odom_ground_truth" in message:
            continue
        parsed = parse_app_response(message)
        if isinstance(parsed, dict) and parsed.get("kind") == "app_resp":
            if parsed.get("func") not in expected:
                continue
            if parsed.get("status") not in (None, "ok"):
                msg = parsed.get("msg")
                msg_text = f" msg={msg}" if msg else ""
                print(
                    f"[ERROR] ARC 请求失败: func={parsed.get('func')} status={parsed.get('status')} "
                    f"error={parsed.get('error_code')}{msg_text}",
                    flush=True,
                )
                raise SystemExit(6)
            print(f"[INFO] {label}", flush=True)
            return frame
        elif isinstance(parsed, dict) and parsed.get("head", {}).get("type") == "alg_error_code_notify":
            handle_arc_notify(parsed)
    print("[ERROR] 有图进桩未启动：系统未确认请求，请确认 ARC 模块已就绪后重试。", flush=True)
    raise SystemExit(6)


def send_mapped_recharge_request(sock, frame):
    return send_arc_request(
        sock,
        frame,
        "start_arc_with_map",
        MAP_ID,
        "已发送有图进桩请求。",
        expected_funcs={"start_arc_with_map", "start_nav"},
    )


def send_coarse_control_request(sock, frame):
    return send_arc_request(
        sock,
        frame,
        "start_arc_align_coarse",
        label="已进入对准阶段，继续进桩。",
        wait_seconds=3,
        expected_funcs={"start_arc_align_coarse", "start_align_coarse"},
    )


def should_send_coarse_control(alg, dock):
    return alg == "DockAlignCoarse"


def mapped_stage_text(alg, dock):
    if alg == "DockAlignCoarse":
        return "已到达桩前，开始粗对准。"
    if alg == "DockAlignFine":
        return "正在精对准。"
    if alg == "DockContact":
        return "已接触充电桩。"
    if alg == "RequestPowerOn" or dock == "Contact":
        return "正在请求充电桩上电。"
    return ""


def cleanup_mapped_recharge(sock, frame):
    for func in ("stop_arc", "stop_nav"):
        try:
            send_text(sock, request(func, frame))
            frame += 1
            deadline = time.time() + 1.0
            while time.time() < deadline:
                message = recv_text(sock)
                if not message:
                    continue
                parsed = parse_app_response(message)
                if isinstance(parsed, dict) and parsed.get("kind") == "app_resp" and parsed.get("func") == func:
                    break
        except Exception:
            pass
    return frame


sock = connect_ws()
frame = 1
exit_code = 0
try:
    before, frame = query_status(sock, frame)
    alg_before = str(before.get("get_arc_alg_status") or "")
    dock_before = str(before.get("get_arc_dock_status") or "")
    if alg_before == "Charging" or dock_before == "Charging":
        print("[ERROR] 当前已经在充电中，请使用出桩。", flush=True)
        raise SystemExit(4)
    frame, alg_before, dock_before = ensure_arc_ready(sock, frame, alg_before, dock_before)

    frame = prepare_mapped_recharge(sock, frame)
    frame = send_mapped_recharge_request(sock, frame)

    last = None
    coarse_sent = False
    align_started_at = None
    fine_align_seen = False
    nav_started_at = time.time()
    nav_wait_seconds = max(MONITOR_SECONDS, 180)
    while True:
        status, frame = query_status(sock, frame)
        snapshot = (status.get("get_arc_alg_status"), status.get("get_arc_dock_status"))
        if snapshot != last:
            stage_text = mapped_stage_text(snapshot[0], snapshot[1])
            if stage_text:
                print(f"[INFO] {stage_text}", flush=True)
            last = snapshot
        alg = str(status.get("get_arc_alg_status") or "")
        dock = str(status.get("get_arc_dock_status") or "")
        if align_started_at is None and alg in {"DockAlignCoarse", "DockAlignFine", "DockContact", "RequestPowerOn"}:
            align_started_at = time.time()
        if not coarse_sent and should_send_coarse_control(alg, dock):
            frame = send_coarse_control_request(sock, frame)
            coarse_sent = True
            continue
        if align_started_at is None and time.time() - nav_started_at >= 8 and alg == "Passive":
            print("[ERROR] 有图进桩未启动：ARC 对准系统仍未就绪。", flush=True)
            raise SystemExit(7)
        if alg == "Charging" or dock == "Charging":
            print("[INFO] 有图回充成功，已进入充电状态。", flush=True)
            raise SystemExit(0)
        if alg == "DockAlignFine":
            fine_align_seen = True
        if mapped_arc_error_seen():
            print(f"[ERROR] ARC 有图回充失败: {mapped_arc_error_text()}", flush=True)
            hint = mapped_arc_error_hint()
            if hint:
                print(f"[ERROR] {hint}", flush=True)
            raise SystemExit(7)
        if alg in {"FailureSafe", "Failure", "FailureContact"}:
            if fine_align_seen:
                print("[ERROR] ARC 有图回充失败：精对准未完成。", flush=True)
                print(f"[ERROR] {mapped_arc_error_hint_for_fine_failure()}", flush=True)
            else:
                print("[ERROR] ARC 有图回充进入失败状态。", flush=True)
            raise SystemExit(7)
        if align_started_at is not None and alg in {"Passive", "UnDockReset", "ChargedExit"}:
            if fine_align_seen and alg == "ChargedExit":
                print("[ERROR] ARC 有图回充失败：精对准未完成。", flush=True)
                print(f"[ERROR] {mapped_arc_error_hint_for_fine_failure()}", flush=True)
            else:
                print(f"[ERROR] ARC 有图回充进入非进桩状态: alg={alg} dock={dock}", flush=True)
            raise SystemExit(7)
        if align_started_at is None and time.time() - nav_started_at >= nav_wait_seconds:
            print("[ERROR] ARC 有图回充等待进入对准阶段超时。", flush=True)
            break
        if align_started_at is not None and time.time() - align_started_at >= MONITOR_SECONDS:
            final_status, frame = query_status(sock, frame)
            final_alg = str(final_status.get("get_arc_alg_status") or "")
            final_dock = str(final_status.get("get_arc_dock_status") or "")
            if final_alg == "Charging" or final_dock == "Charging":
                print("[INFO] 有图回充成功，已进入充电状态。", flush=True)
                raise SystemExit(0)
            print("[ERROR] ARC 有图回充进桩阶段等待超时。", flush=True)
            break
        time.sleep(0.5)

    try:
        frame = cleanup_mapped_recharge(sock, frame)
        print("[INFO] 已发送有图回充停止请求，清理超时任务。", flush=True)
    except Exception as exc:
        print(f"[WARN] 有图回充停止请求发送失败: {exc}", flush=True)
    raise SystemExit(8)
except SystemExit as exc:
    try:
        exit_code = int(exc.code or 0)
    except Exception:
        exit_code = 1
    raise
except Exception:
    exit_code = 1
    raise
finally:
    if exit_code != 0:
        try:
            frame = cleanup_mapped_recharge(sock, frame)
            print("[INFO] 已停止有图回充任务并释放控制。", flush=True)
        except Exception as exc:
            print(f"[WARN] 有图回充停止请求发送失败: {exc}", flush=True)
    try:
        send_close(sock)
    except Exception:
        pass
    try:
        sock.close()
    except Exception:
        pass
'''


def start_arc_with_map_command(profile: ProductProfile, map_pcd_path: str, monitor_seconds: int = 120) -> CommandSpec:
    runtime_profile = mapping.arc_runtime_profile(profile)
    monitor_seconds = max(30, min(int(monitor_seconds), 180))
    map_yaml_path = _payloads._navigation_2d_map_path(map_pcd_path)
    map_id = _payloads.map_id_from_map_path(map_pcd_path)
    cleanup = (
        "rc=$?; "
        "if [ \"$rc\" -ne 0 ]; then "
        "if ps -eo args= 2>/dev/null | grep -E -- '(^|[ /])robot_alg_manager([[:space:]]|$)' | grep -v grep >/dev/null; then "
        f"{_helper_commands._alg_manager_stop_nav_inner(fail_on_error=False)}"
        "fi; "
        f"{_helper_commands._mode_switch_inner(False, 0.2)}"
        "fi; "
        "exit \"$rc\""
    )
    legacy_control_cleanup = (
        "old_control_pids=$(ps -eo pid,args | awk "
        "'/dog_remote_keyboard_control_claim[.]log|ros2 topic pub -r 20 \\/robot_roamerx\\/is_in_nav_control std_msgs\\/msg\\/Bool [{]data: true[}]/ "
        "&& $0 !~ /awk/ {print $1}'); "
        "if [ -n \"$old_control_pids\" ]; then "
        "kill $old_control_pids >/dev/null 2>&1 || true; "
        "sleep 0.1; "
        "kill -9 $old_control_pids >/dev/null 2>&1 || true; "
        "timeout 0.4s ros2 topic pub -r 20 /robot_roamerx/is_in_nav_control std_msgs/msg/Bool '{data: false}' "
        ">/tmp/dog_remote_arc_pre_release_control_right.log 2>&1 || true; "
        "fi; "
    )
    inner = (
        f"{remote_env(runtime_profile)}; "
        "source /opt/robot/robot_nav/install/setup.bash >/dev/null 2>&1 || true; "
        "source /opt/robot/robot_arc/install/setup.bash >/dev/null 2>&1 || true; "
        f"{stale_app_ws_cleanup_shell()}"
        f"{legacy_control_cleanup}"
        f"if [ ! -s {quote(map_pcd_path)} ]; then {echo_message(f'[ERROR] 地图 PCD 不存在或为空: {map_pcd_path}')}; exit 2; fi; "
        f"if [ ! -f {quote(map_yaml_path)} ]; then {echo_message(f'[ERROR] 当前地图 map.yaml 不存在: {map_yaml_path}')}; exit 2; fi; "
        f"if ! grep -q 'arc_position_flag:[[:space:]]*1' {quote(map_yaml_path)} 2>/dev/null; then "
        f"{echo_message('[ERROR] 当前地图未标记充电桩，未发现 arc_position_flag=1')}; exit 2; fi; "
        f"python3 -c {quote(_arc_with_map_app_ws_python())} {quote(map_id)} {monitor_seconds}; "
        f"{cleanup}"
    )
    return CommandSpec(
        "有图回充",
        _helper_commands._navigation_start_ssh_command(runtime_profile, inner),
        dangerous=True,
        description="会通过系统应用通道执行有图回充，机器人会自主移动到地图中的充电桩。",
        display_command="执行：ARC 有图回充",
        concurrency="parallel",
        locks=("arc", "motion", "app_ws"),
    )
