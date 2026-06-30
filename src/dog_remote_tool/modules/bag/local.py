from __future__ import annotations

import os
from datetime import datetime

from dog_remote_tool.core.durations import format_seconds
from dog_remote_tool.modules.bag import metadata as bag_metadata


load_bag_metadata = bag_metadata.load_bag_metadata
local_bag_paths = bag_metadata.local_bag_paths
metadata_duration_seconds = bag_metadata.metadata_duration_seconds
metadata_topics = bag_metadata.metadata_topics
metadata_start_time_text = bag_metadata.metadata_start_time_text


def directory_size(path: str) -> int:
    total = 0
    if not os.path.exists(path):
        return total
    for root, _dirs, files in os.walk(path):
        for name in files:
            file_path = os.path.join(root, name)
            try:
                total += os.path.getsize(file_path)
            except OSError:
                pass
    return total


def format_duration(seconds: float | int | None) -> str:
    return format_seconds(seconds, none_text="-", always_hours=True)


def record_duration_seconds(record_info: dict, bag_dir: str) -> float | None:
    metadata_seconds = metadata_duration_seconds(bag_dir)
    if metadata_seconds is not None:
        return metadata_seconds
    value = record_info.get("duration_seconds")
    if isinstance(value, (int, float)) and value >= 0:
        return float(value)
    return None


def record_time_text(record_info: dict, transfer_time: datetime, bag_dir: str) -> str:
    metadata_started = metadata_start_time_text(bag_dir)
    if metadata_started:
        return metadata_started
    started = str(record_info.get("started_at") or "").strip()
    finished = str(record_info.get("finished_at") or "").strip()
    if started and finished:
        return f"{started} ~ {finished}"
    if started:
        return started
    return transfer_time.strftime("%Y-%m-%d %H:%M:%S")


def validate_single_bag_directory(bag_path: str) -> tuple[bool, list[str]]:
    metadata_info, details = load_bag_metadata(bag_path)
    data_files = []
    if metadata_info:
        data_files = [os.path.join(bag_path, rel) for rel in metadata_info.get("relative_file_paths", [])]
    if not data_files:
        data_files = [os.path.join(bag_path, name) for name in os.listdir(bag_path) if name.endswith((".mcap", ".db3"))]
    if not data_files:
        details.append(f"{os.path.basename(bag_path)}: 未找到 mcap/db3 数据文件")
        return False, details
    bad = []
    for file_path in data_files:
        if not os.path.exists(file_path):
            bad.append(f"{os.path.basename(file_path)} 不存在")
        elif os.path.getsize(file_path) <= 0:
            bad.append(f"{os.path.basename(file_path)} 大小为0")
    if bad:
        details.append(f"{os.path.basename(bag_path)}: " + "，".join(bad))
        return False, details
    total_size = sum(os.path.getsize(path) for path in data_files if os.path.exists(path))
    details.append(f"{os.path.basename(bag_path)}: 正常，数据文件 {len(data_files)} 个，总大小 {total_size / (1024 * 1024):.1f} MB")
    return True, details


def validate_topic_counts(topic_counts: dict[str, int], expected_topics: list[str], topic_units: list[dict], details: list[str] | None = None) -> dict:
    if not expected_topics:
        return {"ok": True, "summary": "未执行话题级检查（无录制目标缓存）", "details": []}
    details = list(details or [])
    ok_units = []
    failed_units = []
    for unit in topic_units:
        positive = [topic for topic in unit["topics"] if topic_counts.get(topic, 0) > 0]
        zero = [topic for topic in unit["topics"] if topic in topic_counts and topic_counts.get(topic, 0) <= 0]
        missing = [topic for topic in unit["topics"] if topic not in topic_counts]
        if positive:
            ok_units.append(unit["label"])
            if unit["is_group"]:
                details.append(f"候选Topic命中: {unit['label']} -> {', '.join(positive)}")
            continue
        failed_units.append(unit["label"])
        if unit["is_group"]:
            if missing:
                details.append(f"候选Topic缺失: {unit['label']} -> {', '.join(missing)}")
            if zero:
                details.append(f"候选Topic空数据: {unit['label']} -> {', '.join(zero)}")
        elif missing:
            details.append(f"缺失Topic: {unit['topics'][0]}")
        elif zero:
            details.append(f"空数据Topic: {unit['topics'][0]}")
    if ok_units:
        details.append(f"有数据Topic: {len(ok_units)}/{len(topic_units)}")
    if not failed_units:
        return {"ok": True, "summary": f"话题完整，{len(ok_units)}/{len(topic_units)} 个目标Topic均有数据", "details": details}
    if not ok_units:
        return {"ok": False, "summary": f"话题异常，{len(topic_units)} 个目标Topic均未正确录制", "details": details}
    return {"ok": False, "summary": f"话题部分异常，{len(ok_units)}/{len(topic_units)} 个目标Topic有数据", "details": details}


def validate_recorded_topics(bag_paths: list[str], expected_topics: list[str], topic_units: list[dict]) -> dict:
    if not expected_topics:
        return {"ok": True, "summary": "未执行话题级检查（无录制目标缓存）", "details": []}
    topic_counts: dict[str, int] = {}
    details = []
    for bag_path in bag_paths:
        metadata_info, metadata_errors = load_bag_metadata(bag_path)
        if metadata_errors:
            details.extend(metadata_errors)
            continue
        for item in metadata_info.get("topics_with_message_count", []):
            name = item.get("topic_metadata", {}).get("name")
            count = int(item.get("message_count", 0))
            if name:
                topic_counts[name] = topic_counts.get(name, 0) + count
    return validate_topic_counts(topic_counts, expected_topics, topic_units, details)


def validate_pulled_recording(
    target_dir: str,
    bag_success: bool,
    log_success: bool,
    expected_topics: list[str],
    topic_units: list[dict],
) -> dict:
    details = []
    bag_dir = target_dir
    log_dir = os.path.join(target_dir, "log")
    if not bag_success:
        return {"ok": False, "summary": "未完成，Bag未成功拉取", "details": ["Bag未成功拉取，跳过数据完整性检查"]}
    if not os.path.isdir(bag_dir):
        return {"ok": False, "summary": "异常，缺少 bag 目录", "details": ["缺少 bag 目录"]}
    bag_paths = local_bag_paths(bag_dir)
    if not bag_paths:
        return {"ok": False, "summary": "异常，bag 目录为空", "details": ["bag 目录为空"]}
    passed = 0
    for bag_path in sorted(bag_paths):
        ok, bag_details = validate_single_bag_directory(bag_path)
        details.extend(bag_details)
        if ok:
            passed += 1
    topic_validation = validate_recorded_topics(bag_paths, expected_topics, topic_units)
    details.extend(topic_validation["details"])
    if log_success and os.path.isdir(log_dir):
        details.append("log 目录已拉取")
    elif log_success:
        details.append("Log标记成功，但未找到 log 目录")
    else:
        details.append("Log未成功拉取")
    total = len(bag_paths)
    if passed == total and topic_validation["ok"]:
        return {"ok": True, "summary": f"正常，{total}/{total} 个Bag目录完整；{topic_validation['summary']}", "details": details}
    if passed == 0:
        return {"ok": False, "summary": f"异常，{total} 个Bag目录均不完整；{topic_validation['summary']}", "details": details}
    return {"ok": False, "summary": f"部分异常，{passed}/{total} 个Bag目录完整；{topic_validation['summary']}", "details": details}
