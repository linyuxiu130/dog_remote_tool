from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path

from dog_remote_tool.core.profiles import ProductProfile
from dog_remote_tool.modules.bag import local as bag_local
from dog_remote_tool.modules.bag.names import data_package_prefix, format_size


def record_summary_lines(
    product: str,
    profile: ProductProfile,
    target_dir: str,
    dataset_name: str,
    expected_topics: list[str],
    include_bag: bool,
    record_info: dict,
    transfer_time: datetime,
) -> list[str]:
    topics = list(dict.fromkeys(expected_topics or record_info.get("topics") or bag_local.metadata_topics(target_dir)))
    bag_paths = bag_local.local_bag_paths(target_dir) if include_bag else []
    data_size_bytes = (
        sum(bag_local.directory_size(path) for path in bag_paths)
        if bag_paths
        else bag_local.directory_size(target_dir)
    )
    topic_text = "<br>".join(f"`{topic}`" for topic in topics) if topics else "-"
    row = [
        dataset_name,
        data_package_prefix(product, profile),
        topic_text,
        bag_local.record_time_text(record_info, transfer_time, target_dir),
        bag_local.format_duration(bag_local.record_duration_seconds(record_info, target_dir)),
        format_size(data_size_bytes),
    ]
    return [
        "# 数据说明",
        "",
        "| 数据包名称 | 数据载体 | 所包含topic | 采集时间 | 采集时长 | 数据包大小 |",
        "| --- | --- | --- | --- | --- | --- |",
        "| " + " | ".join(row) + " |",
        "",
    ]


def write_record_summary(
    product: str,
    profile: ProductProfile,
    target_dir: str,
    dataset_name: str,
    expected_topics: list[str],
    include_bag: bool,
    record_info: dict,
    transfer_time: datetime,
) -> str:
    os.makedirs(target_dir, exist_ok=True)
    summary_path = os.path.join(target_dir, "record_summary.md")
    Path(summary_path).write_text(
        "\n".join(
            record_summary_lines(
                product,
                profile,
                target_dir,
                dataset_name,
                expected_topics,
                include_bag,
                record_info,
                transfer_time,
            )
        ),
        encoding="utf-8",
    )
    return summary_path
