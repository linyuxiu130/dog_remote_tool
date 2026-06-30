from __future__ import annotations

from dog_remote_tool.core.profiles import ProductProfile
from dog_remote_tool.core.shell import CommandSpec, echo_message, quote, ssh_command


def launch_action_command(profile: ProductProfile, name: str, action: str) -> CommandSpec:
    action_labels = {"start": "开启", "stop": "关闭", "restart": "重启"}
    if action not in action_labels:
        raise ValueError(f"unsupported robot-launch action: {action}")
    safe_name = name.strip()
    script = (
        "set -o pipefail; "
        "clean_ansi() { sed -r 's/\\x1B\\[[0-9;]*[A-Za-z]//g'; }; "
        "print_matching_logs() { "
        "local service=\"$1\"; "
        "local short=\"${service#driver-}\"; "
        "local found=0; "
        "local grep_expr=\"error|exception|fail|fatal|traceback|warn|${service}|${short}|serial|tty|device|permission|timeout\"; "
        "printf '\\n[异常日志摘要] 最近 30 分钟内匹配 %s / %s 的日志\\n' \"$service\" \"$short\"; "
        "for file in "
        "\"$HOME/robot_launch_log/${service}.stderr\" \"$HOME/robot_launch_log/${service}.stdout\" "
        "\"/home/robot/robot_launch_log/${service}.stderr\" \"/home/robot/robot_launch_log/${service}.stdout\" "
        "\"/home/firefly/robot_launch_log/${service}.stderr\" \"/home/firefly/robot_launch_log/${service}.stdout\"; do "
        "[ -f \"$file\" ] || continue; "
        "found=1; "
        "printf '\\n--- %s ---\\n' \"$file\"; "
        "match=$(tail -n 300 \"$file\" 2>/dev/null | clean_ansi | grep -Ei \"$grep_expr\" | tail -n 80 || true); "
        "if [ -n \"$match\" ]; then printf '%s\\n' \"$match\"; "
        "else printf '[INFO] 未命中错误关键词，显示最后 80 行\\n'; tail -n 80 \"$file\" 2>/dev/null | clean_ansi; fi; "
        "done; "
        "for dir in /tmp/zsibot/log /tmp/log/alg_data \"$HOME/.ros/log/latest\" \"$HOME/.ros/log\"; do "
        "[ -d \"$dir\" ] || continue; "
        "while IFS= read -r file; do "
        "[ -f \"$file\" ] || continue; "
        "found=1; "
        "printf '\\n--- %s ---\\n' \"$file\"; "
        "match=$(tail -n 300 \"$file\" 2>/dev/null | clean_ansi | grep -Ei \"$grep_expr\" | tail -n 60 || true); "
        "if [ -n \"$match\" ]; then printf '%s\\n' \"$match\"; "
        "else printf '[INFO] 未命中错误关键词，显示最后 40 行\\n'; tail -n 40 \"$file\" 2>/dev/null | clean_ansi; fi; "
        "done < <(find -L \"$dir\" -maxdepth 3 -type f "
        "\\( -iname \"*${service}*\" -o -iname \"*${short}*\" -o -iname '*robot-launch*' -o -iname '*.log' \\) "
        "-mmin -30 -printf '%T@ %p\\n' 2>/dev/null | sort -nr | head -5 | cut -d' ' -f2-); "
        "done; "
        "if [ \"$found\" -eq 0 ]; then printf '[INFO] 未找到近 30 分钟内匹配的日志文件。\\n'; fi; "
        "}; "
        "if ! command -v robot-launch >/dev/null 2>&1; then "
        "echo '[ERROR] robot-launch 不存在'; exit 2; "
        "fi; "
        f"{echo_message(f'[INFO] {action_labels[action]} robot-launch 进程: {safe_name}')}; "
        f"ACTION_OUTPUT=$(robot-launch {quote(action)} {quote(safe_name)} 2>&1); "
        "ACTION_CODE=$?; "
        "printf '%s\\n' \"$ACTION_OUTPUT\" | clean_ansi; "
        f"if [ {quote(action)} = start ] && printf '%s\\n' \"$ACTION_OUTPUT\" | grep -qi 'already running'; then "
        "sleep 1; "
        "CHECK_LIST=$(robot-launch list 2>&1 | clean_ansi || true); "
        f"CURRENT_STATUS=$(printf '%s\\n' \"$CHECK_LIST\" | awk -F'│' -v target={quote(safe_name)} "
        "'{name=$4; status=$5; gsub(/^[[:space:]]+|[[:space:]]+$/, \"\", name); "
        "gsub(/^[[:space:]]+|[[:space:]]+$/, \"\", status); if (name == target) {print status; exit}}'); "
        "if [ -n \"$CURRENT_STATUS\" ] && [ \"$CURRENT_STATUS\" != running ]; then "
        "printf '\\n[INFO] robot-launch 返回 already running，但当前状态是 %s，先 stop 清理异常状态后再 start。\\n' \"$CURRENT_STATUS\"; "
        f"robot-launch stop {quote(safe_name)} 2>&1 | clean_ansi || true; "
        "sleep 1; "
        f"ACTION_OUTPUT=$(robot-launch start {quote(safe_name)} 2>&1); "
        "ACTION_CODE=$?; "
        "printf '%s\\n' \"$ACTION_OUTPUT\" | clean_ansi; "
        "fi; "
        "fi; "
        "sleep 1; "
        "LAUNCH_LIST=$(robot-launch list 2>&1 | clean_ansi || true); "
        "printf '%s\\n' \"$LAUNCH_LIST\"; "
        f"EGG_INDEX=$(printf '%s\\n' \"$LAUNCH_LIST\" | awk -F'│' -v target={quote(safe_name)} "
        "'{idx=$2; name=$4; gsub(/^[[:space:]]+|[[:space:]]+$/, \"\", idx); "
        "gsub(/^[[:space:]]+|[[:space:]]+$/, \"\", name); if (name == target) {print idx; exit}}'); "
        "if [ -n \"$EGG_INDEX\" ]; then "
        f"printf '\\n[robot-launch egg %s] %s\\n' \"$EGG_INDEX\" {quote(safe_name)}; "
        "robot-launch egg \"$EGG_INDEX\" 2>&1 | clean_ansi | tail -n 160 || true; "
        "else "
        f"printf '\\n[WARN] 未在 robot-launch list 中找到 %s，无法自动查询 egg 详情。\\n' {quote(safe_name)}; "
        "fi; "
        f"if [ {quote(action)} != stop ]; then print_matching_logs {quote(safe_name)}; fi; "
        "exit \"$ACTION_CODE\""
    )
    inner = f"bash -c {quote(script)}"
    return CommandSpec(
        f"{action_labels[action]} {safe_name}",
        ssh_command(profile, inner),
        dangerous=action in {"stop", "restart"},
    )
