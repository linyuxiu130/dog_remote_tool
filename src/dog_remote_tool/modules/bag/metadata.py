from __future__ import annotations

import os
from datetime import datetime

import yaml


def load_bag_metadata(bag_path: str) -> tuple[dict | None, list[str]]:
    metadata_path = os.path.join(bag_path, "metadata.yaml")
    if not os.path.exists(metadata_path):
        return None, [f"{os.path.basename(bag_path)}: 缺少 metadata.yaml"]
    try:
        with open(metadata_path, "r", encoding="utf-8") as fh:
            metadata = yaml.safe_load(fh) or {}
        return metadata.get("rosbag2_bagfile_information", {}), []
    except Exception as exc:
        return None, [f"{os.path.basename(bag_path)}: metadata.yaml 读取失败 ({exc})"]


def local_bag_paths(bag_dir: str) -> list[str]:
    if not os.path.isdir(bag_dir):
        return []
    paths = []
    for name in os.listdir(bag_dir):
        bag_path = os.path.join(bag_dir, name)
        if not os.path.isdir(bag_path):
            continue
        try:
            entries = os.listdir(bag_path)
        except OSError:
            continue
        if "metadata.yaml" in entries or any(item.endswith((".mcap", ".db3")) for item in entries):
            paths.append(bag_path)
    return paths


def metadata_duration_seconds(bag_dir: str) -> float | None:
    if not os.path.isdir(bag_dir):
        return None
    durations = []
    for bag_path in local_bag_paths(bag_dir):
        metadata, _errors = load_bag_metadata(bag_path)
        if not metadata:
            continue
        duration = metadata.get("duration")
        if isinstance(duration, dict):
            ns = duration.get("nanoseconds")
        else:
            ns = duration
        try:
            durations.append(float(ns) / 1_000_000_000)
        except (TypeError, ValueError):
            pass
    return max(durations) if durations else None


def metadata_topics(bag_dir: str) -> list[str]:
    if not os.path.isdir(bag_dir):
        return []
    topics: list[str] = []
    for bag_path in local_bag_paths(bag_dir):
        metadata, _errors = load_bag_metadata(bag_path)
        if not metadata:
            continue
        for item in metadata.get("topics_with_message_count") or []:
            topic_metadata = item.get("topic_metadata") if isinstance(item, dict) else None
            topic_name = topic_metadata.get("name") if isinstance(topic_metadata, dict) else ""
            if topic_name and topic_name not in topics:
                topics.append(topic_name)
    return topics


def metadata_start_time_text(bag_dir: str) -> str:
    if not os.path.isdir(bag_dir):
        return ""
    starts = []
    for bag_path in local_bag_paths(bag_dir):
        metadata, _errors = load_bag_metadata(bag_path)
        if not metadata:
            continue
        start = metadata.get("starting_time")
        if isinstance(start, dict):
            ns = start.get("nanoseconds_since_epoch")
        else:
            ns = start
        try:
            starts.append(float(ns) / 1_000_000_000)
        except (TypeError, ValueError):
            pass
    if not starts:
        return ""
    return datetime.fromtimestamp(min(starts)).strftime("%Y-%m-%d %H:%M:%S")
