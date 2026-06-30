from __future__ import annotations

from dog_remote_tool.core.profiles import ProductProfile
from dog_remote_tool.core.shell import CommandSpec, quote, ssh_command
import dog_remote_tool.modules.control.speed_l2 as _l2_speed
import dog_remote_tool.modules.control.speed_config as _speed_config


NAV_CONFIG_CANDIDATES = _speed_config.NAV_CONFIG_CANDIDATES
L2_REMOTE_CONFIG = _speed_config.L2_REMOTE_CONFIG
l2_nav_speed_status_command = _l2_speed.l2_nav_speed_status_command
l2_nav_speed_override_command = _l2_speed.l2_nav_speed_override_command


def speed_override_command(profile: ProductProfile, speed: float, enabled: bool) -> CommandSpec:
    paths = NAV_CONFIG_CANDIDATES.get(profile.key, [])
    if not paths:
        return CommandSpec("速度配置覆盖", "echo 当前产品不支持速度配置覆盖", dangerous=True)
    enabled_text = "True" if enabled else "False"
    script = (
        "set -e; "
        f"for p in {' '.join(quote(p) for p in paths)}; do [ -f \"$p\" ] && cfg=\"$p\" && break; done; "
        "test -n \"${cfg:-}\"; "
        "sudo cp \"$cfg\" \"$cfg.bak.$(date +%Y%m%d_%H%M%S)\"; "
        "sudo CFG=\"$cfg\" python3 - <<'PY'\n"
        "import os, re\n"
        "path = os.environ['CFG']\n"
        "text = open(path, encoding='utf-8').read()\n"
        "text = re.sub(r'(enabled:\\s*)\\w+', r'\\1" + enabled_text + "', text)\n"
        "text = re.sub(r'(linear_x:\\s*)[-0-9.]+', r'\\1" + f"{speed:.2f}" + "', text)\n"
        "open(path, 'w', encoding='utf-8').write(text)\n"
        "PY\n"
        "sudo systemctl restart robot-alg-manager || sudo robot-launch restart robot-alg-manager"
    )
    return CommandSpec("速度配置覆盖", ssh_command(profile, script), dangerous=True)
