from __future__ import annotations

import ast
import math
from pathlib import Path
import re

from dog_remote_tool.core.parsers import parse_key_value_fields, parse_key_values
from dog_remote_tool.modules import mapping
from dog_remote_tool.ui.map_helpers import local_map_pull_target_dir, parse_history_map_entries

try:
    import yaml
except ImportError:  # pragma: no cover - fallback covers minimal map.yaml parsing.
    yaml = None


def parse_map_list_entries(output: str) -> list[tuple[str, str, str]]:
    return parse_history_map_entries(output)


def local_map_directory(remote_pgm: str, save_map_path: str, local_root: str = mapping.DEFAULT_LOCAL_MAP_DIR) -> Path:
    return local_map_pull_target_dir(remote_pgm, save_map_path, local_root)


def read_map_yaml_metadata(yaml_path: str) -> tuple[float, tuple[float, float, float]] | None:
    try:
        lines = Path(yaml_path).read_text(encoding="utf-8").splitlines()
        resolution = 0.0
        origin = (0.0, 0.0, 0.0)
        for raw in lines:
            line = raw.strip()
            if line.startswith("resolution:"):
                resolution = float(line.split(":", 1)[1].split("#", 1)[0].strip())
            elif line.startswith("origin:"):
                parsed = ast.literal_eval(line.split(":", 1)[1].split("#", 1)[0].strip())
                origin = (float(parsed[0]), float(parsed[1]), float(parsed[2] if len(parsed) > 2 else 0.0))
        if resolution <= 0:
            return None
        return resolution, origin
    except (OSError, ValueError, SyntaxError, IndexError):
        return None


def read_map_yaml_charging_docks(yaml_path: str) -> list[tuple[int, float, float, float]]:
    try:
        text = Path(yaml_path).read_text(encoding="utf-8")
    except OSError:
        return []
    if yaml is not None:
        try:
            parsed_yaml = yaml.safe_load(text) or {}
        except yaml.YAMLError:
            parsed_yaml = {}
        if isinstance(parsed_yaml, dict):
            try:
                flag_enabled = int(parsed_yaml.get("arc_position_flag", 0)) == 1
            except (TypeError, ValueError):
                flag_enabled = bool(parsed_yaml.get("arc_position_flag"))
            if not flag_enabled:
                return []
            return _parse_arc_entries(parsed_yaml.get("arc"))
    flag_enabled = False
    docks: list[tuple[int, float, float, float]] = []
    lines = text.splitlines()
    for raw in lines:
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        value = line.split("#", 1)[0].strip()
        if value.startswith("arc_position_flag:"):
            flag_text = value.split(":", 1)[1].strip()
            flag_enabled = flag_text in {"1", "true", "True", "yes", "Yes"}
            continue
        if value.startswith("arc:"):
            arc_text = value.split(":", 1)[1].strip()
            if not arc_text or arc_text == "[]":
                continue
            try:
                parsed = ast.literal_eval(arc_text)
            except (ValueError, SyntaxError):
                docks.extend(_parse_arc_text(arc_text))
                continue
            docks.extend(_parse_arc_entries(parsed))
    return docks if flag_enabled else []


def _parse_arc_entries(entries) -> list[tuple[int, float, float, float]]:
    if not isinstance(entries, list):
        return []
    docks: list[tuple[int, float, float, float]] = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        position = entry.get("arc_position")
        if not isinstance(position, (list, tuple)) or len(position) < 2:
            continue
        try:
            tag_id = int(entry.get("tag_id", len(docks)))
            x = float(position[0])
            y = float(position[1])
            yaw = float(position[2]) if len(position) >= 3 else 0.0
        except (TypeError, ValueError):
            continue
        docks.append((tag_id, x, y, yaw))
    return docks


def _parse_arc_text(arc_text: str) -> list[tuple[int, float, float, float]]:
    docks: list[tuple[int, float, float, float]] = []
    for match in re.finditer(r"tag_id\s*:\s*(-?\d+).*?arc_position\s*:\s*\[([^\]]+)\]", arc_text):
        try:
            tag_id = int(match.group(1))
            parts = [float(part.strip()) for part in match.group(2).split(",") if part.strip()]
            if len(parts) < 2:
                continue
            yaw = parts[2] if len(parts) >= 3 else 0.0
        except ValueError:
            continue
        docks.append((tag_id, parts[0], parts[1], yaw))
    return docks


