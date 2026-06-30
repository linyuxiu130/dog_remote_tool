from __future__ import annotations

from dog_remote_tool.core.profiles import PRODUCTS, ProductProfile
from dog_remote_tool.core.shell import CommandSpec, echo_message, quote, ssh_prefix_command


def account_probe_command(profile: ProductProfile) -> CommandSpec:
    parts = ["echo '[INFO] 当前账号不可用时，仅探测同机型族同 IP 已知账号。'", "found=0"]
    seen: set[tuple[str, str, str]] = set()
    family_prefix = profile.key.split("_", 1)[0]
    for candidate in PRODUCTS.values():
        if candidate.host != profile.host:
            continue
        if candidate.key != profile.key and candidate.key.split("_", 1)[0] != family_prefix:
            continue
        key = (candidate.user, candidate.password, candidate.host)
        if key in seen:
            continue
        seen.add(key)
        cmd = (
            f"{ssh_prefix_command(candidate)} "
            f"{quote('echo ONLINE')} >/dev/null 2>&1"
        )
        parts.append(
            f"if {cmd}; then {echo_message(f'[INFO] 可用账号: {candidate.label} {candidate.target}')}; found=1; fi"
        )
    parts.append("if [ \"$found\" -eq 0 ]; then echo '[WARN] 未发现同 IP 可用账号。'; fi")
    return CommandSpec(
        "探测可用账号",
        "; ".join(parts),
        display_command="探测当前设备可用账号",
    )
