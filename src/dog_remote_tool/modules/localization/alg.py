from __future__ import annotations

from pathlib import PurePosixPath

from dog_remote_tool.core.profiles import ProductProfile
from dog_remote_tool.core.shell import echo_message, quote, remote_env
from dog_remote_tool.modules.arc_app_ws import common_arc_app_ws_python, stale_app_ws_cleanup_shell


def map_id_from_map_pcd_path(map_pcd_path: str) -> str:
    path = PurePosixPath(map_pcd_path.strip())
    if path.name in {"map.pcd", "map.pgm", "map.yaml"} and path.parent.name:
        return path.parent.name
    return path.name or map_pcd_path.strip()


def map_yaml_from_map_pcd_path(map_pcd_path: str) -> str:
    if map_pcd_path.endswith(".pcd"):
        return map_pcd_path[:-4] + ".yaml"
    return map_pcd_path


def _current_map_history_root(map_pcd_path: str) -> str:
    path = PurePosixPath(map_pcd_path.strip())
    if path.name in {"map.pcd", "map.pgm", "map.yaml"} and path.parent.name == "map":
        return str(path.parent / "history_map")
    return ""


def _alg_localization_python() -> str:
    return common_arc_app_ws_python() + r'''
MAP_ID = sys.argv[1]
TIMEOUT_SECONDS = int(sys.argv[2])
DOG_REMOTE_LOC_MAP_MARKER = "/tmp/dog_remote_localization_map_id"


sock = connect_ws()
frame = 1
start = time.monotonic()


def read_loc_status(required=False, log_response=False):
    global frame
    try:
        resp, frame = request_once(
            sock,
            frame,
            "get_loc_status",
            wait_seconds=2,
            required=required,
            log_response=log_response,
        )
    except Exception as exc:
        if required:
            raise
        print(f"[WARN] get_loc_status 状态回读失败: {exc}", flush=True)
        return None
    return None if resp is None else resp.get("data")


def load_map_with_recovery():
    global frame
    before = read_loc_status(required=False, log_response=False)
    try:
        with open(DOG_REMOTE_LOC_MAP_MARKER, "r", encoding="utf-8") as marker_file:
            marked_map_id = marker_file.read().strip()
    except Exception:
        marked_map_id = ""
    if marked_map_id == MAP_ID and is_location_continuous(before):
        print(f"[INFO] 当前地图已连续定位，跳过重复 loc_load_map: map_id={MAP_ID}", flush=True)
        return

    try:
        resp, frame = request_once(
            sock,
            frame,
            "loc_load_map",
            MAP_ID,
            label="alg定位地图加载",
            wait_seconds=8,
            required=False,
            log_response=True,
        )
    except Exception as exc:
        print(f"[WARN] alg定位地图加载请求异常: {exc}", flush=True)
        raise SystemExit(7)
    status = None if resp is None else resp.get("status")
    msg = "" if resp is None else str(resp.get("msg") or "")
    if status in (None, "ok"):
        return
    print(f"[ERROR] alg定位地图加载请求失败: status={status} msg={msg}", flush=True)
    raise SystemExit(6)


try:
    load_map_with_recovery()
    deadline = time.time() + TIMEOUT_SECONDS
    last_loc = None
    while time.time() < deadline:
        loc_status = read_loc_status(required=False, log_response=False)
        if loc_status != last_loc:
            print(f"[INFO] alg定位状态: {loc_status}", flush=True)
            last_loc = loc_status
        if is_location_continuous(loc_status):
            try:
                with open(DOG_REMOTE_LOC_MAP_MARKER, "w", encoding="utf-8") as marker_file:
                    marker_file.write(MAP_ID + "\n")
            except Exception:
                pass
            print(f"[INFO] alg定位已进入连续定位状态: map_id={MAP_ID} elapsed={time.monotonic() - start:.1f}s", flush=True)
            raise SystemExit(0)
        if str(loc_status).strip().lower() in {"failed", "failure", "locfailed", "error"}:
            print(f"[ERROR] alg定位失败: {loc_status}", flush=True)
            raise SystemExit(5)
        time.sleep(0.25)
    print(f"[ERROR] alg定位等待连续定位超时: map_id={MAP_ID} elapsed={time.monotonic() - start:.1f}s", flush=True)
    raise SystemExit(8)
finally:
    try:
        sock.close()
    except Exception:
        pass
'''


def alg_loc_status_inner() -> str:
    python = common_arc_app_ws_python() + r'''
sock = connect_ws()
try:
    resp, _frame = request_once(sock, 1, "get_loc_status", wait_seconds=2, required=True, log_response=False)
    value = "" if resp is None else str(resp.get("data") or "")
    print(f"ALG_LOC_STATUS={value}", flush=True)
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
    return f"{stale_app_ws_cleanup_shell()}python3 -c {quote(python)}"


def alg_localization_load_inner(
    profile: ProductProfile,
    map_pcd_path: str,
    timeout_seconds: int = 45,
) -> str:
    timeout_seconds = max(5, min(int(timeout_seconds), 90))
    map_id = map_id_from_map_pcd_path(map_pcd_path)
    map_yaml_path = map_yaml_from_map_pcd_path(map_pcd_path)
    history_root = _current_map_history_root(map_pcd_path)
    resolve_map_id = f"DOG_REMOTE_LOC_MAP_ID={quote(map_id)}; "
    if history_root:
        resolve_map_id += (
            f"DOG_REMOTE_LOC_HISTORY_ROOT={quote(history_root)}; "
            "if [ \"$DOG_REMOTE_LOC_MAP_ID\" = map ] && [ -d \"$DOG_REMOTE_LOC_HISTORY_ROOT\" ]; then "
            "DOG_REMOTE_LOC_HISTORY_DIR=$(find \"$DOG_REMOTE_LOC_HISTORY_ROOT\" -mindepth 2 -maxdepth 2 -type f -name map.pcd "
            "-printf '%T@ %h\\n' 2>/dev/null | while IFS= read -r line; do "
            "dir=${line#* }; [ -s \"$dir/map.yaml\" ] && printf '%s\\n' \"$line\"; "
            "done | sort -nr | head -1 | cut -d' ' -f2-); "
            "if [ -n \"$DOG_REMOTE_LOC_HISTORY_DIR\" ]; then "
            "DOG_REMOTE_LOC_MAP_ID=$(basename \"$DOG_REMOTE_LOC_HISTORY_DIR\"); "
            "echo '[INFO] 当前地图副本对应 history map_id: '\"$DOG_REMOTE_LOC_MAP_ID\"; "
            "fi; "
            "fi; "
        )
    return (
        "dog_remote_alg_localization_load() { "
        f"{remote_env(profile)}; "
        "source /opt/robot/robot_nav/install/setup.bash >/dev/null 2>&1 || true; "
        f"{stale_app_ws_cleanup_shell()}"
        f"if [ ! -s {quote(map_pcd_path)} ]; then {echo_message(f'[ERROR] 地图 PCD 不存在或为空: {map_pcd_path}')}; return 2; fi; "
        f"if [ ! -f {quote(map_yaml_path)} ]; then {echo_message(f'[ERROR] 当前地图 map.yaml 不存在: {map_yaml_path}')}; return 2; fi; "
        f"{resolve_map_id}"
        "echo '[INFO] 使用系统应用通道加载定位地图: '\"$DOG_REMOTE_LOC_MAP_ID\"; "
        f"python3 -c {quote(_alg_localization_python())} \"$DOG_REMOTE_LOC_MAP_ID\" {timeout_seconds}; "
        "}; "
        "dog_remote_alg_localization_load"
    )
