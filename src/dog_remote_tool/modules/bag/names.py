from __future__ import annotations

import os
import re
from datetime import datetime

from dog_remote_tool.core.units import format_byte_size
from dog_remote_tool.core.profiles import ProductProfile


def normalize_topic(topic: str) -> str:
    topic = topic.strip()
    if not topic or topic.startswith("#"):
        return ""
    if not topic.startswith("/"):
        topic = f"/{topic}"
    return topic


def safe_filename_component(value: str, default: str = "bag") -> str:
    value = re.sub(r"[^A-Za-z0-9._-]+", "_", (value or "").strip())
    value = re.sub(r"_+", "_", value).strip("._-")
    return value or default


def data_package_prefix(product: str, profile: ProductProfile) -> str:
    if product == "nxl2" or profile.key == "xg2_s100":
        return "L2"
    if product in {"zg", "zgnx"} or profile.key in {"zg3588", "zg_surround_3588", "zg_lidar_nx", "zg_surround_s100"}:
        return "ZG"
    return "XG"


def standard_remote_bag_name(product: str, profile: ProductProfile, timestamp: datetime | None = None) -> str:
    timestamp = timestamp or datetime.now()
    prefix = data_package_prefix(product, profile).lower()
    return f"rosbag2_{prefix}_{timestamp:%Y%m%d_%H%M%S}"


def standard_dataset_name(product: str, profile: ProductProfile, timestamp: datetime | None = None) -> str:
    timestamp = timestamp or datetime.now()
    prefix = data_package_prefix(product, profile)
    return f"{prefix}_{timestamp:%Y%m%d_%H%M%S}"


def dataset_name_from_remote_bags(remote_bag_paths: list[str]) -> str:
    names = [os.path.basename(path.rstrip("/")) for path in remote_bag_paths if path.strip()]
    if not names:
        return ""
    parsed = []
    for name in names:
        match = re.match(r"^(?:rosbag2_)?([A-Za-z0-9]+)_(\d{8}_\d{6})$", name)
        if match:
            parsed.append(f"{match.group(1).upper()}_{match.group(2)}")
        else:
            parsed.append(safe_filename_component(name, "bag"))
    if len(parsed) == 1:
        return parsed[0]
    return safe_filename_component("multi_" + "_".join(parsed[:3]), "multi_bag")


def local_bag_name_from_remote(remote_bag_path: str) -> str:
    name = os.path.basename(remote_bag_path.rstrip("/"))
    match = re.match(r"^(?:rosbag2_)?([A-Za-z0-9]+)_(\d{8}_\d{6})$", name)
    if match:
        return safe_filename_component(f"{match.group(1).upper()}_{match.group(2)}", "bag")
    return safe_filename_component(name, "bag")


def profile_product_key(profile: ProductProfile) -> str:
    mapping = {
        "xg3588": "xg",
        "xg2_3588": "xg",
        "zg3588": "zg",
        "zg_surround_3588": "zg",
        "xg1_nx": "nx",
        "xg2_s100": "nxl2",
        "zg_surround_s100": "zgnx",
        "zg_lidar_nx": "zgnx",
    }
    return mapping.get(profile.key, "nx")


def format_size(size_bytes: int | float) -> str:
    return format_byte_size(size_bytes, ("B", "KB", "MB", "GB", "TB"))


def format_rsync_speed(speed_text: str) -> str:
    match = re.match(r"\s*([0-9.,]+)\s*([A-Za-z]+/s)\s*", speed_text)
    if not match:
        return speed_text
    try:
        value = float(match.group(1).replace(",", ""))
    except ValueError:
        return speed_text
    unit = match.group(2)
    normalized_unit = {
        "B/s": "B/s",
        "kB/s": "KB/s",
        "KB/s": "KB/s",
        "MB/s": "MB/s",
        "GB/s": "GB/s",
        "TB/s": "TB/s",
    }.get(unit, unit)
    if normalized_unit == "B/s":
        return f"{int(round(value))} {normalized_unit}"
    return f"{value:.1f} {normalized_unit}"
