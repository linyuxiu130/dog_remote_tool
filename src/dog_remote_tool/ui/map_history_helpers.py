from __future__ import annotations

from pathlib import Path

from dog_remote_tool.core.units import format_byte_size


def format_history_map_size(size_text: str) -> str:
    try:
        size = float(size_text)
    except ValueError:
        return f"{size_text} B" if size_text else "--"
    return format_byte_size(size)


def history_map_display(remote_path: str, mtime: str, size: str) -> tuple[str, str]:
    parent = Path(remote_path).parent
    if parent.name and parent.parent.name == "history_map":
        name = parent.name
    elif parent.name == "map":
        name = "地图"
    else:
        name = parent.name or "地图"
    short_time = mtime[:16] if mtime else "--"
    readable_size = format_history_map_size(size)
    label = f"{short_time} | {readable_size} | {name}"
    detail = f"地图：{name}\n大小：{readable_size}\n目录：{parent}"
    return label, detail


def history_map_label_prefix(label: str) -> str:
    if "|" not in label:
        return ""
    compact = label.split("|", 1)[0].strip()
    return compact if compact and compact != "--" else ""


def history_map_timestamp_label(remote_pgm: str, *, include_seconds: bool = True) -> str:
    parent = Path(remote_pgm).parent
    name = parent.name or "地图"
    parts = name.split("_")
    if len(parts) >= 6 and parts[0].isdigit() and len(parts[0]) == 4:
        if not include_seconds:
            return f"{parts[1]}-{parts[2]} {parts[3]}:{parts[4]}"
        return f"{parts[1]}-{parts[2]} {parts[3]}:{parts[4]}:{parts[5]}"
    return ""


def compact_history_map_label(label: str, remote_pgm: str) -> str:
    compact = history_map_label_prefix(label)
    if compact:
        return compact
    parent = Path(remote_pgm).parent
    if parent.name == "map":
        return "地图"
    timestamp = history_map_timestamp_label(remote_pgm)
    if timestamp:
        return timestamp
    name = parent.name or "地图"
    return name


def is_history_map_pgm(remote_path: str) -> bool:
    path = Path(remote_path)
    parent = path.parent
    return path.name == "map.pgm" and bool(parent.name) and parent.parent.name == "history_map"


def format_disk_detail(avail: str, total: str, used_percent: str = "", target: str = "") -> str:
    if not avail or not total:
        return ""
    detail = f"可用空间 {format_history_map_size(avail)} / {format_history_map_size(total)}"
    if used_percent:
        detail += f"（已用 {used_percent}）"
    if target:
        detail += f"；分区 {target}"
    return detail


def parse_history_map_entries(output: str) -> list[tuple[str, str, str]]:
    entries: list[tuple[str, str, str]] = []
    seen: set[str] = set()
    for raw in output.splitlines():
        parts = raw.split("\t")
        if len(parts) != 4:
            continue
        _timestamp, mtime, size, remote_path = parts
        if not is_history_map_pgm(remote_path):
            continue
        if remote_path in seen:
            continue
        seen.add(remote_path)
        label, detail = history_map_display(remote_path, mtime, size)
        entries.append((label, remote_path, detail))
    return entries


def parse_history_map_disk_detail(output: str) -> str:
    for raw in output.splitlines():
        parts = raw.split("\t")
        if len(parts) >= 5 and parts[0] == "DISK":
            return format_disk_detail(parts[1], parts[2], parts[3], parts[4])
    return ""


def local_map_preview_dir(profile_key: str, host: str, remote_pgm: str, local_root: str) -> Path:
    safe_host = host.replace(".", "_").replace(":", "_")
    safe_remote = "".join(ch if ch.isalnum() else "_" for ch in str(Path(remote_pgm).parent).strip("/"))
    return Path(local_root) / "_preview" / f"{profile_key}_{safe_host}_{safe_remote}"


def local_map_pull_target_dir(remote_pgm: str, save_map_path: str, local_root: str) -> Path:
    remote_dir = Path(remote_pgm).parent
    remote_root = Path(save_map_path.rstrip("/"))
    try:
        rel_dir = remote_dir.relative_to(remote_root)
    except ValueError:
        rel_dir = Path(remote_dir.name)
    if rel_dir.parts[:1] == ("history_map",) and len(rel_dir.parts) > 1:
        rel_dir = Path(*rel_dir.parts[1:])
    return Path(local_root) / rel_dir
