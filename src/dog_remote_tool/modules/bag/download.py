from __future__ import annotations

import os
import time
from typing import Callable

from dog_remote_tool.modules.bag import logs as bag_logs
from dog_remote_tool.modules.bag.names import local_bag_name_from_remote


ProgressCallback = Callable[[str, float, str], None]


def download_remote_bags(
    remote_bag_paths: list[str],
    bag_dir: str,
    wait_remote_bags_finalized_paths: Callable[[list[str], int], set[str]],
    wait_remote_bags_finalized: Callable[[list[str], int], bool],
    build_rsync_command: Callable[..., list[str]],
    run_rsync_with_progress: Callable[..., bool],
    log: Callable[[str], None],
    progress: ProgressCallback | None = None,
) -> bool:
    bag_results = []
    finalized_paths = wait_remote_bags_finalized_paths(remote_bag_paths, 180) if len(remote_bag_paths) > 1 else set()
    for index, remote_path in enumerate(remote_bag_paths, start=1):
        name = os.path.basename(remote_path)
        local_name = local_bag_name_from_remote(remote_path)
        local_bag_dir = os.path.join(bag_dir, local_name)
        if remote_path in finalized_paths:
            log(f"远端Bag已收尾，开始下载: {name}")
        else:
            log(f"等待远端Bag收尾: {name}")
            if not wait_remote_bags_finalized([remote_path], 180):
                bag_results.append(False)
                log(f"✗ Bag包未完成收尾，已跳过下载: {name}")
                continue
        os.makedirs(local_bag_dir, exist_ok=True)
        log(f"正在下载Bag包: {name} -> {local_name}")
        cmd = build_rsync_command(
            remote_path.rstrip("/") + "/",
            local_bag_dir + os.sep,
            rsync_args=["-avz", "--info=progress2", "--partial", "--append-verify", "-r"],
        )
        ok = False
        max_attempts = 4
        for attempt in range(1, max_attempts + 1):
            if attempt > 1:
                log(f"[续传] Bag包下载中断，正在第 {attempt}/{max_attempts} 次续传: {name}")
                time.sleep(min(10, attempt * 2))
            ok = run_rsync_with_progress(
                cmd,
                f"正在拉取Bag包 {index}/{len(remote_bag_paths)}",
                1000,
                progress,
                f"{name} ",
            )
            if ok:
                break
        bag_results.append(ok)
        log(("✓" if ok else "✗") + f" Bag包下载{'完成' if ok else '失败'}: {name}")
    return bool(bag_results) and all(bag_results)


def download_remote_logs(
    log_dir: str,
    product: str,
    resolve_remote_log_paths: Callable[[], list[str]],
    local_log_source_dir: Callable[[str], str],
    build_rsync_command: Callable[..., list[str]],
    run_rsync_with_progress: Callable[..., bool],
    log: Callable[[str], None],
    progress: ProgressCallback | None = None,
    log_kind: str = "all",
) -> bool:
    remote_logs = resolve_remote_log_paths()
    if not remote_logs:
        checked_paths = bag_logs.candidate_log_paths(product, log_kind)
        log(f"✗ 未找到可用Log目录，已检查: {', '.join(checked_paths)}")
        return False

    log_results = []
    for remote_log in remote_logs:
        source_dir = local_log_source_dir(remote_log) if len(remote_logs) > 1 or log_kind != "all" else ""
        local_log_dir = os.path.join(log_dir, source_dir) if source_dir else log_dir
        os.makedirs(local_log_dir, exist_ok=True)
        target_note = f"log/{source_dir}" if source_dir else "log/"
        log(f"正在下载Log目录: {remote_log} -> {target_note}")
        cmd = build_rsync_command(
            remote_log.rstrip("/") + "/",
            local_log_dir + os.sep,
            rsync_args=["-az", "--info=progress2", "--partial", "-r"],
            excludes=["*.mcap", "*.db3"],
        )
        ok = run_rsync_with_progress(
            cmd,
            "正在拉取Log",
            300,
            progress,
            "Log ",
        )
        log_results.append(ok)
        log(("✓" if ok else "✗") + f" Log目录下载{'完成' if ok else '失败'}: {remote_log}")
    log_success = bool(log_results) and all(log_results)
    log("✓ Log文件下载完成" if log_success else "✗ Log文件下载失败")
    return log_success
