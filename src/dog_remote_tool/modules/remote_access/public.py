from __future__ import annotations

from dog_remote_tool.core.paths import resource_path
from dog_remote_tool.core.profiles import ProductProfile
from dog_remote_tool.core.shell import (
    CommandSpec,
    echo_message,
    quote,
    scp_push_command,
    ssh_command,
    sudo_run_shell,
)
from dog_remote_tool.modules.remote_access.resources import (
    REMOTE_ACCESS_BINARY_NAME,
    REMOTE_ACCESS_RESOURCE_NAME,
    REMOTE_ACCESS_SCRIPT_NAME,
)


REMOTE_ACCESS_RESOURCE_DIR = str(resource_path(REMOTE_ACCESS_RESOURCE_NAME))
PUBLIC_SERVER = "47.102.113.200"
PUBLIC_PORT_MANAGER_PORT = "7501"
PUBLIC_FRP_SERVER_PORT = "7000"
DEFAULT_PUBLIC_SSID = ""
REMOTE_SCRIPT_INSTALL_PATH = f"/opt/robot/nx-launch/script/{REMOTE_ACCESS_SCRIPT_NAME}"
REMOTE_BINARY_INSTALL_PATH = f"/usr/local/bin/{REMOTE_ACCESS_BINARY_NAME}"


def _resource_path(name: str) -> str:
    return str(resource_path(REMOTE_ACCESS_RESOURCE_NAME, name))


def remote_access_resource_paths() -> tuple[str, str]:
    return _resource_path(REMOTE_ACCESS_SCRIPT_NAME), _resource_path(REMOTE_ACCESS_BINARY_NAME)


def default_remote_access_script_path() -> str:
    return _resource_path(REMOTE_ACCESS_SCRIPT_NAME)


def _remote_install_paths(profile: ProductProfile) -> tuple[str, str]:
    return REMOTE_SCRIPT_INSTALL_PATH, REMOTE_BINARY_INSTALL_PATH


def remote_version_shell() -> str:
    return (
        "detect_release_name() { "
        "find /etc/release -maxdepth 1 -type f -name '*.yaml' -printf '%f\\n' 2>/dev/null | sort | tail -1; "
        "}; "
        "is_new_release() { case \"$1\" in *0029*B.yaml|*003[0-9]*.yaml|*00[3-9][0-9]*.yaml) return 0 ;; *) return 1 ;; esac; }; "
        "RELEASE_FILE=$(detect_release_name); "
        "VERSION_KIND=old; "
        "if is_new_release \"$RELEASE_FILE\"; then VERSION_KIND=new; fi; "
    )


def public_server_tcp_check_shell() -> str:
    return (
        "check_public_tcp() { "
        "host=\"$1\"; port=\"$2\"; "
        "if command -v nc >/dev/null 2>&1; then "
        "nc -z -w 3 \"$host\" \"$port\" >/dev/null 2>&1; "
        "else "
        "timeout 4 bash -c \"cat < /dev/null > /dev/tcp/$host/$port\" >/dev/null 2>&1; "
        "fi; "
        "}; "
    )


def _robot_launch_state_shell() -> str:
    return (
        "launch_state=unknown; "
        "if command -v robot-launch >/dev/null 2>&1; then "
        "launch_line=$(robot-launch list 2>/dev/null | sed -r 's/\\x1B\\[[0-9;]*[A-Za-z]//g' | grep remote_access | head -1 || true); "
        "case \"$launch_line\" in *running*) launch_state=running ;; *stopped*) launch_state=stopped ;; *errored*) launch_state=errored ;; esac; "
        "fi; "
    )


def _remote_access_process_list_shell() -> str:
    return (
        "pgrep -af '(^|/)remote_access( |$)' || true; "
        "pgrep -af '(^|/)frpc( |$)' || true; "
        "pgrep -af '[s]tart_remote_access.sh' || true"
    )


def _detect_3588_hotspot_ssid_shell(var_name: str = "DETECTED_SSID") -> str:
    return (
        f"{var_name}=''; "
        "if [ -f /userdata/bak/system/hostapd.conf ]; then "
        f"{var_name}=$(awk -F= '/^ssid=/ {{print $2; exit}}' /userdata/bak/system/hostapd.conf | tr -d ' \\r\\n\\t'); "
        "fi; "
        f"if [ -z \"${var_name}\" ]; then "
        f"{var_name}=$(iwgetid -r wlan0 2>/dev/null | tr -d ' \\r\\n\\t' || true); "
        "fi; "
        f"if [ -z \"${var_name}\" ]; then "
        f"{var_name}=$(iw dev wlan0 info 2>/dev/null | awk '/ssid/ {{print $2; exit}}' | tr -d ' \\r\\n\\t'); "
        "fi; "
    )


