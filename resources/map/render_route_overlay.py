#!/usr/bin/env python3
from __future__ import annotations

import argparse
import io
import math
from pathlib import Path

import yaml
from PIL import Image, ImageDraw, ImageFont


def choose_track_path(map_dir: Path, track_path: Path | None = None) -> Path:
    if track_path:
        return track_path
    candidates = [
        map_dir / "map.static" / "static_map.txt",
        map_dir / "static_map.txt",
        map_dir / "map.txt",
    ]
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return map_dir / "map.txt"


def parse_static_map_line(parts: list[str]) -> tuple[float, float] | None:
    if len(parts) < 18:
        return None
    try:
        values = [float(value) for value in parts[2:18]]
    except ValueError:
        return None
    x = values[3]
    y = values[7]
    if math.isfinite(x) and math.isfinite(y):
        return x, y
    return None


def load_track_points(track_path: Path) -> list[tuple[float, float]]:
    points: list[tuple[float, float]] = []
    for line in track_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split()
        static_point = parse_static_map_line(parts) if track_path.name == "static_map.txt" else None
        if static_point is not None:
            points.append(static_point)
            continue
        if len(parts) < 2:
            continue
        try:
            x = float(parts[0])
            y = float(parts[1])
        except ValueError:
            continue
        if math.isfinite(x) and math.isfinite(y):
            points.append((x, y))
    if not points:
        raise ValueError(f"轨迹文件没有可用点: {track_path}")
    return points


def choose_font(size: int):
    candidates = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ]
    for candidate in candidates:
        try:
            return ImageFont.truetype(candidate, size)
        except OSError:
            continue
    return ImageFont.load_default()


def parse_pgm_header(map_image_path: Path) -> tuple[int, int, int, int]:
    with map_image_path.open("rb") as f:
        magic = f.readline().strip()
        if magic != b"P5":
            raise ValueError(f"仅支持 P5 PGM，当前是: {magic!r}")

        tokens: list[bytes] = []
        header_end = 0
        while len(tokens) < 3:
            line = f.readline()
            if not line:
                raise ValueError(f"PGM 头部不完整: {map_image_path}")
            if line.startswith(b"#"):
                continue
            tokens.extend(line.split())
            header_end = f.tell()

        width = int(tokens[0])
        height = int(tokens[1])
        maxval = int(tokens[2])
        return width, height, maxval, header_end


def load_map_image(map_image_path: Path) -> Image.Image:
    width, height, maxval, header_end = parse_pgm_header(map_image_path)
    expected_bytes = width * height * (2 if maxval > 255 else 1)
    actual_bytes = map_image_path.stat().st_size - header_end

    if actual_bytes < expected_bytes:
        raise ValueError(
            f"地图文件不完整: {map_image_path.name} 声明需要 {expected_bytes} 字节像素数据，"
            f"实际只有 {actual_bytes} 字节。"
        )

    data = map_image_path.read_bytes()
    return Image.open(io.BytesIO(data)).convert("RGB")


def build_blank_canvas(
    track_points: list[tuple[float, float]],
    resolution: float,
    padding_m: float = 3.0,
) -> tuple[Image.Image, float, float]:
    xs = [x for x, _ in track_points]
    ys = [y for _, y in track_points]
    origin_x = min(xs) - padding_m
    origin_y = min(ys) - padding_m
    width = max(1, int((max(xs) - origin_x + padding_m) / resolution))
    height = max(1, int((max(ys) - origin_y + padding_m) / resolution))
    image = Image.new("RGB", (width, height), color=(255, 255, 255))
    return image, origin_x, origin_y


def expand_canvas_for_track(
    image: Image.Image,
    track_points: list[tuple[float, float]],
    resolution: float,
    origin_x: float,
    origin_y: float,
    padding_m: float = 1.0,
) -> tuple[Image.Image, float, float, bool]:
    width, height = image.size
    map_min_x = origin_x
    map_max_x = origin_x + width * resolution
    map_min_y = origin_y
    map_max_y = origin_y + height * resolution

    xs = [x for x, _ in track_points]
    ys = [y for _, y in track_points]
    new_min_x = min(map_min_x, min(xs) - padding_m)
    new_max_x = max(map_max_x, max(xs) + padding_m)
    new_min_y = min(map_min_y, min(ys) - padding_m)
    new_max_y = max(map_max_y, max(ys) + padding_m)

    new_width = max(width, int(math.ceil((new_max_x - new_min_x) / resolution)))
    new_height = max(height, int(math.ceil((new_max_y - new_min_y) / resolution)))
    expanded = new_width != width or new_height != height or new_min_x != origin_x or new_min_y != origin_y
    if not expanded:
        return image, origin_x, origin_y, False

    canvas = Image.new("RGB", (new_width, new_height), color=(255, 255, 255))
    paste_x = int(round((map_min_x - new_min_x) / resolution))
    paste_y = int(round(new_height - ((map_max_y - new_min_y) / resolution)))
    canvas.paste(image, (paste_x, paste_y))
    return canvas, new_min_x, new_min_y, True


def world_to_pixel(
    x: float,
    y: float,
    resolution: float,
    origin_x: float,
    origin_y: float,
    image_height: int,
) -> tuple[float, float]:
    px = (x - origin_x) / resolution
    py = image_height - ((y - origin_y) / resolution)
    return px, py


def scaled_size(image: Image.Image, ratio: float, minimum: int, maximum: int) -> int:
    return max(minimum, min(maximum, int(min(image.size) * ratio)))


