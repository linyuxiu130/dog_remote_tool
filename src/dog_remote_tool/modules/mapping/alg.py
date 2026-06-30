from __future__ import annotations

from dog_remote_tool.core.profiles import ProductProfile
from dog_remote_tool.core.shell import CommandSpec, quote, remote_env, ssh_command
from dog_remote_tool.modules.arc_app_ws import common_arc_app_ws_python, stale_app_ws_cleanup_shell
from dog_remote_tool.modules.mapping.defaults import history_map_path


ALG_READY_STATUSES = {"Ready", "MappingReady", "StandBy"}
ALG_MAPPING_STATUSES = {"Mapping", "MappingRunning"}
ALG_SAVING_STATUSES = {"MappingSaving", "MappingSaveBegin"}
ALG_SUCCESS_STATUSES = {"MappingSaved", "MappingSaveEnd"}
ALG_ERROR_STATUSES = {
    "Error",
    "MappingError",
    "LaunchMappingError",
    "VisualPclError",
    "RepeatMapping",
    "MappingNotStart",
}


def alg_mapping_status(status: str, error_code: str = "", error_msg: str = "") -> tuple[str, str] | None:
    value = str(status or "").strip()
    code = str(error_code or "").strip()
    if code and code not in {"0", "None", "null"}:
        detail = str(error_msg or "").strip()
        return "error", f"alg异常{code}" + (f"：{detail}" if detail else "")
    if value in ALG_READY_STATUSES:
        return "ready", "已就绪"
    if value in ALG_MAPPING_STATUSES:
        return "mapping", "建图中"
    if value in ALG_SAVING_STATUSES:
        return "saving", "保存中"
    if value in ALG_SUCCESS_STATUSES:
        return "success", "保存完成"
    if value in ALG_ERROR_STATUSES:
        return "error", value
    if value:
        return "unknown", f"未知状态：{value}"
    return None


def is_alg_mapping_active(status: str) -> bool:
    return str(status or "").strip() in ALG_MAPPING_STATUSES


