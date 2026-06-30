from __future__ import annotations

from dog_remote_tool.core.profiles import ProductProfile
from dog_remote_tool.core.shell import CommandSpec, echo_message
from dog_remote_tool.modules.control.l1_config import L1_DEFAULT_REMOTE_SDK_PATH
from dog_remote_tool.modules.control.shared import l1_control_profile, ssh_bash_stdin_command


def l1_sdk_basic_action_command(profile: ProductProfile, remote_path: str, action: str) -> CommandSpec:
    target = l1_control_profile(profile)
    if target is None:
        return CommandSpec("L1 SDK 动作", "echo '[ERROR] 当前设备不是小狗一代。'", dangerous=False)
    labels = {
        "status": ("状态检查", "status", False),
        "neutral": ("停止移动", "move_stop", False),
        "stand": ("站立", "standUp", False),
        "low": ("低姿态", "lieDown", False),
        "lie": ("低姿态", "lieDown", False),
        "crawl": ("匍匐", "crawl", True),
        "passive": ("阻尼趴下", "passive", True),
    }
    if action not in labels:
        return CommandSpec("L1 SDK 动作", echo_message(f"[ERROR] 未知动作: {action}"), dangerous=False)
    label, sdk_action, dangerous = labels[action]
    sdk_root = (remote_path or L1_DEFAULT_REMOTE_SDK_PATH).strip().rstrip("/") or L1_DEFAULT_REMOTE_SDK_PATH
    remote_py = f"""
import os
import platform
import subprocess
import sys
import tempfile
import time

sdk_root = {sdk_root!r}
robot_ip = {target.host!r}
arch = platform.machine().replace("amd64", "x86_64").replace("arm64", "aarch64")
base_candidates = [
    ("zsl-1", "mc_sdk_zsl_1_py"),
    ("zsl-1w", "mc_sdk_zsl_1w_py"),
]

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
        print(output, end="" if output.endswith("\\n") else "\\n")
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
    print("sdk_preferred=", preferred)
    return ordered

last_error = None
app = None
selected = None
init_output = ""
for lib_subdir, module_name in ordered_candidates():
    lib_path = os.path.join(sdk_root, "lib", lib_subdir, arch)
    if not os.path.isdir(lib_path):
        last_error = f"{{lib_path}} 不存在"
        continue
    sys.path.insert(0, lib_path)
    try:
        sdk = __import__(module_name)
        app = sdk.HighLevel()
        _init_ret, init_output = call_with_native_output(lambda: app.initRobot(robot_ip, 43988, robot_ip))
        if "dismatch" in init_output.lower():
            last_error = f"{{lib_subdir}} SDK 型号不匹配"
            app = None
            continue
        selected = lib_subdir
        break
    except Exception as exc:
        last_error = exc
        app = None
if app is None:
    raise SystemExit(f"[ERROR] L1 SDK 初始化失败: {{last_error}}")
print("sdk_selected=", selected)
time.sleep(0.5)
action = {sdk_action!r}
action_output = ""
def call_optional(name):
    if hasattr(app, name):
        return call_with_native_output(lambda: getattr(app, name)())[0]
    return None

def current_ctrl_mode():
    if not hasattr(app, "getCurrentCtrlmode"):
        return None
    try:
        value, _output = call_with_native_output(lambda: app.getCurrentCtrlmode())
        return int(value)
    except Exception:
        return None

def wait_sdk_connected(timeout=6.0):
    if not hasattr(app, "checkConnect"):
        return True
    start = time.time()
    while time.time() - start < timeout:
        try:
            value, _output = call_with_native_output(lambda: app.checkConnect())
            if value:
                return True
        except Exception:
            pass
        time.sleep(0.5)
    return False

if action == "status":
    for name in ("checkConnect", "checkConnection", "getBatteryPower", "getCurrentCtrlmode"):
        if hasattr(app, name):
            value, _output = call_with_native_output(lambda n=name: getattr(app, n)())
            print(f"{{name}}=", value)
    ret = 0
elif not wait_sdk_connected():
    raise SystemExit("[ERROR] L1 SDK 连接超时，未建立有效控制会话")
elif action == "move_stop":
    ret, action_output = call_with_native_output(lambda: app.move(0.0, 0.0, 0.0))
    print("move_stop=", ret)
elif action == "standUp":
    mode = current_ctrl_mode()
    if mode in (1, 3):
        print(f"already_stand_ctrl_mode={{mode}}")
        ret = 0
        action_output = ""
    else:
        call_optional("cancelCrawl")
        call_optional("cancelTwoLegStand")
        print("action=", action)
        ret, action_output = call_with_native_output(lambda: app.standUp())
        print("action_ret=", ret)
elif action == "crawl":
    if not hasattr(app, "crawl"):
        raise SystemExit(f"[ERROR] 当前 SDK 型号不支持匍匐 crawl: {{selected}}")
    mode = current_ctrl_mode()
    if mode not in (1, 3):
        call_optional("standUp")
        time.sleep(1.5)
    else:
        print(f"already_stand_ctrl_mode={{mode}}")
    print("action=", action)
    ret, action_output = call_with_native_output(lambda: app.crawl(0.0, 0.0, 0.0))
    print("action_ret=", ret)
else:
    if not hasattr(app, action):
        raise SystemExit(f"[ERROR] SDK 不支持动作: {{action}}")
    print("action=", action)
    ret, action_output = call_with_native_output(lambda: getattr(app, action)())
    print("action_ret=", ret)
if "dismatch" in action_output.lower():
    raise SystemExit(f"[ERROR] SDK 型号不匹配，动作未确认执行: {{selected}}")
if ret not in (0, None):
    raise SystemExit(f"[ERROR] SDK 动作返回失败: {{ret}}")
print("action_done=PASS")
"""
    script = f"""
set -e
python3 - <<'DOG_REMOTE_L1_ACTION_PY'
{remote_py.rstrip()}
DOG_REMOTE_L1_ACTION_PY
"""
    return CommandSpec(
        f"L1 SDK {label}",
        ssh_bash_stdin_command(target, script),
        dangerous=dangerous,
        display_command=f"执行：L1 SDK {label}",
    )
