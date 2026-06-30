from __future__ import annotations

import os
import re
import select
import shlex
import subprocess
import time
from typing import Callable

from dog_remote_tool.core.profiles import ProductProfile
from dog_remote_tool.core.shell import sshpass_argv
from dog_remote_tool.modules.bag.names import format_rsync_speed


RSYNC_LINE_SPLIT_PATTERN = re.compile(r"[\r\n]")
RSYNC_PROGRESS_PATTERN = re.compile(r"(\d+)%\s+([0-9.,]+\s*[A-Za-z]+/s)?")


def local_log_source_dir(remote_log_path: str) -> str:
    source = remote_log_path.strip().strip("/")
    safe = re.sub(r"[^A-Za-z0-9._-]+", "_", source)
    safe = re.sub(r"_+", "_", safe).strip("._-")
    return safe or "remote_log"


def build_rsync_command(
    profile: ProductProfile,
    ssh_options: list[str],
    remote_path: str,
    local_path: str,
    rsync_args: list[str] | None = None,
    excludes: list[str] | None = None,
) -> list[str]:
    ssh_cmd = "ssh " + " ".join(shlex.quote(option) for option in ssh_options)
    cmd = [*sshpass_argv(profile.password), "rsync", *(rsync_args or ["-az", "--partial"])]
    for pattern in excludes or []:
        cmd.extend(["--exclude", pattern])
    cmd.extend(["-e", ssh_cmd, f"{profile.target}:{remote_path}", local_path])
    return cmd


def split_rsync_output(buffer: str, text: str) -> tuple[str, list[str]]:
    buffer += text
    parts = RSYNC_LINE_SPLIT_PATTERN.split(buffer)
    return parts.pop(), parts


def parse_rsync_progress(line: str) -> tuple[int, str] | None:
    if "%" not in line:
        return None
    match = RSYNC_PROGRESS_PATTERN.search(line.strip())
    if not match:
        return None
    return int(match.group(1)), format_rsync_speed(match.group(2) or "")


def is_warning_line(line: str) -> bool:
    lowered = line.lower()
    return bool(line) and any(token in lowered for token in ("error", "fail", "refused", "denied"))


def remember_output_tail(output_tail: list[str], line: str, limit: int = 8) -> None:
    if not line:
        return
    output_tail.append(line[:300])
    del output_tail[:-limit]


def run_rsync_with_progress(
    cmd: list[str],
    label: str,
    idle_timeout: int,
    log: Callable[[str], None],
    progress: Callable[[str, float, str], None] | None = None,
    progress_prefix: str = "",
) -> bool:
    process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, bufsize=0)
    last_output_at = time.monotonic()
    last_percent = -1
    last_progress_emit_at = 0.0
    last_speed = ""
    buffer = ""
    output_tail: list[str] = []

    def handle_line(line: str) -> None:
        nonlocal last_percent, last_progress_emit_at, last_speed
        line = line.strip()
        remember_output_tail(output_tail, line)
        parsed = parse_rsync_progress(line)
        if parsed:
            percent, speed = parsed
            now = time.monotonic()
            should_emit = (
                percent > last_percent
                or (speed and speed != last_speed)
                or (progress is not None and now - last_progress_emit_at >= 0.35)
            )
            if should_emit:
                percent_changed = percent > last_percent
                last_percent = percent
                last_speed = speed
                last_progress_emit_at = now
                if progress:
                    progress(label, float(percent), speed)
                if progress_prefix and percent_changed:
                    suffix = f"，当前速率: {speed}" if speed else ""
                    log(f"  {progress_prefix}下载进度: {percent}%{suffix}")
        elif is_warning_line(line):
            log(f"  {label}警告: {line[:120]}")

    def consume(text: str) -> None:
        nonlocal buffer
        buffer, parts = split_rsync_output(buffer, text)
        for part in parts:
            handle_line(part)

    while process.poll() is None:
        if time.monotonic() - last_output_at > idle_timeout:
            process.kill()
            process.wait()
            raise subprocess.TimeoutExpired(cmd, idle_timeout)
        readable, _, _ = select.select([process.stdout], [], [], 1)
        if not readable:
            continue
        chunk = os.read(process.stdout.fileno(), 4096)
        if chunk:
            last_output_at = time.monotonic()
            consume(chunk.decode(errors="replace"))
    remaining = process.stdout.read()
    if remaining:
        consume(remaining.decode(errors="replace"))
    if buffer:
        handle_line(buffer)
    process.wait()
    if process.returncode != 0:
        detail = " | ".join(output_tail[-4:]) if output_tail else "无输出"
        log(f"  {label} rsync退出码: {process.returncode}，最后输出: {detail}")
    return process.returncode == 0
