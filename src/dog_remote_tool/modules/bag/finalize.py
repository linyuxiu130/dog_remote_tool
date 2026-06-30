from __future__ import annotations

import os
import time
from typing import Callable


BagStatus = dict[str, int]
BagStatusMap = dict[str, BagStatus]


def unique_remote_paths(remote_bag_paths: list[str]) -> list[str]:
    return list(dict.fromkeys(path for path in remote_bag_paths if path))


def bag_status_ready(status: BagStatus, stable_count: int) -> bool:
    return (
        status["exists"] == 1
        and status["active"] == 0
        and status["meta"] == 1
        and status["size"] > 0
        and stable_count >= 1
    )


def bag_status_needs_reindex(status: BagStatus, stable_count: int) -> bool:
    return (
        status["exists"] == 1
        and status["active"] == 0
        and status["meta"] == 0
        and status["size"] > 0
        and stable_count >= 1
    )


def wait_remote_bags_finalized_paths(
    remote_bag_paths: list[str],
    remote_bag_statuses: Callable[[list[str]], BagStatusMap],
    remote_bag_status: Callable[[str], BagStatus],
    reindex_remote_bag: Callable[[str], bool],
    log: Callable[[str], None],
    timeout: int = 180,
    sleep_interval: float = 2.0,
) -> set[str]:
    paths = unique_remote_paths(remote_bag_paths)
    if not paths:
        return set()

    deadline = time.time() + timeout
    last_sizes: dict[str, int] = {}
    stable_counts = {path: 0 for path in paths}
    reindexed = set()
    ready_paths: set[str] = set()
    while time.time() < deadline:
        all_ready = True
        status_parts = []
        try:
            statuses = remote_bag_statuses(paths)
        except Exception as exc:
            statuses = {}
            batch_error = str(exc)[:80]
        else:
            batch_error = ""

        for remote_path in paths:
            try:
                if batch_error:
                    raise RuntimeError(batch_error)
                status = statuses.get(remote_path)
                if status is None:
                    raise RuntimeError("status_missing")
            except Exception as exc:
                all_ready = False
                status_parts.append(f"{os.path.basename(remote_path)} status_error={str(exc)[:80]}")
                continue

            size = status["size"]
            if last_sizes.get(remote_path) == size and size > 0:
                stable_counts[remote_path] += 1
            else:
                stable_counts[remote_path] = 0
            last_sizes[remote_path] = size

            if bag_status_needs_reindex(status, stable_counts[remote_path]) and remote_path not in reindexed:
                reindexed.add(remote_path)
                log(f"[录制] Bag缺少 metadata，尝试重建: {os.path.basename(remote_path)}")
                if reindex_remote_bag(remote_path):
                    status = remote_bag_status(remote_path)
                else:
                    return ready_paths

            ready = bag_status_ready(status, stable_counts[remote_path])
            if ready:
                ready_paths.add(remote_path)
            else:
                ready_paths.discard(remote_path)
            all_ready = all_ready and ready
            status_parts.append(
                f"{os.path.basename(remote_path)} active={status['active']} meta={status['meta']} size={status['size']}"
            )
        if all_ready:
            log("[录制] 远端Bag已完成收尾: " + "; ".join(status_parts))
            return ready_paths
        time.sleep(sleep_interval)
    log("[录制] 等待远端Bag收尾超时")
    return ready_paths
