from __future__ import annotations

from dog_remote_tool.core.profiles import ProductProfile
from dog_remote_tool.core.shell import quote, sudo_run_shell


def sudo_sh(profile: ProductProfile, script: str) -> str:
    return sudo_run_shell(fallback_without_sudo=False) + f"sudo_run sh -c {quote(script)}"


def sudo_exec(profile: ProductProfile, command: str) -> str:
    return sudo_run_shell(fallback_without_sudo=False) + f"sudo_run {command}"