def _alg_mapping_python() -> str:
    return common_arc_app_ws_python() + r'''
ACTION = sys.argv[1]
MONITOR_SECONDS = int(sys.argv[2])

READY = {"Ready", "MappingReady", "StandBy"}
MAPPING = {"Mapping", "MappingRunning"}
SAVING = {"MappingSaving", "MappingSaveBegin"}
SUCCESS = {"MappingSaved", "MappingSaveEnd"}
ERROR = {"Error", "MappingError", "LaunchMappingError", "VisualPclError", "RepeatMapping", "MappingNotStart"}

ACTION_FUNC = {
    "status": None,
    "start": "start_mapping",
    "finish": "stop_mapping",
    "cancel": "cancel_mapping",
}[ACTION]

ACTION_VALUE = {
    "status": NO_VALUE,
    "start": 1,
    "finish": 1,
    "cancel": NO_VALUE,
}[ACTION]

TARGETS = {
    "status": READY | MAPPING | SAVING | SUCCESS | ERROR,
    "start": MAPPING,
    "finish": SAVING | READY | SUCCESS,
    "cancel": READY | SUCCESS,
}[ACTION]

LABELS = {
    "status": "读取建图状态",
    "start": "开始建图",
    "finish": "结束保存建图",
    "cancel": "取消建图",
}

POLL_SECONDS = {
    "start": 0.25,
    "finish": 0.5,
    "cancel": 0.25,
}.get(ACTION, 1.0)


def status_text(status):
    value = "" if status is None else str(status)
    if value in READY:
        return "已就绪"
    if value in MAPPING:
        return "建图中"
    if value in SAVING:
        return "保存中"
    if value in SUCCESS:
        return "保存完成"
    if value in ERROR:
        return f"异常：{value}"
    if value:
        return f"未知状态：{value}"
    return "无状态"


def print_user_status(status, action=""):
    value = "" if status is None else str(status)
    label = "保存确认中" if action == "finish" and value in READY else status_text(value)
    if value:
        print(f"[INFO] 建图状态：{label}（{value}）", flush=True)
    else:
        print("[INFO] 建图状态：无状态", flush=True)


def emit_status(status, source="app", machine=True):
    value = "" if status is None else str(status)
    if not machine:
        return
    print(f"ALG_MAPPING_STATUS={value}", flush=True)
    print(f"ALG_MAPPING_SOURCE={source}", flush=True)
    label = status_text(value)
    if value in READY:
        print("STATUS=ready", flush=True)
        print(f"TEXT={label}", flush=True)
    elif value in MAPPING:
        print("STATUS=mapping", flush=True)
        print(f"TEXT={label}", flush=True)
    elif value in SAVING:
        print("STATUS=saving", flush=True)
        print(f"TEXT={label}", flush=True)
    elif value in SUCCESS:
        print("STATUS=success", flush=True)
        print(f"TEXT={label}", flush=True)
    elif value in ERROR:
        print("STATUS=error", flush=True)
        print(f"TEXT={label}", flush=True)
    else:
        print("STATUS=unknown", flush=True)
        print(f"TEXT={label}", flush=True)


def query_mapping_status(sock, frame, *, required=False, log_response=False):
    resp, frame = request_once(
        sock,
        frame,
        "get_mapping_status",
        wait_seconds=3,
        required=required,
        log_response=log_response,
    )
    return (None if resp is None else resp.get("data")), frame


sock = connect_ws()
frame = 1
try:
    before, frame = query_mapping_status(sock, frame, required=(ACTION == "status"), log_response=(ACTION == "status"))
    if before is not None:
        print_user_status(before)
    if ACTION == "status":
        emit_status(before)
        raise SystemExit(0)

    if ACTION == "start" and before in MAPPING:
        print("[INFO] 当前已在建图中，无需重复开始。", flush=True)
        emit_status(before, machine=False)
        raise SystemExit(0)
    if ACTION == "finish" and before in SUCCESS:
        print("[INFO] 当前地图已保存完成，无需重复结束保存。", flush=True)
        emit_status(before, machine=False)
        raise SystemExit(0)
    if ACTION == "cancel" and before not in MAPPING:
        print(f"[INFO] 当前不在建图中，无需取消。状态：{status_text(before)}（{before}）", flush=True)
        emit_status(before, machine=False)
        raise SystemExit(0)

    print(f"[INFO] 正在发送{LABELS[ACTION]}请求...", flush=True)
    _resp, frame = request_once(sock, frame, ACTION_FUNC, ACTION_VALUE, wait_seconds=8, log_response=False)
    print(f"[INFO] {LABELS[ACTION]}请求已确认。", flush=True)
    deadline = time.time() + MONITOR_SECONDS
    last = None
    while time.time() < deadline:
        status, frame = query_mapping_status(sock, frame)
        if status != last and status is not None:
            print_user_status(status, ACTION)
            last = status
        if status in TARGETS:
            emit_status(status, machine=False)
            raise SystemExit(0)
        if status in ERROR:
            emit_status(status, machine=False)
            raise SystemExit(7)
        time.sleep(POLL_SECONDS)

    print(f"[ERROR] {LABELS[ACTION]}等待状态超时，最后状态：{status_text(last)}（{last}）", flush=True)
    emit_status(last, machine=False)
    raise SystemExit(8)
finally:
    try:
        send_close(sock)
    except Exception:
        pass
    try:
        sock.close()
    except Exception:
        pass
'''


def alg_mapping_action_inner(action: str, timeout_seconds: int = 90) -> str:
    timeout_seconds = max(3, min(int(timeout_seconds), 300))
    return (
        f"{stale_app_ws_cleanup_shell()}"
        f"python3 -c {quote(_alg_mapping_python())} {quote(action)} {timeout_seconds}"
    )


def alg_mapping_inner(profile: ProductProfile, action: str, timeout_seconds: int = 90) -> str:
    return f"{remote_env(profile)}; {alg_mapping_action_inner(action, timeout_seconds)} || exit $?"


def alg_mapping_status_inner(profile: ProductProfile) -> str:
    return alg_mapping_inner(profile, "status", 5)


