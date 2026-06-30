from __future__ import annotations

import shlex
import subprocess
from typing import Callable

from dog_remote_tool.core.profiles import ProductProfile
from dog_remote_tool.core.shell import sshpass_argv
from dog_remote_tool.modules.bag import remote_delete_commands as bag_remote_delete_commands


def delete_remote_bags(
    profile: ProductProfile,
    remote_paths: list[str],
    ssh_options: list[str],
    log: Callable[[str], None],
    auto_delete: bool = False,
) -> tuple[list[str], list[str]]:
    deleted: list[str] = []
    failed: list[str] = []
    safe_paths: list[str] = []
    prefix = "[清理]" if auto_delete else "✗"
    success_prefix = "[清理]" if auto_delete else "✓"

    for remote_path in remote_paths:
        if not bag_remote_delete_commands.is_safe_remote_bag_path(remote_path, profile):
            failed.append(remote_path)
            log(f"{prefix} 拒绝删除非录包安全路径: {remote_path}")
            continue
        if remote_path not in safe_paths:
            safe_paths.append(remote_path)

    if not safe_paths:
        return deleted, failed

    cmd = [
        *sshpass_argv(profile.password),
        "ssh",
        *ssh_options,
        profile.target,
        f"bash -lc {shlex.quote(bag_remote_delete_commands.delete_remote_bags_command(safe_paths))}",
    ]
    try:
        result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=60)
    except Exception as exc:
        for remote_path in safe_paths:
            failed.append(remote_path)
            log(f"{prefix} 远端Bag删除异常: {remote_path} ({exc})")
        return deleted, failed

    batch_deleted, batch_failed = bag_remote_delete_commands.parse_delete_remote_bags_output(result.stdout or "")
    deleted_set = set(batch_deleted)
    for remote_path in safe_paths:
        if remote_path in deleted_set:
            deleted.append(remote_path)
            log(f"{success_prefix} 远端Bag已删除: {remote_path}")
        else:
            failed.append(remote_path)
            reason = batch_failed.get(remote_path)
            if not reason:
                hint = (result.stdout or "").strip().splitlines()
                reason = hint[-1][:120] if hint else str(result.returncode)
            log(f"{prefix} 远端Bag删除失败: {remote_path} ({reason[:120]})")
    return deleted, failed
