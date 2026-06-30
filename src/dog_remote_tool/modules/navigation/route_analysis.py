from __future__ import annotations

from collections import Counter
import json
from pathlib import Path
from typing import Any, Iterator


NAV_POINT_REQUIRED_FIELDS = ("id",)
NAV_EDGE_REQUIRED_FIELDS = ("id", "startid", "endid", "direction")


def analyze_geojson_file(path: str | Path) -> dict[str, Any]:
    source = Path(path)
    stat = source.stat()
    data = json.loads(source.read_text(encoding="utf-8"))
    features = data.get("features", []) if isinstance(data, dict) else []
    if not isinstance(features, list):
        features = []

    geometry_counts: Counter[str] = Counter()
    property_stats: dict[str, dict[str, Any]] = {}
    feature_summaries: list[dict[str, Any]] = []
    coordinate_pairs: list[tuple[float, float]] = []
    coordinate_dimensions: Counter[int] = Counter()
    third_values: list[float] = []
    point_required = {required_field: 0 for required_field in NAV_POINT_REQUIRED_FIELDS}
    edge_required = {required_field: 0 for required_field in NAV_EDGE_REQUIRED_FIELDS}

    for index, feature in enumerate(features, start=1):
        if not isinstance(feature, dict):
            continue
        geometry = feature.get("geometry") or {}
        if not isinstance(geometry, dict):
            geometry = {}
        properties = feature.get("properties") or {}
        if not isinstance(properties, dict):
            properties = {}
        geometry_type = str(geometry.get("type") or "None")
        geometry_counts[geometry_type] += 1
        coords = list(_iter_coordinate_pairs(geometry.get("coordinates")))
        coordinate_pairs.extend(coords)
        for coord in _iter_coordinates(geometry.get("coordinates")):
            coordinate_dimensions[len(coord)] += 1
            if len(coord) >= 3:
                third_values.append(float(coord[2]))

        if geometry_type == "Point":
            for required_field in NAV_POINT_REQUIRED_FIELDS:
                if required_field in properties:
                    point_required[required_field] += 1
        if geometry_type in {"LineString", "MultiLineString"}:
            for required_field in NAV_EDGE_REQUIRED_FIELDS:
                if required_field in properties:
                    edge_required[required_field] += 1

        for property_name, value in properties.items():
            field_stat = property_stats.setdefault(
                str(property_name),
                {"count": 0, "types": Counter(), "unique": set(), "examples": []},
            )
            field_stat["count"] += 1
            field_stat["types"][type(value).__name__] += 1
            value_key = _stable_value_text(value)
            field_stat["unique"].add(value_key)
            if len(field_stat["examples"]) < 3 and value_key not in field_stat["examples"]:
                field_stat["examples"].append(value_key)

        feature_summaries.append(
            {
                "index": index,
                "geometry": geometry_type,
                "id": properties.get("id"),
                "properties": properties,
                "coordinate_count": len(coords),
            }
        )

    bounds = None
    if coordinate_pairs:
        xs = [point[0] for point in coordinate_pairs]
        ys = [point[1] for point in coordinate_pairs]
        bounds = (min(xs), min(ys), max(xs), max(ys))

    return {
        "path": str(source),
        "file_size": stat.st_size,
        "modified": stat.st_mtime,
        "geojson_type": data.get("type") if isinstance(data, dict) else type(data).__name__,
        "feature_count": len(features),
        "geometry_counts": geometry_counts,
        "property_stats": property_stats,
        "features": feature_summaries,
        "bounds": bounds,
        "coordinate_dimensions": coordinate_dimensions,
        "third_coordinate_stats": _numeric_stats(third_values),
        "point_required": point_required,
        "edge_required": edge_required,
    }


def _iter_coordinate_pairs(value) -> Iterator[tuple[float, float]]:
    if isinstance(value, (list, tuple)):
        if len(value) >= 2 and all(isinstance(item, (int, float)) for item in value[:2]):
            yield float(value[0]), float(value[1])
            return
        for item in value:
            yield from _iter_coordinate_pairs(item)


def _iter_coordinates(value) -> Iterator[tuple[float, ...]]:
    if isinstance(value, (list, tuple)):
        if len(value) >= 2 and all(isinstance(item, (int, float)) for item in value[:2]):
            yield tuple(float(item) for item in value if isinstance(item, (int, float)))
            return
        for item in value:
            yield from _iter_coordinates(item)


def _numeric_stats(values: list[float]) -> dict[str, float | int] | None:
    if not values:
        return None
    return {
        "count": len(values),
        "min": min(values),
        "max": max(values),
        "mean": sum(values) / len(values),
    }


def _stable_value_text(value) -> str:
    if isinstance(value, str):
        return value
    try:
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    except TypeError:
        return str(value)