def _map_file_summary_inner(save_map_path: str) -> str:
    root = save_map_path.rstrip("/")
    history_root = history_map_path(save_map_path)
    return (
        f"DF_TARGET={quote(root)}; [ -e \"$DF_TARGET\" ] || DF_TARGET=$(dirname \"$DF_TARGET\"); "
        "DF_LINE=$(df -B1 --output=avail,size,pcent,target \"$DF_TARGET\" 2>/dev/null | awk 'NR==2{print $1\" \"$2\" \"$3\" \"$4}'); "
        "if [ -n \"$DF_LINE\" ]; then "
        "set -- $DF_LINE; "
        "echo DISK_AVAILABLE=$1; echo DISK_SIZE=$2; echo DISK_USED_PERCENT=$3; echo DISK_TARGET=$4; "
        "fi; "
        f"CURRENT_MAP_COUNT=0; [ -s {quote(root + '/map.pgm')} ] && [ -s {quote(root + '/map.yaml')} ] && CURRENT_MAP_COUNT=1; "
        f"HISTORY_MAP_COUNT=$(find {quote(history_root)} -maxdepth 3 -type f -name 'map.pgm' -size +0c 2>/dev/null | while IFS= read -r pgm; do dir=$(dirname \"$pgm\"); [ -s \"$dir/map.yaml\" ] && echo \"$pgm\"; done | wc -l); "
        "MAP_COUNT=$HISTORY_MAP_COUNT; "
        f"LATEST_MAP_LINE=$( ( [ -s {quote(root + '/map.pgm')} ] && [ -s {quote(root + '/map.yaml')} ] && printf '%s %s\\n' \"$(stat -c %Y {quote(root + '/map.pgm')} 2>/dev/null)\" {quote(root + '/map.pgm')}; "
        f"find {quote(history_root)} -maxdepth 3 -type f -name 'map.pgm' -size +0c -printf '%T@ %p\\n' 2>/dev/null ) | "
        "while IFS= read -r line; do pgm=${line#* }; dir=$(dirname \"$pgm\"); [ -s \"$dir/map.yaml\" ] && printf '%s\\n' \"$line\"; done | sort -nr | head -1); "
        "LATEST_MAP_TS=${LATEST_MAP_LINE%% *}; "
        "LATEST_MAP=${LATEST_MAP_LINE#* }; "
        "if [ -n \"$LATEST_MAP_TS\" ] && [ \"$LATEST_MAP\" != \"$LATEST_MAP_LINE\" ]; then "
        "LATEST_MAP_AGE=$(awk -v now=$(date +%s) -v ts=\"$LATEST_MAP_TS\" 'BEGIN{age=now-ts; if (age < 0) age=0; printf \"%d\", age}'); "
        "else LATEST_MAP=; LATEST_MAP_AGE=; fi; "
        "echo MAP_COUNT=$MAP_COUNT; "
        "echo LATEST_MAP=$LATEST_MAP; "
        "echo LATEST_MAP_TS=$LATEST_MAP_TS; "
        "echo LATEST_MAP_AGE=$LATEST_MAP_AGE"
    )


def alg_probe_status_command(profile: ProductProfile, save_map_path: str) -> str:
    inner = (
        f"{remote_env(profile)}; "
        f"{alg_mapping_action_inner('status', 5)} || exit $?; "
        f"{_map_file_summary_inner(save_map_path)}"
    )
    return ssh_command(profile, inner)


