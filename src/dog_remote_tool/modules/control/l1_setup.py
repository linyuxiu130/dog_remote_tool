from __future__ import annotations

import os
from pathlib import Path

from dog_remote_tool.core.network_routes import with_route_repair
from dog_remote_tool.core.profiles import ProductProfile
from dog_remote_tool.core.shell import (
    CommandSpec,
    echo_message,
    quote,
    remote_target_path,
    rsync_prefix_command,
    ssh_prefix_command,
)
from dog_remote_tool.modules.control.l1_config import L1_DEFAULT_REMOTE_SDK_PATH, L1_LOCAL_SDK_PATH, L1_SDK_MODES, l1_sdk_mode
from dog_remote_tool.modules.control.shared import l1_control_profile, ssh_bash_stdin_command


def l1_sdk_prepare_command(profile: ProductProfile, mode_key: str, remote_path: str) -> CommandSpec:
    target = l1_control_profile(profile)
    if target is None:
        return CommandSpec("L1 SDK 准备", "echo '[ERROR] 当前设备不是小狗一代。'", dangerous=False)
    mode = l1_sdk_mode(mode_key)
    sdk_root = (remote_path or L1_DEFAULT_REMOTE_SDK_PATH).strip().rstrip("/") or L1_DEFAULT_REMOTE_SDK_PATH
    lib_subdir = mode["lib_subdir"]
    module_name = mode["module_name"]
    cpp_namespace = "mc_sdk::" + lib_subdir.replace("-", "_")
    script = f"""
set -e
sdk_root={quote(sdk_root)}
lib_subdir={quote(lib_subdir)}
module_name={quote(module_name)}
arch=$(python3 -c 'import platform; print(platform.machine().replace("amd64", "x86_64").replace("arm64", "aarch64"))')
lib_dir="$sdk_root/lib/$lib_subdir/$arch"
echo "[SDK] sdk_root=$sdk_root"
echo "[SDK] lib_dir=$lib_dir"
test -d "$lib_dir"
test -n "$(find "$lib_dir" -maxdepth 1 -name '*.so' -print -quit)"
python3 -c "import sys; sys.path.insert(0, '$lib_dir'); __import__('$module_name'); print('python_import=PASS')"
cpp_dir="$sdk_root/demo/$lib_subdir/cpp"
sdk_lib="$(find "$lib_dir" -maxdepth 1 -name 'libmc_sdk*.so' -print -quit)"
if [ -n "$sdk_lib" ] && command -v g++ >/dev/null 2>&1; then
    mkdir -p "$cpp_dir/build"
    cpp_check="$cpp_dir/build/dog_remote_sdk_compile_check.cpp"
    cat > "$cpp_check" <<'EOF'
#include "{lib_subdir}/highlevel.h"

int main() {{
    {cpp_namespace}::HighLevel app;
    return 0;
}}
EOF
    g++ "$cpp_check" "$sdk_lib" -std=c++17 -I "$sdk_root/include" -I "$sdk_root/include/$lib_subdir" -pthread -o "$cpp_dir/build/dog_remote_sdk_compile_check"
    echo "cpp_build=PASS"
else
    echo "cpp_build=SKIP"
fi
echo "---sdk_config---"
grep -n 'target_ip\\|target_port' /opt/export/config/sdk_config.yaml 2>/dev/null || echo NO_SDK_CONFIG
"""
    return CommandSpec(
        "L1 SDK 远端准备",
        ssh_bash_stdin_command(target, script),
        display_command=f"执行：L1 SDK 远端准备（{mode['label']}）",
    )


