from __future__ import annotations

import os
import shlex

from dog_remote_tool.core.parsers import parse_key_value_fields


def record_process_match_awk_functions() -> str:
    return r"""
function arg_boundary(cmd, pos, length_value) {
  c = substr(cmd, pos + length_value, 1)
  return c == "" || c == " " || c == "\t"
}
function has_output_path(cmd, path) {
  if (path == "") {
    return 0
  }
  pattern = " -o " path
  pos = index(cmd, pattern)
  if (pos > 0 && arg_boundary(cmd, pos, length(pattern))) {
    return 1
  }
  pattern = " -o=" path
  pos = index(cmd, pattern)
  if (pos > 0 && arg_boundary(cmd, pos, length(pattern))) {
    return 1
  }
  pattern = " --output " path
  pos = index(cmd, pattern)
  if (pos > 0 && arg_boundary(cmd, pos, length(pattern))) {
    return 1
  }
  pattern = " --output=" path
  pos = index(cmd, pattern)
  if (pos > 0 && arg_boundary(cmd, pos, length(pattern))) {
    return 1
  }
  return 0
}
""".strip()


def _remote_bag_status_shell() -> str:
    return (
        "active=$(ps -eww -o pid=,cmd= | awk -v path=\"$path\" '"
        + record_process_match_awk_functions()
        + "\nindex($0, \"ros2 bag record\") > 0 && has_output_path($0, path) {count++} END {print count+0}'); "
        "meta=0; [ -s \"$path/metadata.yaml\" ] && meta=1; "
        "size=$(find \"$path\" -maxdepth 1 -type f \\( -name '*.mcap' -o -name '*.db3' \\) -printf '%s\\n' 2>/dev/null | awk '{s+=$1} END{printf \"%.0f\", s+0}'); "
        "exists=0; [ -d \"$path\" ] && exists=1; "
    )


def remote_bag_status_command(remote_path: str) -> str:
    return (
        f"path={shlex.quote(remote_path)}; "
        + _remote_bag_status_shell()
        + "printf 'exists=%s active=%s meta=%s size=%s\\n' \"$exists\" \"$active\" \"$meta\" \"$size\""
    )


def remote_bag_statuses_command(remote_paths: list[str]) -> str:
    if not remote_paths:
        return "true"
    path_args = " ".join(shlex.quote(path) for path in remote_paths)
    return (
        f"for path in {path_args}; do "
        + _remote_bag_status_shell()
        + "printf '%s\\texists=%s active=%s meta=%s size=%s\\n' \"$path\" \"$exists\" \"$active\" \"$meta\" \"$size\"; "
        "done"
    )


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
    path_args = " ".join(shlex.quote(path) for path in remote_paths)
    return (
        "total=0; "
        f"for path in {path_args}; do "
        "size=$(find \"$path\" -maxdepth 1 -type f \\( -name '*.mcap' -o -name '*.db3' \\) "
        "-printf '%s\\n' 2>/dev/null | awk '{s+=$1} END{printf \"%.0f\", s+0}'); "
        "total=$((total + ${size:-0})); "
        "done; "
        "printf '%s\\n' \"$total\""
    )


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
