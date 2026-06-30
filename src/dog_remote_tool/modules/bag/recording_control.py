from __future__ import annotations

import subprocess
from typing import Callable

from dog_remote_tool.modules.bag import remote_helper as bag_remote_helper


def start_remote_recording(
    remote_bag_paths: list[str],
    script: str,
    ssh_bash_command: Callable[..., subprocess.CompletedProcess],
    log: Callable[[str], None],
) -> tuple[bool, str]:
    if not remote_bag_paths:
        return False, "未生成远端Bag路径"
    remote_cmd = bag_remote_helper.start_recording_command(script, remote_bag_paths)
    try:
        result = ssh_bash_command(remote_cmd, timeout=10, login_shell=False)
    except subprocess.TimeoutExpired:
        return False, "远端启动录制超时"
    output = "\n".join(line for line in (result.stdout + "\n" + result.stderr).splitlines() if line.strip())
    if result.returncode != 0:
        return False, output[-600:] or f"return code {result.returncode}"
    payload = bag_remote_helper.parse_helper_json(output)
    if payload.get("ok"):
        detail = f"pid={payload.get('pid', '-')}"
        if payload.get("log"):
            detail += f" log={payload.get('log')}"
        if payload.get("already_running"):
            detail += " already_running=1"
        log(f"[录制] 远端后台录制已启动: {detail}")
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
    remote_cmd = bag_remote_helper.stop_recording_command(remote_bag_paths)
    try:
        result = ssh_bash_command(remote_cmd, timeout=12, login_shell=False)
    except subprocess.TimeoutExpired:
        log("[录制] 远端停止命令超时")
        return False
    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip() or f"return code {result.returncode}"
        log(f"[录制] 远端停止信号发送异常: {detail[:160]}")
        return False
    payload = bag_remote_helper.parse_helper_json(result.stdout + "\n" + result.stderr)
    if not payload.get("ok"):
        log(f"[录制] 远端停止信号发送异常: {(result.stdout or result.stderr).strip()[:160]}")
        return False
    if payload.get("deferred"):
        log("[录制] 远端停止信号已发送，Bag仍在收尾，可稍后刷新确认")
    elif payload.get("already_stopped"):
        log("[录制] 远端录制进程已不在运行")
    else:
        log(f"[录制] 远端停止: {payload.get('signal', 'SIGINT')}")
    return True