def render_overlay(
    map_dir: Path,
    output_path: Path,
    track_path: Path | None = None,
    overlay_title: str | None = None,
    include_legend: bool = True,
) -> Path:
    map_image_path = map_dir / "map.pgm"
    map_yaml_path = map_dir / "map.yaml"
    explicit_track = track_path is not None
    track_path = choose_track_path(map_dir, track_path)

    if not map_image_path.is_file():
        raise FileNotFoundError(f"未找到地图图片: {map_image_path}")
    if not map_yaml_path.is_file():
        raise FileNotFoundError(f"未找到地图配置: {map_yaml_path}")
    if not track_path.is_file():
        raise FileNotFoundError(f"未找到轨迹文件: {track_path}")

    map_cfg = yaml.safe_load(map_yaml_path.read_text(encoding="utf-8"))
    resolution = float(map_cfg["resolution"])
    origin_x, origin_y, _ = map_cfg["origin"]

    track_points = load_track_points(track_path)
    map_warning = ""
    try:
        image = load_map_image(map_image_path)
        image, origin_x, origin_y, expanded = expand_canvas_for_track(
            image,
            track_points,
            resolution,
            origin_x,
            origin_y,
        )
        _, height = image.size
        if expanded:
            map_warning = "Canvas expanded to include full track"
    except Exception as exc:
        image, origin_x, origin_y = build_blank_canvas(track_points, resolution)
        _, height = image.size
        map_warning = f"Map fallback: {exc}"

    image = image.convert("RGBA")
    overlay = Image.new("RGBA", image.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    pixel_points = [world_to_pixel(x, y, resolution, origin_x, origin_y, height) for x, y in track_points]
    route_width = scaled_size(image, 0.005, 4, 10)
    point_radius = scaled_size(image, 0.003, 2, 6)

    if len(pixel_points) >= 2:
        for start, end in zip(pixel_points, pixel_points[1:]):
            draw.line((start, end), fill=(220, 20, 60, 195), width=route_width)
    for px, py in pixel_points:
        draw.ellipse(
            (px - point_radius, py - point_radius, px + point_radius, py + point_radius),
            fill=(220, 20, 60, 120),
        )

    label_font = choose_font(scaled_size(image, 0.013, 12, 17))

    markers = [
        (pixel_points[0], (34, 197, 94, 190)),
        (pixel_points[-1], (250, 204, 21, 195)),
    ]
    marker_radius = max(point_radius + 2, scaled_size(image, 0.0045, 4, 8))
    for (px, py), color in markers:
        draw.ellipse(
            (px - marker_radius, py - marker_radius, px + marker_radius, py + marker_radius),
            fill=color,
            outline=(255, 255, 255, 210),
            width=2,
        )

    if include_legend:
        title = overlay_title or ("Custom Route Overlay" if explicit_track else "Mapping Route Overlay")
        legend_lines = [
            title,
            f"Map: {map_dir.name}",
            f"Track: {track_path.relative_to(map_dir) if track_path.is_relative_to(map_dir) else track_path.name}",
            f"Track points: {len(track_points)}",
        ]
        if map_warning:
            legend_lines.append("Map image invalid, rendered on blank canvas")
        boxes = [draw.textbbox((0, 0), line, font=label_font) for line in legend_lines]
        line_height = max(bottom - top for _, top, _, bottom in boxes)
        legend_width = max(right - left for left, _, right, _ in boxes) + 24
        legend_height = line_height * len(legend_lines) + 28
        lx, ly = 24, 24
        draw.rounded_rectangle(
            (lx, ly, lx + legend_width, ly + legend_height),
            radius=10,
            fill=(255, 255, 255, 185),
            outline=(0, 0, 0, 90),
            width=1,
        )
        for idx, line in enumerate(legend_lines):
            draw.text((lx + 12, ly + 10 + idx * line_height), line, fill=(0, 0, 0, 210), font=label_font)

    image = Image.alpha_composite(image, overlay).convert("RGB")
    image.save(output_path)
    return output_path


def main():
    parser = argparse.ArgumentParser(description="根据 map.pgm/map.yaml 和轨迹文件生成轨迹叠加 PNG。")
    parser.add_argument("map_dir", help="地图目录，例如 ~/data/maps/2026_05_08_11_05_38")
    parser.add_argument(
        "-o",
        "--output",
        help="输出 PNG 路径。默认写到地图目录下的 map_route_overlay.png",
    )
    parser.add_argument(
        "--track",
        help="轨迹文件路径。未指定时只使用建图轨迹: map.static/static_map.txt、static_map.txt 或 map.txt。",
    )
    parser.add_argument(
        "--title",
        help="叠加图左上角标题。默认建图轨迹为 Mapping Route Overlay，自定义轨迹为 Custom Route Overlay。",
    )
    parser.add_argument(
        "--no-legend",
        action="store_true",
        help="不绘制左上角标题、地图名、轨迹文件和点数等文字信息。",
    )
    args = parser.parse_args()

    map_dir = Path(args.map_dir).expanduser().resolve()
    track_path = Path(args.track).expanduser().resolve() if args.track else None
    output_path = (
        Path(args.output).expanduser().resolve()
        if args.output
        else map_dir / "map_route_overlay.png"
    )

    output_path = render_overlay(map_dir, output_path, track_path, args.title, include_legend=not args.no_legend)
    print(output_path)


if __name__ == "__main__":
    main()
