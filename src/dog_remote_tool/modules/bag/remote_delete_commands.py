from __future__ import annotations

import os
import re
import shlex

from dog_remote_tool.core.profiles import ProductProfile


def delete_remote_bag_command(remote_path: str) -> str:
    quoted = shlex.quote(remote_path.rstrip("/"))
    return f"test -d {quoted} && rm -rf -- {quoted} && test ! -e {quoted}"


def delete_remote_bags_command(remote_paths: list[str]) -> str:
    paths = list(dict.fromkeys(path.rstrip("/") for path in remote_paths if path.strip()))
    if not paths:
        return "true"
    path_args = " ".join(shlex.quote(path) for path in paths)
    return (
        "status=0; "
        f"for path in {path_args}; do "
        "if [ ! -d \"$path\" ]; then printf 'FAIL\\t%s\\tmissing\\n' \"$path\"; status=1; continue; fi; "
        "err=$(rm -rf -- \"$path\" 2>&1); "
        "if [ $? -eq 0 ] && [ ! -e \"$path\" ]; then "
        "printf 'OK\\t%s\\n' \"$path\"; "
        "else "
        "reason=${err:-delete_failed}; "
        "printf 'FAIL\\t%s\\t%s\\n' \"$path\" \"$reason\"; "
        "status=1; "
        "fi; "
        "done; "
        "exit \"$status\""
    )


def parse_delete_remote_bags_output(output: str) -> tuple[list[str], dict[str, str]]:
    deleted: list[str] = []
    failed: dict[str, str] = {}
    for line in output.splitlines():
        parts = line.split("\t", 2)
        if len(parts) < 2:
            continue
        status, path = parts[0], parts[1]
        if status == "OK":
            deleted.append(path)
        elif status == "FAIL":
            failed[path] = parts[2] if len(parts) > 2 and parts[2] else "delete_failed"
    return deleted, failed


def is_safe_remote_bag_path(remote_path: str, profile: ProductProfile | None = None) -> bool:
    normalized = remote_path.rstrip("/")
    name = os.path.basename(normalized)
    if not normalized.startswith("/"):
        return False
    if normalized in {"/", "/home", "/home/robot", "/home/firefly", "/tmp"}:
        return False
    if not re.match(r"^(?:rosbag2_)?(?:xg|zg|air|l2)_\d{8}_\d{6}$", name, re.IGNORECASE):
        return False
    parent = os.path.dirname(normalized)
    allowed_parents = {"/tmp/zsibot", "/tmp/zsibot/bag", "/tmp/log/alg_data"}
    if profile is not None:
        home = profile.home.rstrip("/")
        allowed_parents.update({home, f"{home}/bag", f"{home}/bags"})
        if profile.key == "xg2_s100":
            allowed_parents.add("/opt/data")
    return parent in allowed_parents
