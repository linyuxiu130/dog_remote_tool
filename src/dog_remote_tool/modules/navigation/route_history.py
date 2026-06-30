from __future__ import annotations

import hashlib
import json
import os
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any


ROUTE_HISTORY_SCHEMA = 1


@dataclass(frozen=True)
class RouteHistoryEntry:
    name: str
    path: Path
    remote_pgm: str
    node_ids: list[int]
    saved_at: str
    route_geojson_path: str = ""

    @property
    def point_count(self) -> int:
        return len(self.node_ids)

    def title_label(self) -> str:
        return compact_route_name(self.name, self.saved_at)

    def meta_label(self) -> str:
        saved_at = compact_saved_at_label(self.saved_at)
        if self.title_label() == "路线" and " " in saved_at:
            saved_at = saved_at.split(" ", 1)[1]
        elif saved_at.startswith(datetime.now().strftime("%m-%d ")):
            saved_at = saved_at.split(" ", 1)[1]
        parts = [f"{self.point_count}点"]
        if saved_at:
            parts.append(saved_at)
        return " · ".join(part for part in parts if part)

    def label(self) -> str:
        meta = self.meta_label()
        return f"{self.title_label()} · {meta}" if meta else self.title_label()

    def detail_label(self) -> str:
        meta = self.meta_label()
        return f"{self.title_label()} · {meta}" if meta else self.title_label()


def default_route_history_dir() -> Path:
    base = os.environ.get("XDG_DATA_HOME")
    if base:
        return Path(base) / "dog_remote_tool" / "route_history"
    return Path.home() / ".local" / "share" / "dog_remote_tool" / "route_history"


def default_route_history_name(now: datetime | None = None) -> str:
    now = now or datetime.now()
    return now.strftime("路线 %H:%M")


def compact_saved_at_label(saved_at: str) -> str:
    try:
        dt = datetime.fromisoformat(saved_at)
    except ValueError:
        return saved_at[:16].replace("T", " ")
    return dt.strftime("%m-%d %H:%M")


def full_saved_at_label(saved_at: str) -> str:
    try:
        dt = datetime.fromisoformat(saved_at)
    except ValueError:
        return saved_at.replace("T", " ")
    return dt.strftime("%Y-%m-%d %H:%M:%S")


def compact_route_name(name: str, saved_at: str = "") -> str:
    text = name.strip() or "路线"
    if re.fullmatch(r"路线 \d{4}-\d{2}-\d{2} \d{2}:\d{2}(?::\d{2})?", text):
        return "路线"
    if saved_at:
        short_time = compact_saved_at_label(saved_at).split(" ")[-1]
        if text in {f"路线 {short_time}", f"路线 {short_time}:00"}:
            return "路线"
    return text


def _safe_filename_part(text: str) -> str:
    safe = re.sub(r"[^0-9A-Za-z._-]+", "_", text.strip())
    safe = safe.strip("._-")
    return safe[:48] or "route"


def route_history_filename(remote_pgm: str, name: str, saved_at: str) -> str:
    source = f"{remote_pgm}\n{name}\n{saved_at}"
    digest = hashlib.sha1(source.encode("utf-8")).hexdigest()[:12]
    return f"{_safe_filename_part(name)}_{digest}.json"


def map_key(remote_pgm: str) -> str:
    return hashlib.sha1(remote_pgm.encode("utf-8")).hexdigest()[:16] if remote_pgm else "unmapped"


def save_route_history(
    *,
    name: str,
    remote_pgm: str,
    route_geojson_path: str,
    node_ids: list[int],
    waypoints_text: str,
    base_dir: Path | None = None,
    now: datetime | None = None,
) -> Path:
    clean_node_ids = [int(node_id) for node_id in node_ids]
    if not clean_node_ids:
        raise ValueError("至少需要一个路网目标节点")
    name = name.strip() or default_route_history_name(now)
    saved_at = (now or datetime.now()).replace(microsecond=0).isoformat()
    root = base_dir or default_route_history_dir()
    target_dir = root / map_key(remote_pgm)
    target_dir.mkdir(parents=True, exist_ok=True)
    path = target_dir / route_history_filename(remote_pgm, name, saved_at)
    payload: dict[str, Any] = {
        "schema": ROUTE_HISTORY_SCHEMA,
        "name": name,
        "saved_at": saved_at,
        "remote_pgm": remote_pgm,
        "route_geojson_path": route_geojson_path,
        "node_ids": clean_node_ids,
        "waypoints_text": waypoints_text,
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def read_route_history(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("路线历史格式无效")
    node_ids = data.get("node_ids")
    if not isinstance(node_ids, list) or not node_ids:
        raise ValueError("路线历史缺少路网节点")
    data["node_ids"] = [int(node_id) for node_id in node_ids]
    data["name"] = str(data.get("name") or path.stem)
    data["remote_pgm"] = str(data.get("remote_pgm") or "")
    data["saved_at"] = str(data.get("saved_at") or "")
    data["route_geojson_path"] = str(data.get("route_geojson_path") or "")
    data["waypoints_text"] = str(data.get("waypoints_text") or "")
    return data


def list_route_histories(remote_pgm: str, base_dir: Path | None = None) -> list[RouteHistoryEntry]:
    root = base_dir or default_route_history_dir()
    target_dir = root / map_key(remote_pgm)
    if not target_dir.exists():
        return []
    entries: list[RouteHistoryEntry] = []
    for path in target_dir.glob("*.json"):
        try:
            data = read_route_history(path)
        except (OSError, ValueError, json.JSONDecodeError):
            continue
        if data["remote_pgm"] != remote_pgm:
            continue
        entries.append(
            RouteHistoryEntry(
                name=data["name"],
                path=path,
                remote_pgm=data["remote_pgm"],
                node_ids=data["node_ids"],
                saved_at=data["saved_at"],
                route_geojson_path=data["route_geojson_path"],
            )
        )
    return sorted(entries, key=lambda item: (item.saved_at, item.path.name), reverse=True)
