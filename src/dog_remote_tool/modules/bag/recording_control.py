from __future__ import annotations

import shlex
import subprocess
from typing import Callable

from dog_remote_tool.core.profiles import ProductProfile
from dog_remote_tool.core.shell import sshpass_argv
from dog_remote_tool.modules.bag import recording_remote as bag_recording_remote


def record_process_command(profile: ProductProfile, ssh_options: list[str], script: str) -> list[str]:
    return [
        *sshpass_argv(profile.password),
        "ssh",
        *ssh_options,
        profile.target,
        f"bash -lc {shlex.quote(script)}",
    ]


def start_remote_recording(
    remote_bag_paths: list[str],
    script: str,
    ssh_bash_command: Callable[..., subprocess.CompletedProcess],
    log: Callable[[str], None],
) -> tuple[bool, str]:
    if not remote_bag_paths:
        return False, "未生成远端Bag路径"
    remote_cmd = bag_recording_remote.start_recording_wrapper_command(script, remote_bag_paths)
    try:
        result = ssh_bash_command(remote_cmd, timeout=20, login_shell=False)
    except subprocess.TimeoutExpired:
        return False, "远端启动录制超时"
    output = "\n".join(line for line in (result.stdout + "\n" + result.stderr).splitlines() if line.strip())
    if result.returncode != 0:
        return False, output[-600:] or f"return code {result.returncode}"
    for line in output.splitlines():
        if line.startswith("__DOG_REMOTE_RECORD_STARTED__"):
            log(f"[录制] 远端后台录制已启动: {line.replace('__DOG_REMOTE_RECORD_STARTED__ ', '')}")
            return True, ""
    return False, output[-600:] or "远端未返回启动确认"


def stop_remote_recording(
    remote_bag_paths: list[str],
    ssh_bash_command: Callable[..., subprocess.CompletedProcess],
    log: Callable[[str], None],
) -> bool:
    if not remote_bag_paths:
        log("[录制] 未找到当前录制的远端Bag路径，无法精确停止")
        return False
    log("[录制] 尝试停止远端录制进程")
    remote_cmd = bag_recording_remote.stop_recording_command(remote_bag_paths)
    try:
        result = ssh_bash_command(remote_cmd, timeout=220, login_shell=False)
    except subprocess.TimeoutExpired:
        log("[录制] 远端停止命令超时")
        return False
    for line in result.stdout.splitlines():
        if line.strip():
            log(f"[录制] 远端停止: {line.strip()}")
    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip() or f"return code {result.returncode}"
        log(f"[录制] 远端停止信号发送异常: {detail[:160]}")
        return False
    return True
