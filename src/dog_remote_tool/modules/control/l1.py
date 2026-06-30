from __future__ import annotations

from dog_remote_tool.core.profiles import ProductProfile
from dog_remote_tool.core.shell import CommandSpec, echo_message
import dog_remote_tool.modules.control.l1_actions as _actions
import dog_remote_tool.modules.control.l1_config as _config
import dog_remote_tool.modules.control.l1_setup as _setup
from dog_remote_tool.modules.control.l1_stream import build_l1_sdk_stream_command
from dog_remote_tool.modules.control.shared import l1_control_profile, ssh_bash_stdin_command


L1_LOCAL_SDK_PATH = _config.L1_LOCAL_SDK_PATH
L1_DEFAULT_REMOTE_SDK_PATH = _config.L1_DEFAULT_REMOTE_SDK_PATH
L1_SDK_MODES = _config.L1_SDK_MODES
L1_SDK_ACTIONS = _config.L1_SDK_ACTIONS
l1_sdk_mode = _config.l1_sdk_mode
_l1_clamp = _config.l1_clamp
l1_sdk_prepare_command = _setup.l1_sdk_prepare_command
l1_sdk_prepare_auto_command = _setup.l1_sdk_prepare_auto_command
l1_sdk_deploy_command = _setup.l1_sdk_deploy_command
l1_sdk_basic_action_command = _actions.l1_sdk_basic_action_command


def _l1_python_command(
    profile: ProductProfile,
    mode_key: str,
    remote_path: str,
    title: str,
    body: str,
    *,
    dangerous: bool = False,
    timeout_hint: str = "",
) -> CommandSpec:
    target = l1_control_profile(profile)
    if target is None:
        return CommandSpec("L1 SDK 遥控", "echo '[ERROR] 当前设备不是小狗一代，无法使用 L1 SDK 遥控。'", dangerous=False)
    mode = l1_sdk_mode(mode_key)
    sdk_root = (remote_path or L1_DEFAULT_REMOTE_SDK_PATH).strip().rstrip("/") or L1_DEFAULT_REMOTE_SDK_PATH
    py = f"""
import os
import platform
import sys
import time

sdk_root = {sdk_root!r}
lib_subdir = {mode["lib_subdir"]!r}
module_name = {mode["module_name"]!r}
robot_ip = {target.host!r}
arch = platform.machine().replace("amd64", "x86_64").replace("arm64", "aarch64")
lib_path = os.path.join(sdk_root, "lib", lib_subdir, arch)
print("sdk_root=", sdk_root)
print("lib_path=", lib_path)
if not os.path.isdir(lib_path):
    raise SystemExit(f"[ERROR] SDK lib 目录不存在: {{lib_path}}")
sys.path.insert(0, lib_path)
sdk = __import__(module_name)
print("python_import=PASS", module_name)
app = sdk.HighLevel()
init_ret = app.initRobot(robot_ip, 43988, robot_ip)
print("init=", init_ret)
time.sleep(0.8)
{body.strip()}
"""
    script = f"""
set -e
python3 - <<'DOG_REMOTE_L1_SDK_PY'
{py.rstrip()}
DOG_REMOTE_L1_SDK_PY
"""
    display = f"执行：{title}（{mode['label']}）"
    if timeout_hint:
        display += f"；{timeout_hint}"
    return CommandSpec(
        title,
        ssh_bash_stdin_command(target, script),
        dangerous=dangerous,
        display_command=display,
    )


def l1_sdk_status_command(profile: ProductProfile, mode_key: str, remote_path: str) -> CommandSpec:
    body = r"""
def call_optional(name):
    if hasattr(app, name):
        try:
            print(f"{name}=", getattr(app, name)())
        except Exception as exc:
            print(f"{name}=ERROR {exc}")

call_optional("checkConnect")
call_optional("checkConnection")
call_optional("getBatteryPower")
call_optional("getCurrentCtrlmode")
print("verify=PASS")
"""
    return _l1_python_command(profile, mode_key, remote_path, "L1 SDK 检查", body)


