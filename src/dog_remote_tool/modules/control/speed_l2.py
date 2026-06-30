from __future__ import annotations

from dog_remote_tool.core.profiles import ProductProfile
from dog_remote_tool.core.shell import CommandSpec, quote, remote_env, ssh_command
import dog_remote_tool.modules.control.speed_config as _speed_config
from dog_remote_tool.modules.control.l2_speed_scripts import nav_speed_reader_python
from dog_remote_tool.modules.control.shared import l2_control_profile, ssh_bash_stdin_command


L2_REMOTE_CONFIG = _speed_config.L2_REMOTE_CONFIG


def l2_nav_speed_status_command(profile: ProductProfile) -> CommandSpec:
    target = l2_control_profile(profile)
    if target is None:
        return CommandSpec("读取 L2 导航速度", "echo '[ERROR] 当前设备不是小狗二代 L2 的 S100/3588，无法读取 robot_remote 导航速度。'")
    script = (
        f"{remote_env(target)}; "
        f"CFG={quote(L2_REMOTE_CONFIG)}; "
        "echo '[INFO] L2 robot_remote 导航速度配置'; "
        "echo \"target=$(hostname 2>/dev/null || true) cfg=$CFG\"; "
        f"python3 - <<'PY'\n{nav_speed_reader_python(L2_REMOTE_CONFIG)}\nPY\n"
        "echo '[INFO] 运行时 ROS 参数'; "
        "for key in vertical_move horizontal_move yaw; do "
        "printf 'PARAM_%s=' \"$key\"; "
        "ros2 param get /robot_remote speed.noload.nav.$key 2>/dev/null | awk -F': ' 'NF>1{print $2; found=1} END{if(!found) print \"--\"}'; "
        "done"
    )
    return CommandSpec(
        "读取 L2 导航速度",
        ssh_command(target, script),
        display_command="执行：读取导航速度",
        concurrency="parallel",
    )


def l2_nav_speed_override_command(profile: ProductProfile, speed: float, restart: bool) -> CommandSpec:
    target = l2_control_profile(profile)
    if target is None:
        return CommandSpec(
            "应用 L2 导航速度覆盖",
            "echo '[ERROR] 当前设备不是小狗二代 L2 的 S100/3588，无法覆盖 robot_remote 导航速度。'",
            dangerous=True,
        )
    speed = _speed_config.clamp_nav_speed(speed)
    restart_flag = "1" if restart else "0"
    script = (
        "set -eo pipefail\n"
        f"CFG={quote(L2_REMOTE_CONFIG)}\n"
        "sudo_run() {\n"
        "  if sudo -n true >/dev/null 2>&1; then sudo \"$@\"; else printf '%s\\n' \"$SUDO_PASS\" | sudo -S -p '' \"$@\"; fi\n"
        "}\n"
        "read_nav() {\n"
        f"  python3 - <<'PY'\n{nav_speed_reader_python(L2_REMOTE_CONFIG, 'nav.')}\nPY\n"
        "}\n"
        "test -f \"$CFG\" || { echo \"[ERROR] 配置不存在: $CFG\"; exit 2; }\n"
        "echo '[INFO] 修改前 YAML:'\n"
        "read_nav\n"
        "echo '[INFO] 修改运行时 ROS 参数: speed.noload.nav.vertical_move'\n"
        f"{remote_env(target)}\n"
        "ros2 param set /robot_remote speed.noload.nav.vertical_move $NEW_SPEED\n"
        "BACKUP=\"$CFG.bak.$(date +%Y%m%d_%H%M%S)\"\n"
        "echo \"[INFO] 备份配置: $BACKUP\"\n"
        "sudo_run cp \"$CFG\" \"$BACKUP\"\n"
        "TMP=/tmp/dog_remote_l2_nav_speed.yaml\n"
        "NEW_SPEED=\"$NEW_SPEED\" CFG=\"$CFG\" python3 - <<'PY' > \"$TMP\"\n"
        "import os\n"
        "from pathlib import Path\n"
        "path = Path(os.environ['CFG'])\n"
        "new_speed = float(os.environ['NEW_SPEED'])\n"
        "lines = path.read_text(errors='ignore').splitlines(True)\n"
        "stack = []\n"
        "changed = False\n"
        "out = []\n"
        "for raw in lines:\n"
        "    stripped = raw.strip()\n"
        "    if stripped and not raw.lstrip().startswith('#'):\n"
        "        indent = len(raw) - len(raw.lstrip(' '))\n"
        "        while stack and indent <= stack[-1][0]:\n"
        "            stack.pop()\n"
        "        if stripped.endswith(':'):\n"
        "            stack.append((indent, stripped[:-1]))\n"
        "        elif ':' in stripped and [item[1] for item in stack[-3:]] == ['speed', 'noload', 'nav']:\n"
        "            key = stripped.split(':', 1)[0].strip()\n"
        "            if key == 'vertical_move':\n"
        "                prefix = raw[: raw.index('vertical_move:')] if 'vertical_move:' in raw else '          '\n"
        "                newline = '\\n' if raw.endswith('\\n') else ''\n"
        "                raw = f'{prefix}vertical_move: {new_speed:.3f}{newline}'\n"
        "                changed = True\n"
        "    out.append(raw)\n"
        "if not changed:\n"
        "    raise SystemExit('未找到 speed.noload.nav.vertical_move')\n"
        "print(''.join(out), end='')\n"
        "PY\n"
        "sudo_run cp \"$TMP\" \"$CFG\"\n"
        "rm -f \"$TMP\"\n"
        "echo '[INFO] 修改后 YAML:'\n"
        "read_nav\n"
        "if [ \"$RESTART_REMOTE\" = 1 ]; then\n"
        "  echo '[INFO] 重启 robot_remote 让持久配置重新加载'\n"
        "  if command -v robot-launch >/dev/null 2>&1; then robot-launch restart robot_remote; else sudo_run systemctl restart robot_remote; fi\n"
        "  sleep 2\n"
        "  robot-launch list 2>/dev/null | sed -r 's/\\x1B\\[[0-9;]*[A-Za-z]//g' | grep -E 'robot_remote|name|#' || true\n"
        "else\n"
        "  echo '[INFO] 未重启 robot_remote；当前运行时参数已设置，重启后会从 YAML 保留该速度。'\n"
        "fi\n"
    )
    return CommandSpec(
        "应用 L2 导航速度覆盖",
        ssh_bash_stdin_command(
            target,
            script,
            {"NEW_SPEED": f"{speed:.3f}", "RESTART_REMOTE": restart_flag, "SUDO_PASS": target.password},
        ),
        dangerous=True,
        display_command=f"执行：设置导航速度 {speed:.3f} m/s，重启：{'是' if restart else '否'}",
    )