def public_access_probe_command(profile: ProductProfile) -> str:
    inner = (
        remote_version_shell()
        + _robot_launch_state_shell()
        + f"LOG={quote(profile.home + '/remote_access.log')}; "
        "PORT=''; "
        "[ -f \"$LOG\" ] && PORT=$(grep -m1 'remotePort' \"$LOG\" | awk -F'= ' '{print $2}'); "
        "printf 'RELEASE=%s\\n' \"${RELEASE_FILE:-unknown}\"; "
        "printf 'VERSION=%s\\n' \"$VERSION_KIND\"; "
        "printf 'LAUNCH_STATE=%s\\n' \"$launch_state\"; "
        "if pgrep -x remote_access >/dev/null 2>&1; then "
        "printf 'STATE=running\\n'; "
        "printf 'PORT=%s\\n' \"$PORT\"; "
        "pgrep -x remote_access | head -1 | awk '{print \"PID=\"$1}'; "
        "elif [ \"$VERSION_KIND\" = new ] && [ \"$launch_state\" = errored ]; then "
        "printf 'STATE=errored\\n'; "
        "printf 'PORT=%s\\n' \"$PORT\"; "
        "else "
        "printf 'STATE=stopped\\n'; "
        "printf 'PORT=%s\\n' \"$PORT\"; "
        "fi"
    )
    return ssh_command(profile, inner)


def public_ssid_probe_command(profile: ProductProfile) -> str:
    inner = (
        _detect_3588_hotspot_ssid_shell("SSID")
        + "printf 'SSID=%s\\n' \"$SSID\"; "
        + "[ -n \"$SSID\" ]"
    )
    return ssh_command(profile, inner)


