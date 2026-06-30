from __future__ import annotations

import fcntl
import hashlib
import os
import time
from datetime import datetime
from pathlib import Path

from dog_remote_tool.modules.bag.names import local_bag_name_from_remote


TRANSFER_COMPLETE_MARKER = ".dog_remote_transfer_complete"
TRANSFER_INCOMPLETE_MARKER = ".dog_remote_transfer_incomplete"
BAG_PAYLOAD_SUFFIXES = (".mcap", ".db3", ".yaml")


def acquire_transfer_locks(local_base_dir: str, remote_bag_paths: list[str]):
    if not remote_bag_paths:
        return []
    lock_dir = os.path.join(local_base_dir, ".dog_remote_tool_locks")
    os.makedirs(lock_dir, exist_ok=True)
    handles = []
    for remote_path in sorted(set(remote_bag_paths)):
        digest = hashlib.sha256(remote_path.encode("utf-8")).hexdigest()[:24]
        lock_path = os.path.join(lock_dir, f"{digest}.lock")
        handle = open(lock_path, "w", encoding="utf-8")
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            handle.close()
            release_transfer_locks(handles)
            raise RuntimeError(f"远端Bag正在回传中，请等待当前任务完成: {remote_path}") from exc
        handle.write(f"{os.getpid()} {remote_path}\n")
        handle.flush()
        handles.append(handle)
    return handles


def release_transfer_locks(handles) -> None:
    for handle in handles:
        try:
            fcntl.flock(handle, fcntl.LOCK_UN)
            handle.close()
        except OSError:
            pass


def unique_directory_path(path: str) -> str:
    if not os.path.exists(path):
        return path
    for index in range(2, 1000):
        candidate = f"{path}_{index:02d}"
        if not os.path.exists(candidate):
            return candidate
    return f"{path}_{int(time.time())}"


def is_transfer_complete_directory(path: str) -> bool:
    return os.path.exists(os.path.join(path, TRANSFER_COMPLETE_MARKER))


def write_transfer_state_marker(path: str, complete: bool) -> None:
    os.makedirs(path, exist_ok=True)
    complete_path = os.path.join(path, TRANSFER_COMPLETE_MARKER)
    incomplete_path = os.path.join(path, TRANSFER_INCOMPLETE_MARKER)
    try:
        if complete:
            Path(complete_path).write_text(datetime.now().isoformat(timespec="seconds") + "\n", encoding="utf-8")
            if os.path.exists(incomplete_path):
                os.unlink(incomplete_path)
        else:
            Path(incomplete_path).write_text(datetime.now().isoformat(timespec="seconds") + "\n", encoding="utf-8")
            if os.path.exists(complete_path):
                os.unlink(complete_path)
    except OSError:
        pass


def _entry_size(entry: os.DirEntry) -> int:
    try:
        return entry.stat(follow_symlinks=False).st_size
    except OSError:
        return 0


def _bag_dir_size(path: str) -> int:
    total = 0
    try:
        with os.scandir(path) as entries:
            pending = []
            for entry in entries:
                if entry.is_file(follow_symlinks=False) and (
                    entry.name == "metadata.yaml" or entry.name.endswith(BAG_PAYLOAD_SUFFIXES)
                ):
                    total += _entry_size(entry)
                elif entry.is_dir(follow_symlinks=False):
                    pending.append(entry.path)
    except OSError:
        return 0
    if total:
        return total

    while pending:
        current = pending.pop()
        try:
            with os.scandir(current) as nested_entries:
                for entry in nested_entries:
                    if entry.is_dir(follow_symlinks=False):
                        pending.append(entry.path)
                    elif entry.is_file(follow_symlinks=False):
                        total += _entry_size(entry)
        except OSError:
            continue
    return total


def find_reusable_transfer_directory(local_base_dir: str, remote_bag_paths: list[str]) -> str:
    bag_names = list(dict.fromkeys(local_bag_name_from_remote(path) for path in remote_bag_paths if path.strip()))
    if not bag_names or not os.path.isdir(local_base_dir):
        return ""
    candidates: list[tuple[int, float, str]] = []
    try:
        entries = os.scandir(local_base_dir)
    except OSError:
        return ""
    with entries:
        for entry in entries:
            if entry.name == ".dog_remote_tool_locks" or not entry.is_dir(follow_symlinks=False):
                continue
            root = entry.path
            if is_transfer_complete_directory(root):
                continue
            bag_dirs = [os.path.join(root, name) for name in bag_names]
            if not all(os.path.isdir(path) for path in bag_dirs):
                continue
            size = sum(_bag_dir_size(path) for path in bag_dirs)
            try:
                mtime = entry.stat(follow_symlinks=False).st_mtime
            except OSError:
                mtime = 0
            candidates.append((size, mtime, root))
    if not candidates:
        return ""
    candidates.sort(reverse=True)
    return candidates[0][2]


def transfer_target_directory(
    local_base_dir: str,
    dataset_name: str,
    remote_bag_paths: list[str],
    include_bag: bool,
) -> tuple[str, str]:
    base = os.path.join(local_base_dir, dataset_name)
    if not include_bag or not remote_bag_paths:
        return unique_directory_path(base), ""
    reusable = find_reusable_transfer_directory(local_base_dir, remote_bag_paths)
    if reusable:
        return reusable, f"[续传] 复用已有未完成目录: {reusable}"
    if not os.path.exists(base):
        return base, ""
    if os.path.isdir(base) and not is_transfer_complete_directory(base):
        return base, f"[续传] 复用未完成的本地目录: {base}"
    return unique_directory_path(base), ""
