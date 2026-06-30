from __future__ import annotations

from pathlib import Path

from dog_remote_tool.modules.navigation.route_network import MapMetadata


def read_map_yaml(path: str | Path) -> MapMetadata:
    yaml_path = Path(path)
    values: dict[str, str] = {}
    for raw in yaml_path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.split("#", 1)[0].strip()
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        values[key.strip()] = value.strip().strip("'\"")
    image_value = values.get("image", "map.pgm")
    image_path = Path(image_value)
    if not image_path.is_absolute():
        image_path = yaml_path.parent / image_path
    resolution = float(values.get("resolution", "0"))
    occupied_thresh = float(values.get("occupied_thresh", "0.65"))
    free_thresh = float(values.get("free_thresh", "0.196"))
    negate = int(float(values.get("negate", "0")))
    origin_text = values.get("origin", "[0, 0, 0]").strip().strip("[]")
    origin_parts = [float(part.strip()) for part in origin_text.split(",") if part.strip()]
    while len(origin_parts) < 3:
        origin_parts.append(0.0)
    return MapMetadata(
        image_path=image_path,
        resolution=resolution,
        origin=(origin_parts[0], origin_parts[1], origin_parts[2]),
        occupied_thresh=occupied_thresh,
        free_thresh=free_thresh,
        negate=negate,
    )
