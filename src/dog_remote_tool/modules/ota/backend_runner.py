from __future__ import annotations

import re
import shutil
import subprocess
import sys
from pathlib import Path

from dog_remote_tool.core.quoting import quote
from dog_remote_tool.core.shell import ssh_options_argv, sshpass_argv
from dog_remote_tool.modules.ota.targets import OtaTarget


SSH_OPTS = ssh_options_argv(include_connect_timeout=False, server_alive_interval=30, server_alive_count_max=120)


def log(message: str) -> None:
    print(message, flush=True)


def die(message: str, code: int = 1) -> None:
    print(f"[ERROR] {message}", file=sys.stderr, flush=True)
    raise SystemExit(code)


RSYNC_PROGRESS_PATTERN = re.compile(r"^\s*[0-9,]+\s+([0-9]{1,3})%\s+(\S+/s)?")
RSYNC_PACKAGE_LINE_PATTERN = re.compile(r"^[^/\s].*\.(?:deb|whl|zip|tar\.gz|tgz|tar\.xz|txz)\s*$", re.IGNORECASE)


def _format_rsync_progress_line(line: str) -> str:
    stripped = line.strip()
    if stripped in {"sending incremental file list", "receiving file list", "receiving incremental file list"}:
        return ""
    if RSYNC_PACKAGE_LINE_PATTERN.match(stripped):
        return ""
    match = RSYNC_PROGRESS_PATTERN.search(stripped)
    if not match:
        return line
    percent, speed = match.groups()
    if percent == "0" and (not speed or speed.startswith("0.00")):
        return ""
    suffix = f" {speed}" if speed else ""
    return f"[INFO] [upload] 上传进度: {percent}%{suffix}\n"


def run_stream(args: list[str], *, input_text: str | None = None) -> None:
    proc = subprocess.Popen(
        args,
        stdin=subprocess.PIPE if input_text is not None else None,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )
    if input_text is not None and proc.stdin:
        proc.stdin.write(input_text)
        proc.stdin.close()
    assert proc.stdout is not None
    is_rsync = "rsync" in args
    last_rsync_percent = ""
    for line in proc.stdout:
        if is_rsync:
            match = RSYNC_PROGRESS_PATTERN.search(line.strip())
            line = _format_rsync_progress_line(line)
            if not line:
                continue
            if match:
                percent = match.group(1)
                if percent == last_rsync_percent:
                    continue
                last_rsync_percent = percent
        print(line, end="", flush=True)
    code = proc.wait()
    if code != 0:
        raise subprocess.CalledProcessError(code, args)


def capture(args: list[str], *, input_text: str | None = None) -> str:
    proc = subprocess.run(args, input=input_text, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    if proc.returncode != 0:
        raise subprocess.CalledProcessError(proc.returncode, args, output=proc.stdout)
    return proc.stdout


def ssh_args(target: OtaTarget, remote_command: str, *, tty: bool = False) -> list[str]:
    args = [*sshpass_argv(target.password), "ssh"]
    if tty:
        args.append("-tt")
    args.extend(SSH_OPTS)
    args.extend([target.remote, remote_command])
    return args


def scp_args(target: OtaTarget, src: Path, remote_dir: str) -> list[str]:
    return [*sshpass_argv(target.password), "scp", *SSH_OPTS, str(src), f"{target.remote}:{remote_dir}/"]


def rsync_args(target: OtaTarget, src: Path, remote_dir: str) -> list[str]:
    ssh = "ssh " + " ".join(quote(part) for part in SSH_OPTS)
    return [
        *sshpass_argv(target.password),
        "rsync",
        "-avP",
        "--append-verify",
        "--partial",
        "--info=progress2",
        "-e",
        ssh,
        str(src),
        f"{target.remote}:{remote_dir}/",
    ]


def remote_supports_rsync(target: OtaTarget) -> bool:
    if not shutil.which("rsync"):
        return False
    try:
        capture(ssh_args(target, "command -v rsync >/dev/null"))
        return True
    except subprocess.CalledProcessError:
        return False


def ensure_tools() -> None:
    for tool in ("ssh", "sshpass"):
        if not shutil.which(tool):
            die(f"本机缺少命令: {tool}")
