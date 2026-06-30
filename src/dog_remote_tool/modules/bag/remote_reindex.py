from __future__ import annotations

import os
import select
import shlex
import signal
import subprocess
import time
from typing import Callable


def remote_bag_reindex_command(remote_path: str) -> str:
    return f"""
source /opt/ros/humble/setup.bash 2>/dev/null
path={shlex.quote(remote_path)}
storage_arg=""
if find "$path" -maxdepth 1 -type f -name '*.mcap' | grep -q .; then
  storage_arg="-s mcap"
elif find "$path" -maxdepth 1 -type f -name '*.db3' | grep -q .; then
  storage_arg="-s sqlite3"
fi
ros2 bag reindex $storage_arg "$path"
"""


def run_remote_bag_reindex(
    cmd: list[str],
    remote_path: str,
    log: Callable[[str], None],
    timeout: int = 180,
) -> bool:
    process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, start_new_session=True)
    start = time.monotonic()
    output = []
    while process.poll() is None:
        if time.monotonic() - start > timeout:
            try:
                os.killpg(process.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
            process.wait(timeout=5)
            log(f"[录制] Bag metadata 重建超时: {os.path.basename(remote_path)}")
            return False
        readable, _, _ = select.select([process.stdout], [], [], 1)
        if readable:
            line = process.stdout.readline()
            if line:
                output.append(line.strip())
    remaining = process.stdout.read()
    if remaining:
        output.extend(line.strip() for line in remaining.splitlines() if line.strip())
    if process.returncode == 0:
        log(f"[录制] Bag metadata 已重建: {os.path.basename(remote_path)}")
        return True
    log("[录制] Bag metadata 重建失败: " + ("\n".join(output[-6:]) or f"return code {process.returncode}")[:600])
    return False
