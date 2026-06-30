from __future__ import annotations


L1_STREAM_REMOTE_PY = r"""
import json
import os
import platform
import queue
import subprocess
import sys
import tempfile
import threading
import time

sdk_root = os.environ["DOG_REMOTE_L1_SDK_ROOT"]
robot_ip = os.environ["DOG_REMOTE_L1_ROBOT_IP"]
interval = float(os.environ.get("DOG_REMOTE_L1_INTERVAL", "0.02"))
percent_limit = max(5, min(100, int(os.environ.get("DOG_REMOTE_L1_PERCENT_LIMIT", "35"))))
arch = platform.machine().replace("amd64", "x86_64").replace("arm64", "aarch64")
base_candidates = [
    ("zsl-1", "mc_sdk_zsl_1_py", 3.0, 1.0, 3.0),
    ("zsl-1w", "mc_sdk_zsl_1w_py", 3.7, 1.0, 3.0),
]

def emit(payload):
    print(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), flush=True)

def call_with_native_output(func):
    fd = sys.stdout.fileno()
    saved_fd = os.dup(fd)
    tmp = tempfile.TemporaryFile()
    error = None
    result = None
    try:
        os.dup2(tmp.fileno(), fd)
        try:
            result = func()
        except BaseException as exc:
            error = exc
        finally:
            sys.stdout.flush()
            os.dup2(saved_fd, fd)
    finally:
        os.close(saved_fd)
    tmp.seek(0)
    output = tmp.read().decode("utf-8", errors="replace")
    tmp.close()
    if output:
        for line in output.splitlines():
            emit({"type": "log", "message": line})
    if error is not None:
        raise error
    return result, output

def ordered_candidates():
    try:
        ps_text = subprocess.check_output(["ps", "-eo", "args"], text=True, errors="replace")
    except Exception:
        ps_text = ""
    lower = ps_text.lower()
    preferred = "zsl-1w" if any(marker in lower for marker in ("start_motion_control_xgw", "xgwhspd", "zsl-1w")) else "zsl-1"
    ordered = [item for item in base_candidates if item[0] == preferred]
    ordered.extend(item for item in base_candidates if item[0] != preferred)
    emit({"type": "log", "message": f"sdk_preferred={preferred}"})
    return ordered

last_error = None
app = None
selected = None
limits = (3.0, 1.0, 3.0)
for lib_subdir, module_name, vx_max, vy_max, yaw_max in ordered_candidates():
    lib_path = os.path.join(sdk_root, "lib", lib_subdir, arch)
    if not os.path.isdir(lib_path):
        last_error = f"{lib_path} 不存在"
        continue
    sys.path.insert(0, lib_path)
    try:
        sdk = __import__(module_name)
        app = sdk.HighLevel()
        _init_ret, init_output = call_with_native_output(lambda: app.initRobot(robot_ip, 43988, robot_ip))
        if "dismatch" in init_output.lower():
            last_error = f"{lib_subdir} SDK 型号不匹配"
            app = None
            continue
        selected = {"model": lib_subdir, "module": module_name, "lib_path": lib_path}
        limits = (vx_max, vy_max, yaw_max)
        break
    except Exception as exc:
        last_error = str(exc)
        app = None

if app is None:
    emit({"type": "error", "message": f"L1 SDK 初始化失败: {last_error}"})
    raise SystemExit(2)

commands = queue.Queue()
running = True
target = {"vx": 0.0, "vy": 0.0, "yaw": 0.0}
last_sent = None
stand_ready = False
last_telemetry = 0.0
move_lock = threading.Lock()
ready_ctrl_modes = (1, 3, 18)

def reader():
    global running
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            commands.put(json.loads(line))
        except Exception as exc:
            emit({"type": "error", "message": str(exc)})
    running = False

def iter_pending_commands():
    while not commands.empty():
        try:
            yield commands.get_nowait()
        except queue.Empty:
            return

def clamp(value, limit):
    return max(-limit, min(limit, float(value)))

def direction(value):
    value = float(value)
    if value > 0.0:
        return 1.0
    if value < 0.0:
        return -1.0
    return 0.0

def command_speed(command, key, fallback):
    try:
        return abs(float(command[key])) if key in command else fallback
    except Exception:
        return fallback

def set_target(command):
    vx_max, vy_max, yaw_max = limits
    forward = command.get("forward", 0)
    strafe = command.get("strafe", 0)
    turn = command.get("turn", 0)
    if "linear_speed" in command or "angular_speed" in command:
        linear_limit = min(command_speed(command, "linear_limit_mps", 3.0), vx_max)
        angular_limit = min(command_speed(command, "angular_limit_radps", 3.0), yaw_max)
        linear_speed = min(command_speed(command, "linear_speed", 0.0), linear_limit)
        angular_speed = min(command_speed(command, "angular_speed", 0.0), angular_limit)
        target["vx"] = clamp(direction(forward) * linear_speed, vx_max)
        target["vy"] = clamp(direction(strafe) * min(linear_speed, vy_max), vy_max)
        target["yaw"] = clamp(direction(turn) * angular_speed, yaw_max)
        return
    scale = percent_limit / 100.0
    target["vx"] = clamp(float(forward) / 100.0 * vx_max * scale, vx_max)
    target["vy"] = clamp(float(strafe) / 100.0 * vy_max * scale, vy_max)
    target["yaw"] = clamp(float(turn) / 100.0 * yaw_max * scale, yaw_max)

def read_ctrl_mode():
    if not hasattr(app, "getCurrentCtrlmode"):
        return None
    try:
        return int(app.getCurrentCtrlmode())
    except Exception:
        return None

def wait_sdk_connected(timeout=6.0):
    if not hasattr(app, "checkConnect"):
        return True
    start = time.time()
    while time.time() - start < timeout:
        try:
            if app.checkConnect():
                return True
        except Exception:
            pass
        time.sleep(0.5)
    return False

def is_stand_ready_mode(mode):
    return mode in ready_ctrl_modes

def wait_stand_transition():
    start = time.time()
    last_mode = None
    while time.time() - start < 3.5:
        time.sleep(0.25)
        last_mode = read_ctrl_mode()
        if is_stand_ready_mode(last_mode) and time.time() - start >= 1.5:
            break
    elapsed = time.time() - start
    if elapsed < 2.8:
        time.sleep(2.8 - elapsed)
    ready = last_mode is None or is_stand_ready_mode(last_mode)
    prefix = "stand_ready" if ready else "stand_not_ready"
    emit({"type": "log", "message": f"{prefix} ctrl_mode={last_mode if last_mode is not None else '-'}"})
    return ready, last_mode

def ensure_stand():
    global stand_ready
    if stand_ready:
        return None
    current_mode = read_ctrl_mode()
    if is_stand_ready_mode(current_mode):
        stand_ready = True
        emit({"type": "log", "message": f"already_stand ctrl_mode={current_mode}"})
        return None
    if not hasattr(app, "standUp"):
        raise RuntimeError("SDK 不支持动作: standUp")
    ret, output = call_with_native_output(lambda: app.standUp())
    if "dismatch" in output.lower():
        raise RuntimeError(f"SDK 型号不匹配: {selected.get('model') if selected else '-'}")
    if ret not in (0, None):
        raise RuntimeError(f"standUp 返回失败: {ret}")
    ready, last_mode = wait_stand_transition()
    if not ready:
        stand_ready = False
        raise RuntimeError(f"standUp 后控制模式仍为 {last_mode}，未进入站立/移动状态")
    stand_ready = True
    return ret

def stop_motion(strict=False):
    target.update({"vx": 0.0, "vy": 0.0, "yaw": 0.0})
    if not stand_ready:
        return None
    with move_lock:
        ret, output = call_with_native_output(lambda: app.move(0.0, 0.0, 0.0))
    if "dismatch" in output.lower():
        raise RuntimeError(f"SDK 型号不匹配: {selected.get('model') if selected else '-'}")
    if ret not in (0, None):
        if strict:
            raise RuntimeError(f"move 返回失败: {ret}")
        emit({"type": "log", "message": f"速度归零未生效 ret={ret}"})
        return ret
    return ret

def run_action(name):
    global stand_ready
    if name == "neutral":
        return stop_motion()
    sdk_name = {"stand": "standUp", "low": "lieDown", "lie": "lieDown", "passive": "passive"}.get(name)
    if not sdk_name and name != "crawl":
        raise ValueError(f"未知动作: {name}")
    if name in {"low", "lie", "passive", "crawl"}:
        stop_motion()
    if name == "stand":
        current_mode = read_ctrl_mode()
        if is_stand_ready_mode(current_mode):
            stand_ready = True
            emit({"type": "log", "message": f"already_stand ctrl_mode={current_mode}"})
            return None
        for cancel_name in ("cancelCrawl", "cancelTwoLegStand"):
            if hasattr(app, cancel_name):
                call_with_native_output(lambda n=cancel_name: getattr(app, n)())
    if name == "crawl":
        ensure_stand()
        if not hasattr(app, "crawl"):
            raise RuntimeError(f"当前 SDK 型号不支持匍匐 crawl: {selected.get('model') if selected else '-'}")
        with move_lock:
            ret, output = call_with_native_output(lambda: app.crawl(0.0, 0.0, 0.0))
        if "dismatch" in output.lower():
            raise RuntimeError(f"SDK 型号不匹配: {selected.get('model') if selected else '-'}")
        if ret not in (0, None):
            raise RuntimeError(f"crawl 返回失败: {ret}")
        stand_ready = True
        return ret
    if not hasattr(app, sdk_name):
        raise RuntimeError(f"SDK 不支持动作: {sdk_name}")
    with move_lock:
        ret, output = call_with_native_output(lambda: getattr(app, sdk_name)())
    if "dismatch" in output.lower():
        raise RuntimeError(f"SDK 型号不匹配: {selected.get('model') if selected else '-'}")
    if ret not in (0, None):
        raise RuntimeError(f"{sdk_name} 返回失败: {ret}")
    if name == "stand":
        ready, last_mode = wait_stand_transition()
        if not ready:
            stand_ready = False
            raise RuntimeError(f"standUp 后控制模式仍为 {last_mode}，未进入站立/移动状态")
        stand_ready = True
    elif name in {"low", "lie", "passive"}:
        stand_ready = False
    return ret

def safe_vector(name):
    if not hasattr(app, name):
        return None
    try:
        value = getattr(app, name)()
    except Exception:
        return None
    try:
        return [float(item) for item in value]
    except Exception:
        return None

def emit_telemetry():
    body_velocity = safe_vector("getBodyVelocity")
    world_velocity = safe_vector("getWorldVelocity")
    body_gyro = safe_vector("getBodyGyro")
    ctrl_mode = read_ctrl_mode()
    emit({
        "type": "telemetry",
        "body_velocity": body_velocity,
        "world_velocity": world_velocity,
        "body_gyro": body_gyro,
        "ctrl_mode": ctrl_mode,
    })

if not wait_sdk_connected():
    emit({"type": "error", "message": "L1 SDK 连接超时，未建立有效控制会话"})
    raise SystemExit(3)

initial_ctrl_mode = read_ctrl_mode()
stand_ready = is_stand_ready_mode(initial_ctrl_mode)
threading.Thread(target=reader, daemon=True).start()
emit({
    "type": "ready",
    "selected": selected,
    "limits": {"vx": limits[0], "vy": limits[1], "yaw": limits[2]},
    "speed_percent": percent_limit,
    "ctrl_mode": initial_ctrl_mode,
    "stand_ready": stand_ready,
})

try:
    while running:
        for command in iter_pending_commands():
            cmd = command.get("cmd")
            try:
                if cmd == "set":
                    set_target(command)
                elif cmd in {"neutral", "stand", "low", "lie", "passive", "crawl"}:
                    ret = run_action(cmd)
                    emit({"type": "result", "cmd": cmd, "ret": ret})
                    last_sent = None
                elif cmd == "quit":
                    running = False
            except Exception as exc:
                emit({"type": "error", "cmd": cmd, "message": str(exc)})

        vector = (round(target["vx"], 4), round(target["vy"], 4), round(target["yaw"], 4))
        if vector != last_sent and not stand_ready and vector != (0.0, 0.0, 0.0):
            emit({"type": "error", "message": "未进入站立/移动状态，请先点击站立或按 1"})
            last_sent = vector
        if vector != last_sent and stand_ready:
            with move_lock:
                ret, output = call_with_native_output(lambda: app.move(target["vx"], target["vy"], target["yaw"]))
            if "dismatch" in output.lower():
                emit({"type": "error", "message": f"SDK 型号不匹配: {selected.get('model') if selected else '-'}"})
                running = False
                break
            if ret not in (0, None):
                hint = "，请先点击站立或按 1" if vector != (0.0, 0.0, 0.0) else ""
                emit({"type": "error", "message": f"move 返回失败: {ret}{hint}"})
                last_sent = vector
                time.sleep(interval)
                continue
            stand_ready = True
            emit({"type": "move", "vx": vector[0], "vy": vector[1], "yaw": vector[2], "ret": ret})
            last_sent = vector
        now = time.time()
        if now - last_telemetry >= 0.5:
            emit_telemetry()
            last_telemetry = now
        time.sleep(interval)
finally:
    try:
        stop_motion()
    finally:
        emit({"type": "closed"})
"""