def public_access_action_command(
    profile: ProductProfile, ssid: str = DEFAULT_PUBLIC_SSID, action: str = "open"
) -> CommandSpec:
    stream_id = ssid.strip() or DEFAULT_PUBLIC_SSID
    log_path = f"{profile.home}/remote_access.log"
    install_script_path, install_binary_path = _remote_install_paths(profile)
    script_path = install_script_path
    binary_path = install_binary_path
    missing_script_message = f"[失败] 启动脚本未同步：{script_path}\n请先点击“同步脚本和程序”。"
    missing_binary_message = f"[失败] remote_access 程序未同步：{binary_path}\n请先点击“同步脚本和程序”。"

    close = (
        "set -e; "
        f"cd {quote(profile.home)}; "
        + remote_version_shell()
        + "if [ \"$VERSION_KIND\" = new ] && command -v robot-launch >/dev/null 2>&1; then "
        "printf '[关闭] 使用 robot-launch 关闭 remote_access\\n'; "
        "robot-launch stop remote_access; "
        "sleep 1; "
        "robot-launch list | sed -r 's/\\x1B\\[[0-9;]*[A-Za-z]//g' | grep remote_access || true; "
        "exit 0; "
        "fi; "
        "if ! pgrep -x remote_access >/dev/null 2>&1; then "
        "printf '[状态] 公网连接未运行，无需关闭。\\n'; "
        "exit 0; "
        "fi; "
        "printf '[关闭] 发现公网连接进程，正在关闭...\\n'; "
        "pkill -f '[s]tart_remote_access.sh --ssid' 2>/dev/null || true; "
        "pkill -x remote_access 2>/dev/null || true; "
        "sleep 1; "
        "if pgrep -x remote_access >/dev/null 2>&1; then "
        "printf '[失败] remote_access 仍在运行，请手动检查。\\n'; "
        + _remote_access_process_list_shell()
        + "; "
        "exit 1; "
        "fi; "
        "printf '[完成] 公网连接已关闭。\\n'"
    )

    start = (
        "set -e; "
        f"cd {quote(profile.home)}; "
        "if pgrep -x remote_access >/dev/null 2>&1; then "
        f"PORT=''; [ -f {quote(log_path)} ] && PORT=$(grep -m1 'remotePort' {quote(log_path)} | awk -F'= ' '{{print $2}}'); "
        "printf '[结果] 公网连接已在运行\\n'; "
        f"printf '公网地址: {profile.user}@{PUBLIC_SERVER}\\n'; "
        "printf '公网端口: %s\\n' \"${PORT:-未知}\"; "
        f"if [ -n \"$PORT\" ]; then printf '连接命令: ssh {profile.user}@{PUBLIC_SERVER} -p %s\\n' \"$PORT\"; fi; "
        "exit 0; "
        "fi; "
        + remote_version_shell()
        + "if [ \"$VERSION_KIND\" = new ] && command -v robot-launch >/dev/null 2>&1; then "
        "printf '[启动] 使用 robot-launch 启动 remote_access\\n'; "
        "robot-launch start remote_access; "
        "sleep 2; "
        "printf '[结果] 已请求 robot-launch 启动 remote_access\\n'; "
        "robot-launch list | sed -r 's/\\x1B\\[[0-9;]*[A-Za-z]//g' | grep remote_access || true; "
        "exit 0; "
        "fi; "
        f"test -x {quote(script_path)} || ({echo_message(missing_script_message)}; exit 1); "
        f"test -x {quote(binary_path)} || ({echo_message(missing_binary_message)}; exit 1); "
        f"rm -f {quote(log_path)}; "
        "RELEASE_FILE=$(find /etc/release -maxdepth 1 -type f -name '*.yaml' -printf '%f\\n' 2>/dev/null | sort | tail -1); "
        "USE_SSID=1; "
        "case \"$RELEASE_FILE\" in *0029*B.yaml|*003[0-9]*.yaml|*00[3-9][0-9]*.yaml) USE_SSID=0 ;; esac; "
        + public_server_tcp_check_shell()
        + f"if check_public_tcp {quote(PUBLIC_SERVER)} {quote(PUBLIC_PORT_MANAGER_PORT)}; then "
        f"printf '[检查] 公网服务器: {PUBLIC_SERVER}:{PUBLIC_PORT_MANAGER_PORT} 可达\\n'; "
        "else "
        f"printf '[失败] 公网服务器不可达：{PUBLIC_SERVER}:{PUBLIC_PORT_MANAGER_PORT}\\n'; "
        "printf '[失败] 当前目标设备没有可用公网链路，请先让 RK3588 或 NX 联网。\\n'; exit 1; "
        "fi; "
        "if ping -c 1 -W 3 www.baidu.com >/dev/null 2>&1; then "
        "printf '[检查] DNS 正常\\n'; "
        "else "
        "printf '[提示] DNS 失败，但 remote_access 使用公网 IP，可继续启动\\n'; "
        "fi; "
        "if [ \"$USE_SSID\" = 0 ]; then "
        "printf '[启动] remote_access，不带 --ssid\\n'; "
        f"PATH={quote(profile.home)}:$PATH nohup {quote(script_path)} --user {quote(profile.user)} > {quote(log_path)} 2>&1 & "
        "else "
        + _detect_3588_hotspot_ssid_shell("DETECTED_STREAM_ID")
        + f"USER_STREAM_ID_ARG={quote(stream_id)}; "
        "STREAM_ID_ARG=\"$DETECTED_STREAM_ID\"; SSID_SOURCE=3588检测; "
        "if [ -z \"$STREAM_ID_ARG\" ]; then STREAM_ID_ARG=\"$USER_STREAM_ID_ARG\"; SSID_SOURCE=输入框; fi; "
        "if [ -z \"$STREAM_ID_ARG\" ]; then printf '[失败] 未读取到 3588 热点 SSID。\\n'; exit 1; fi; "
        "printf '[启动] remote_access，--ssid=%s（%s）\\n' \"$STREAM_ID_ARG\" \"$SSID_SOURCE\"; "
        f"PATH={quote(profile.home)}:$PATH nohup {quote(script_path)} --ssid \"$STREAM_ID_ARG\" --user {quote(profile.user)} > {quote(log_path)} 2>&1 & "
        "fi; "
        "sleep 5; "
        f"PORT=$(grep -m1 'remotePort' {quote(log_path)} | awk -F'= ' '{{print $2}}' || true); "
        "PID=$(pgrep -x remote_access | head -1 || true); "
        f"if grep -q 'start proxy success' {quote(log_path)}; then "
        "printf '\\n[结果] 公网连接已打开\\n'; "
        f"printf '公网地址: {profile.user}@{PUBLIC_SERVER}\\n'; "
        "printf '公网端口: %s\\n' \"$PORT\"; "
        f"printf '连接命令: ssh {profile.user}@{PUBLIC_SERVER} -p %s\\n' \"$PORT\"; "
        "printf '本机进程: remote_access PID=%s\\n' \"${PID:-未知}\"; "
        "else "
        f"printf '\\n[失败] 公网连接未成功\\n日志文件: {log_path}\\n最近日志:\\n'; "
        f"tail -n 20 {quote(log_path)} || true; "
        "exit 1; "
        "fi"
    )
    if action == "close":
        command = (
            "set -e; "
            f"printf '[目标] {profile.label} {profile.target}\\n'; "
            f"{ssh_command(profile, close)}"
        )
        return CommandSpec("关闭公网连接", command, dangerous=True)

    command = (
        "set -e; "
        f"printf '[目标] {profile.label} {profile.target}\\n'; "
        f"{ssh_command(profile, start)}"
    )
    return CommandSpec("打开公网连接", command, dangerous=True)


