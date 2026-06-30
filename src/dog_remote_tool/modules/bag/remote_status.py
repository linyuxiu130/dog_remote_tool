from __future__ import annotations

import os
import shlex

from dog_remote_tool.core.parsers import parse_key_value_fields
from dog_remote_tool.modules.bag import remote_helper


def remote_bag_status_command(remote_path: str) -> str:
    return remote_helper.status_paths_command([remote_path])


def remote_bag_statuses_command(remote_paths: list[str]) -> str:
    if not remote_paths:
        return "true"
    return remote_helper.status_paths_command(remote_paths)


def parse_remote_bag_statuses(output: str) -> dict[str, dict[str, int]]:
    statuses: dict[str, dict[str, int]] = {}
    for line in output.splitlines():
        if "\t" not in line:
            continue
        path, status_text = line.split("\t", 1)
        if path:
            statuses[path] = parse_remote_bag_status(status_text)
    return statuses


def remote_bags_size_command(remote_paths: list[str]) -> str:
    if not remote_paths:
        return "printf '0\\n'"
    return remote_helper.sizes_command(remote_paths)


def parse_remote_bags_size(output: str) -> int:
    for line in reversed(output.splitlines()):
        value = line.strip()
        if value.isdigit():
            return int(value)
    return 0


def remote_bag_topic_counts_command(remote_paths: list[str]) -> str:
    if not remote_paths:
        return "true"
    path_args = " ".join(shlex.quote(path) for path in remote_paths)
    awk_script = r"""
/^[[:space:]]*name:[[:space:]]*/ {
  name=$0
  sub(/^[[:space:]]*name:[[:space:]]*/, "", name)
  gsub(/^["'\'' ]+|["'\'' ]+$/, "", name)
}
/^[[:space:]]*message_count:[[:space:]]*/ {
  count=$0
  sub(/^[[:space:]]*message_count:[[:space:]]*/, "", count)
  gsub(/[^0-9]/, "", count)
  if (name != "") {
    printf("TOPIC\t%s\t%s\t%s\n", path, name, count + 0)
    name=""
  }
}
""".strip()
    return (
        f"for path in {path_args}; do "
        "[ -s \"$path/metadata.yaml\" ] || { printf 'ERROR\\t%s\\t缺少 metadata.yaml\\n' \"$path\"; continue; }; "
        f"awk -v path=\"$path\" {shlex.quote(awk_script)} \"$path/metadata.yaml\"; "
        "done"
    )


def parse_remote_bag_topic_counts(output: str) -> tuple[dict[str, int], list[str]]:
    counts: dict[str, int] = {}
    errors: list[str] = []
    for line in output.splitlines():
        parts = line.split("\t")
        if len(parts) >= 4 and parts[0] == "TOPIC":
            topic = parts[2]
            try:
                count = int(parts[3])
            except ValueError:
                count = 0
            counts[topic] = counts.get(topic, 0) + count
        elif len(parts) >= 3 and parts[0] == "ERROR":
            errors.append(f"{os.path.basename(parts[1].rstrip('/')) or parts[1]}: {parts[2]}")
    return counts, errors


def parse_remote_bag_status(output: str) -> dict[str, int]:
    status = {"exists": 0, "active": 0, "meta": 0, "size": 0}
    for key, value in parse_key_value_fields(output).items():
        if key in status:
            status[key] = int(value) if value.isdigit() else 0
    return status