def _wait_saved_map_stable_inner(save_map_path: str) -> str:
    history_root = history_map_path(save_map_path)
    return (
        "echo '[INFO] 正在确认地图文件落盘，请稍候...'; "
        "LATEST_MAP=; "
        "for i in $(seq 1 30); do "
        f"LATEST_MAP=$(find {quote(history_root)} -maxdepth 3 -type f -name 'map.pgm' -printf '%T@ %p\\n' 2>/dev/null | awk -v start=\"$START_TS\" '$1 >= start {{print}}' | sort -nr | head -1 | cut -d' ' -f2-); "
        "[ -n \"$LATEST_MAP\" ] && break; "
        "sleep 1; "
        "done; "
        "if [ -z \"$LATEST_MAP\" ]; then "
        f"LAST_KNOWN_MAP=$(find {quote(history_root)} -maxdepth 3 -type f -name 'map.pgm' -printf '%T@ %p\\n' 2>/dev/null | sort -nr | head -1 | cut -d' ' -f2-); "
        "echo '[ERROR] alg 已返回保存完成，但未找到本次新落盘的 map.pgm'; "
        "if [ -n \"$LAST_KNOWN_MAP\" ]; then echo '[INFO] 历史最新地图仍是: '\"$LAST_KNOWN_MAP\"; fi; "
        "exit 10; "
        "fi; "
        "LATEST_DIR=$(dirname \"$LATEST_MAP\" 2>/dev/null || true); "
        "LAST_SIG=; STABLE_COUNT=0; "
        "if [ -n \"$LATEST_DIR\" ] && [ -d \"$LATEST_DIR\" ]; then "
        "for i in $(seq 1 20); do "
        "SIG=$(find \"$LATEST_DIR\" -maxdepth 2 -type f "
        "\\( -name 'map.pgm' -o -name 'map.yaml' -o -name 'map.pcd' -o -name 'map.txt' "
        "-o -name 'metadata.yaml' -o -name '*.db3' -o -name 'static_map.txt' -o -name 'key_frame_id.txt' \\) "
        "-printf '%p %s %T@\\n' 2>/dev/null | sort); "
        "if [ -n \"$SIG\" ] && [ \"$SIG\" = \"$LAST_SIG\" ]; then STABLE_COUNT=$((STABLE_COUNT + 1)); "
        "else STABLE_COUNT=0; LAST_SIG=\"$SIG\"; fi; "
        "[ \"$STABLE_COUNT\" -ge 2 ] && break; "
        "sleep 1; "
        "done; "
        "fi; "
        "echo '[INFO] 地图已保存：'\"$LATEST_MAP\""
    )


def alg_start_mapping_command(
    profile: ProductProfile,
    sensor_type: str,
    save_map_path: str,
    calibration_file_path: str,
    arc_calibration_file_path: str,
) -> CommandSpec:
    del sensor_type, arc_calibration_file_path
    inner = (
        f"mkdir -p {quote(save_map_path)}; "
        f"if [ ! -f {quote(calibration_file_path)} ]; then "
        f"printf '%s\\n' {quote(f'[ERROR] calibration file missing: {calibration_file_path}')}; exit 2; "
        "fi; "
        f"{alg_mapping_inner(profile, 'start', 90)}; "
        "echo '[INFO] 建图已开始，请移动机器人采集环境。'"
    )
    return CommandSpec(
        "开始建图",
        ssh_command(profile, inner),
        display_command="执行：alg 开始建图",
        concurrency="parallel",
        locks=("mapping", "app_ws"),
    )


def alg_finish_mapping_command(profile: ProductProfile, save_map_path: str) -> CommandSpec:
    history_root = history_map_path(save_map_path)
    inner = (
        f"mkdir -p {quote(history_root)}; "
        "START_TS=$(date +%s); "
        f"{alg_mapping_inner(profile, 'finish', 180)}; "
        f"{_wait_saved_map_stable_inner(save_map_path)}; "
        "echo '[INFO] 建图保存完成，可以进入导航。'"
    )
    return CommandSpec(
        "结束并保存建图",
        ssh_command(profile, inner),
        display_command="执行：alg 结束保存建图",
        concurrency="parallel",
        locks=("mapping", "app_ws"),
    )


def alg_cancel_mapping_command(profile: ProductProfile) -> CommandSpec:
    inner = (
        f"{alg_mapping_inner(profile, 'cancel', 45)}; "
        "echo '[INFO] 建图已取消，当前地图结果已放弃。'"
    )
    return CommandSpec(
        "取消建图",
        ssh_command(profile, inner),
        dangerous=True,
        display_command="执行：alg 取消建图",
        concurrency="parallel",
        locks=("mapping", "app_ws"),
    )
