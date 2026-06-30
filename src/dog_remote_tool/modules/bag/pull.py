from __future__ import annotations

import os
from datetime import datetime
from typing import Callable

from dog_remote_tool.core.profiles import ProductProfile
from dog_remote_tool.modules.bag.names import safe_filename_component, standard_dataset_name


def pull_bag_and_log_locked(
    backend,
    product: str,
    profile: ProductProfile,
    log: Callable[[str], None],
    remote_bag_paths: list[str],
    local_base_dir: str,
    expected_topics: list[str],
    include_bag: bool,
    include_log: bool,
    delete_remote_on_success: bool = False,
    progress: Callable[[str, float, str], None] | None = None,
    record_info: dict | None = None,
    log_kind: str = "all",
) -> dict:
    transfer_time = datetime.now()
    record_info = dict(record_info or {})
    fallback_name = standard_dataset_name(product, profile, transfer_time)
    dataset_name = safe_filename_component(str(record_info.get("dataset_name") or fallback_name), fallback_name)
    if not include_bag:
        dataset_name = f"log_{dataset_name}"

    target_dir = backend.transfer_target_directory(local_base_dir, dataset_name, remote_bag_paths, include_bag)
    bag_dir = target_dir
    log_dir = os.path.join(target_dir, "log")
    calibration_dir = os.path.join(target_dir, "calibration")
    if include_bag:
        os.makedirs(bag_dir, exist_ok=True)
    if include_bag:
        os.makedirs(calibration_dir, exist_ok=True)
    if include_log:
        os.makedirs(log_dir, exist_ok=True)

    bag_success = not include_bag
    log_success = not include_log
    calibration_success = False
    deleted: list[str] = []
    delete_failed: list[str] = []

    if include_bag:
        bag_success = backend.download_remote_bags(remote_bag_paths, bag_dir, progress)
    if include_log:
        log_success = backend.download_remote_logs(log_dir, progress, log_kind)
    if include_bag:
        calibration_success = backend.download_calibration_files(calibration_dir)
    if delete_remote_on_success and include_bag and bag_success and log_success and remote_bag_paths:
        log("[清理] 回传成功，开始自动删除远端Bag...")
        deleted, delete_failed = backend.delete_remote_bags(remote_bag_paths, auto_delete=True)

    validation = (
        backend.validate_pulled_recording(target_dir, bag_success, log_success, expected_topics)
        if include_bag
        else {"ok": True, "summary": "Log单独拉取完成", "details": ["未执行Bag校验"]}
    )
    summary_file = ""
    try:
        summary_file = backend.write_record_summary(
            target_dir=target_dir,
            dataset_name=dataset_name,
            remote_bag_paths=remote_bag_paths,
            expected_topics=expected_topics,
            include_bag=include_bag,
            include_log=include_log,
            bag_success=bag_success,
            log_success=log_success,
            calibration_success=calibration_success,
            deleted=deleted,
            delete_failed=delete_failed,
            validation=validation,
            record_info=record_info,
            transfer_time=transfer_time,
        )
        if summary_file:
            log(f"✓ 回传说明文件已生成: {os.path.relpath(summary_file, target_dir)}")
    except Exception as exc:
        log(f"  回传说明文件生成失败: {exc}")

    transfer_complete = (not include_bag or bag_success) and (not include_log or log_success) and bool(validation.get("ok", True))
    backend.write_transfer_state_marker(target_dir, transfer_complete)
    return {
        "target_dir": target_dir,
        "summary_file": summary_file,
        "bag_success": bag_success,
        "log_success": log_success,
        "calibration_success": calibration_success,
        "calibration_attempted": include_bag,
        "deleted": deleted,
        "delete_failed": delete_failed,
        "validation": validation,
    }