def l1_sdk_prepare_auto_command(profile: ProductProfile, remote_path: str) -> CommandSpec:
    target = l1_control_profile(profile)
    if target is None:
        return CommandSpec("L1 SDK 准备", "echo '[ERROR] 当前设备不是小狗一代。'", dangerous=False)
    sdk_root = (remote_path or L1_DEFAULT_REMOTE_SDK_PATH).strip().rstrip("/") or L1_DEFAULT_REMOTE_SDK_PATH
    candidates = " ".join(f"{key}:{cfg['module_name']}" for key, cfg in L1_SDK_MODES.items())
    script = f"""
set -e
sdk_root={quote(sdk_root)}
echo "[L1 SDK] sdk_root=$sdk_root"
test -d "$sdk_root"
arch=$(python3 -c 'import platform; print(platform.machine().replace("amd64", "x86_64").replace("arm64", "aarch64"))')
echo "[L1 SDK] arch=$arch"
python3 - <<'PY'
import os
import platform
import subprocess
import sys

sdk_root = {sdk_root!r}
arch = platform.machine().replace("amd64", "x86_64").replace("arm64", "aarch64")
candidates = [
    ("zsl-1", "mc_sdk_zsl_1_py"),
    ("zsl-1w", "mc_sdk_zsl_1w_py"),
]
def preferred_model():
    try:
        ps_text = subprocess.check_output(["ps", "-eo", "args"], text=True, errors="replace")
    except Exception:
        ps_text = ""
    lower = ps_text.lower()
    if any(marker in lower for marker in ("start_motion_control_xgw", "xgwhspd", "zsl-1w")):
        return "zsl-1w"
    return "zsl-1"

preferred = preferred_model()
ok = []
for lib_subdir, module_name in candidates:
    lib_path = os.path.join(sdk_root, "lib", lib_subdir, arch)
    if not os.path.isdir(lib_path):
        print(f"{{lib_subdir}}=MISSING {{lib_path}}")
        continue
    sys.path.insert(0, lib_path)
    try:
        __import__(module_name)
    except Exception as exc:
        print(f"{{lib_subdir}}=IMPORT_ERROR {{exc}}")
    else:
        print(f"{{lib_subdir}}=PASS {{module_name}}")
        ok.append(lib_subdir)
if not ok:
    raise SystemExit("[ERROR] 没有可用的 L1 SDK Python 绑定")
print("sdk_auto_candidates=", ",".join(ok))
print("sdk_recommended=", preferred)
PY
echo "[L1 SDK] 支持候选: {candidates}"
"""
    return CommandSpec(
        "L1 SDK 准备",
        ssh_bash_stdin_command(target, script),
        display_command="执行：L1 SDK 准备",
    )


def l1_sdk_deploy_command(profile: ProductProfile, local_path: str, remote_path: str) -> CommandSpec:
    target = l1_control_profile(profile)
    if target is None:
        return CommandSpec("部署 L1 SDK", "echo '[ERROR] 当前设备不是小狗一代。'", dangerous=False)
    local_root = Path((local_path or str(L1_LOCAL_SDK_PATH)).strip()).expanduser()
    remote_root = (remote_path or L1_DEFAULT_REMOTE_SDK_PATH).strip().rstrip("/") or L1_DEFAULT_REMOTE_SDK_PATH
    remote_root_norm = os.path.normpath(remote_root)
    if remote_root_norm in {"/", "/home", "/home/firefly", "/home/robot", "/opt", "/opt/robot", "/tmp"} or not remote_root_norm.endswith("/genisom_l1_sdk"):
        return CommandSpec(
            "部署 L1 SDK",
            echo_message(f"[ERROR] 远端 SDK 目标目录不安全: {remote_root}。目标必须以 /genisom_l1_sdk 结尾。"),
            dangerous=False,
            display_command="部署 L1 SDK：目标目录不安全",
        )
    if not local_root.is_dir():
        return CommandSpec(
            "部署 L1 SDK",
            echo_message(f"[ERROR] 本地 SDK 不存在: {local_root}"),
            dangerous=False,
            display_command="部署 L1 SDK：本地 SDK 不存在",
        )
    remote_parent = os.path.dirname(remote_root) or "."
    remote_target = remote_target_path(target, remote_root.rstrip("/") + "/")
    command = (
        f"{ssh_prefix_command(target)} "
        f"{quote('mkdir -p ' + quote(remote_parent))} && "
        f"{rsync_prefix_command(target, options='-az --delete')} "
        "--exclude .git --exclude __pycache__ "
        f"{quote(str(local_root).rstrip('/') + '/')} {quote(remote_target)}"
    )
    return CommandSpec(
        "部署 L1 SDK",
        with_route_repair(target, command),
        dangerous=True,
        display_command="部署 L1 SDK",
    )
