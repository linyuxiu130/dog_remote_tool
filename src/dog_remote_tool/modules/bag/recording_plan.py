from __future__ import annotations

import shlex
from dataclasses import dataclass
from typing import Callable

from dog_remote_tool.core.shell import sudo_run_shell
from dog_remote_tool.core.profiles import ProductProfile
from dog_remote_tool.modules.bag.names import profile_product_key, standard_remote_bag_name


PRODUCT_RECORD_ENV = {
    "nx": {
        "ROS_DOMAIN_ID": "24",
        "RMW_IMPLEMENTATION": "rmw_zenoh_cpp",
        "ROS_LOCALHOST_ONLY": "0",
    },
    "nxl2": {
        "ROS_DOMAIN_ID": "24",
        "RMW_IMPLEMENTATION": "rmw_zenoh_cpp",
        "ROS_LOCALHOST_ONLY": "0",
    },
}
PRODUCT_STORAGE_OVERRIDES = {
    "nxl2": "sqlite3",
}
PROFILE_STORAGE_OVERRIDES = {
    "xg3588": "sqlite3",
}


@dataclass
class RecordPlan:
    command: str
    remote_paths: list[str]
    topics: list[str]
    zstd_topics: list[str]
    storage: str


def recording_storage_for_profile(profile: ProductProfile, product: str | None = None) -> str:
    product_key = product or profile_product_key(profile)
    return PROFILE_STORAGE_OVERRIDES.get(profile.key) or PRODUCT_STORAGE_OVERRIDES.get(product_key) or profile.bag_storage


def ros_env_lines(product: str) -> list[str]:
    lines = [
        "source /opt/ros/humble/setup.bash",
        "[ -f /opt/runtime/env.bash ] && source /opt/runtime/env.bash || true",
        "export ROS_LOG_DIR=${ROS_LOG_DIR:-/tmp/dog_remote_ros_log_$(id -un 2>/dev/null || echo robot)}",
        'mkdir -p "$ROS_LOG_DIR"',
    ]
    for key, value in PRODUCT_RECORD_ENV.get(product, {}).items():
        lines.append(f"export {key}={shlex.quote(value)}")
    return lines


def build_single_record_command(
    save_path: str,
    storage: str,
    cache_bytes: int,
    topics: list[str],
    storage_config_file: str | None = None,
) -> str:
    parts = [
        "ros2 bag record",
        f"-o {shlex.quote(save_path)}",
        f"--storage {shlex.quote(storage)}",
        f"--max-cache-size {cache_bytes}",
    ]
    if storage_config_file:
        parts.append(f"--storage-config-file {shlex.quote(storage_config_file)}")
    parts.extend(shlex.quote(topic) for topic in topics)
    return " ".join(parts)


def prepare_save_directory_lines(save_path: str) -> list[str]:
    quoted_save_path = shlex.quote(save_path)
    return [
        sudo_run_shell(fallback_without_sudo=False),
        f"if ! mkdir -p -- {quoted_save_path} 2>/tmp/dog_remote_bag_mkdir.err; then",
        f"  sudo_run mkdir -p -- {quoted_save_path}",
        "fi",
        f"if ! [ -w {quoted_save_path} ]; then",
        f"  sudo_run chown \"$(id -u):$(id -g)\" -- {quoted_save_path} || true",
        "fi",
        f"[ -w {quoted_save_path} ] || {{ echo '[ERROR] Bag保存目录不可写: {save_path}' >&2; exit 2; }}",
    ]


def build_record_plan(
    profile: ProductProfile,
    product: str,
    save_path: str,
    storage: str,
    cache_gb: int,
    topic_plan,
    log: Callable[[str], None],
) -> RecordPlan:
    storage_override = recording_storage_for_profile(profile, product)
    if storage_override and storage != storage_override:
        log(f"[录制] {profile.label} 远端不支持 {storage}，自动改用 {storage_override}")
        storage = storage_override
    normal_topics = topic_plan.normal_topics[:]
    topics = topic_plan.all_topics[:]
    if not topics:
        raise ValueError("请至少选择一个录制主题")

    save_path = (save_path.strip() or profile.home).rstrip("/") or profile.home
    bag_name = standard_remote_bag_name(product, profile)
    full_save_path = f"{save_path}/{bag_name}"
    cache_bytes = int(cache_gb) * 1024 * 1024 * 1024

    lines = ros_env_lines(product)
    lines.extend(prepare_save_directory_lines(save_path))
    lines.append(f"{build_single_record_command(full_save_path, storage, cache_bytes, normal_topics)} &")
    lines.append("pid_main=$!")
    lines.extend(
        [
            "cleanup() {",
            "  kill -SIGINT \"$pid_main\" 2>/dev/null || true",
            "}",
            "trap cleanup INT TERM HUP EXIT",
            "status=0",
            "wait \"$pid_main\" || status=$?",
            "trap - INT TERM HUP EXIT",
            "exit \"$status\"",
        ]
    )
    return RecordPlan("\n".join(lines), [full_save_path], topics, [], storage)