def sync_remote_access_files_command(profile: ProductProfile) -> CommandSpec:
    local_script, local_binary = remote_access_resource_paths()
    install_script_path, install_binary_path = _remote_install_paths(profile)
    tmp_script = f"/tmp/dog_remote_start_remote_access_{profile.user}.sh"
    tmp_binary = f"/tmp/dog_remote_remote_access_{profile.user}"
    upload_script = scp_push_command(profile, local_script, tmp_script, connect_timeout=6)
    upload_binary = scp_push_command(profile, local_binary, tmp_binary, connect_timeout=6)
    remote = (
        "set -e; "
        + sudo_run_shell(fallback_without_sudo=False)
        + "remote_sha() { [ -f \"$1\" ] && sha256sum \"$1\" | awk '{print $1}' || printf 'missing'; }; "
        "sync_root_file() { "
        "label=\"$1\"; src=\"$2\"; dst=\"$3\"; mode=\"$4\"; "
        "dst_dir=$(dirname \"$dst\"); "
        "sudo_run install -d -m 0755 \"$dst_dir\" >/dev/null; "
        "src_sha=$(remote_sha \"$src\"); dst_sha=$(remote_sha \"$dst\"); "
        "short_sha=$(printf '%s' \"$src_sha\" | cut -c1-12); "
        "if [ \"$src_sha\" = \"$dst_sha\" ]; then printf '[同步] %s: 已是最新 (%s)\\n' \"$label\" \"$short_sha\"; "
        "else sudo_run install -m \"$mode\" \"$src\" \"$dst\" >/dev/null; printf '[同步] %s: 已更新 (%s)\\n' \"$label\" \"$short_sha\"; fi; "
        "}; "
        f"chmod +x {quote(tmp_script)} {quote(tmp_binary)}; "
        f"sync_root_file 脚本 {quote(tmp_script)} {quote(install_script_path)} 0755; "
        f"sync_root_file 程序 {quote(tmp_binary)} {quote(install_binary_path)} 0755; "
        f"rm -f {quote(tmp_script)} {quote(tmp_binary)}; "
        "printf '\\n[结果] 脚本和程序已同步\\n'; "
        f"printf '脚本: {install_script_path}\\n'; "
        f"printf '程序: {install_binary_path}\\n'"
    )
    command = (
        "set -e; "
        f"printf '[目标] {profile.label} {profile.target}\\n'; "
        f"test -f {quote(local_script)} || ({echo_message(f'[失败] 工具内置脚本不存在：{local_script}')}; exit 1); "
        f"test -f {quote(local_binary)} || ({echo_message(f'[失败] 工具内置程序不存在：{local_binary}')}; exit 1); "
        "printf '[本地] 脚本和程序已找到\\n'; "
        f"{upload_script}; "
        f"{upload_binary}; "
        f"{ssh_command(profile, remote)}"
    )
    return CommandSpec(
        "同步脚本和程序",
        command,
        dangerous=True,
        description=(
            f"脚本将安装到 {REMOTE_SCRIPT_INSTALL_PATH}\n"
            f"程序将安装到 {REMOTE_BINARY_INSTALL_PATH}"
        ),
    )