def l1_sdk_action_command(profile: ProductProfile, mode_key: str, remote_path: str, action: str) -> CommandSpec:
    if action == "status":
        return l1_sdk_status_command(profile, mode_key, remote_path)
    if action not in L1_SDK_ACTIONS:
        return CommandSpec("L1 SDK 动作", echo_message(f"[ERROR] 未知动作: {action}"), dangerous=False)
    mode = l1_sdk_mode(mode_key)
    label, dangerous = L1_SDK_ACTIONS[action]
    if action == "crawl_mode":
        if not mode.get("crawl"):
            return CommandSpec("L1 SDK crawl", "echo '[ERROR] 当前 zsl-1 点足模式不支持 crawl，请切换到 zsl-1w 轮足。'", dangerous=False)
        body = r"""
print("action=crawl_mode")
if hasattr(app, "standUp"):
    print("standUp=", app.standUp())
    time.sleep(3.0)
print("crawl=", app.crawl(0.15, 0.0, 0.0))
time.sleep(1.5)
if hasattr(app, "cancelCrawl"):
    print("cancelCrawl=", app.cancelCrawl())
print("action_done=PASS")
"""
    else:
        body = f"""
action_name = {action!r}
if not hasattr(app, action_name):
    raise SystemExit(f"[ERROR] SDK 不支持动作: {{action_name}}")
ret = getattr(app, action_name)()
print("action=", action_name)
print("action_ret=", ret)
print("action_done=PASS")
"""
    return _l1_python_command(profile, mode_key, remote_path, f"L1 SDK {label}", body, dangerous=dangerous)


def l1_sdk_move_command(
    profile: ProductProfile,
    mode_key: str,
    remote_path: str,
    vx: float,
    vy: float,
    yaw: float,
    duration: float,
) -> CommandSpec:
    mode = l1_sdk_mode(mode_key)
    vx = _l1_clamp(vx, float(mode["vx_max"]))
    vy = _l1_clamp(vy, float(mode["vy_max"]))
    yaw = _l1_clamp(yaw, float(mode["yaw_max"]))
    duration = max(0.05, min(float(duration), 5.0))
    body = f"""
vx = {vx:.4f}
vy = {vy:.4f}
yaw = {yaw:.4f}
duration = {duration:.3f}
print("move_target=", f"vx={{vx:.3f}}, vy={{vy:.3f}}, yaw={{yaw:.3f}}, duration={{duration:.2f}}")
ret = app.move(vx, vy, yaw)
print("move_ret=", ret)
time.sleep(duration)
stop_ret = app.move(0.0, 0.0, 0.0)
print("stop_ret=", stop_ret)
print("move_done=PASS")
"""
    return _l1_python_command(
        profile,
        mode_key,
        remote_path,
        "L1 SDK 短时移动",
        body,
        dangerous=True,
        timeout_hint=f"vx={vx:.2f}, vy={vy:.2f}, yaw={yaw:.2f}, {duration:.2f}s",
    )


def l1_sdk_stream_command(profile: ProductProfile, remote_path: str, speed_percent: int = 35, interval_ms: int = 20) -> str:
    target = l1_control_profile(profile)
    if target is None:
        return "echo '[ERROR] 当前设备不是小狗一代，无法使用 L1 SDK 键盘遥控。'; exit 2"
    sdk_root = (remote_path or L1_DEFAULT_REMOTE_SDK_PATH).strip().rstrip("/") or L1_DEFAULT_REMOTE_SDK_PATH
    percent_limit = max(5, min(abs(int(speed_percent)), 100))
    interval = max(0.02, min(float(interval_ms) / 1000.0, 0.10))
    return build_l1_sdk_stream_command(target, sdk_root, percent_limit, interval)