def parse_pose_probe(output: str) -> tuple[float, float, float] | None:
    values = parse_key_values(output)
    if values.get("POSE") != "ok":
        return None
    return _pose_from_values(values)


def parse_pose_stream_line(line: str) -> tuple[float, float, float] | None:
    if not line.startswith("POSE=ok "):
        return None
    values = parse_key_value_fields(line)
    return _pose_from_values(values)


def _pose_from_values(values: dict[str, str]) -> tuple[float, float, float] | None:
    try:
        return float(values["X"]), float(values["Y"]), float(values.get("YAW", "0"))
    except (KeyError, ValueError):
        return None


def consume_pose_stream_output(buffer: str, chunk: str) -> tuple[str, tuple[float, float, float] | None]:
    text = buffer + chunk
    lines = text.split("\n")
    remaining = lines.pop() if not text.endswith("\n") else ""
    for line in reversed(lines):
        pose = parse_pose_stream_line(line.strip())
        if pose:
            return remaining, pose
    return remaining, None


def parse_plan_stream_line(line: str) -> tuple[str, str, list[tuple[float, float, float]]] | None:
    if not line.startswith("PLAN="):
        return None
    prefix, _sep, points_text = line.partition(" POINTS=")
    values = parse_key_value_fields(prefix)
    kind = values.get("PLAN", "").upper()
    topic = values.get("TOPIC", "")
    if kind not in {"GLOBAL", "LOCAL"}:
        return None
    points: list[tuple[float, float, float]] = []
    for raw_point in points_text.split(";"):
        raw_point = raw_point.strip()
        if not raw_point:
            continue
        parts = raw_point.split(",")
        if len(parts) < 2:
            continue
        try:
            x = float(parts[0])
            y = float(parts[1])
            yaw = float(parts[2]) if len(parts) >= 3 else 0.0
        except ValueError:
            continue
        points.append((x, y, yaw))
    return kind, topic, points


def consume_plan_stream_output(
    buffer: str,
    chunk: str,
) -> tuple[str, list[tuple[str, str, list[tuple[float, float, float]]]]]:
    text = buffer + chunk
    lines = text.split("\n")
    remaining = lines.pop() if not text.endswith("\n") else ""
    updates = []
    for line in lines:
        parsed = parse_plan_stream_line(line.strip())
        if parsed:
            updates.append(parsed)
    return remaining, updates


def parse_obstacle_stream_line(line: str) -> tuple[str, list[tuple[float, float]]] | None:
    if not line.startswith("OBS=ok "):
        return None
    prefix, _sep, points_text = line.partition(" POINTS=")
    values = parse_key_value_fields(prefix)
    topic = values.get("TOPIC", "")
    points: list[tuple[float, float]] = []
    for raw_point in points_text.split(";"):
        raw_point = raw_point.strip()
        if not raw_point:
            continue
        parts = raw_point.split(",")
        if len(parts) < 2:
            continue
        try:
            points.append((float(parts[0]), float(parts[1])))
        except ValueError:
            continue
    return topic, points


def consume_obstacle_stream_output(
    buffer: str,
    chunk: str,
) -> tuple[str, list[tuple[str, list[tuple[float, float]]]]]:
    text = buffer + chunk
    lines = text.split("\n")
    remaining = lines.pop() if not text.endswith("\n") else ""
    updates = []
    for line in lines:
        parsed = parse_obstacle_stream_line(line.strip())
        if parsed:
            updates.append(parsed)
    return remaining, updates


def should_add_track_point(
    points: list[tuple[float, float, float]],
    x: float,
    y: float,
    min_distance: float = 0.01,
) -> bool:
    if not points:
        return True
    last_x, last_y, _last_yaw = points[-1]
    return math.hypot(x - last_x, y - last_y) >= min_distance
