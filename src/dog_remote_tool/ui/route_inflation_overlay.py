from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Any

from PyQt5.QtGui import QImage, QPixmap

from dog_remote_tool.modules.navigation.route_network import MapMetadata


DEFAULT_ROUTE_INFLATION_RADIUS_M = 0.55


@dataclass(frozen=True)
class SafetyMask:
    occupied: Any
    unknown: Any
    inflated: Any

    @property
    def height(self) -> int:
        return int(self.occupied.shape[0])

    @property
    def width(self) -> int:
        return int(self.occupied.shape[1])

    def status_at_pixel(self, px: float, py: float) -> str:
        ix = int(round(px))
        iy = int(round(py))
        if ix < 0 or iy < 0 or ix >= self.width or iy >= self.height:
            return "outside"
        if bool(self.occupied[iy, ix]):
            return "blocked"
        if bool(self.unknown[iy, ix]):
            return "unknown"
        if bool(self.inflated[iy, ix]):
            return "inflated"
        return "free"


@dataclass(frozen=True)
class InflationOverlay:
    pixmap: QPixmap
    safety_mask: SafetyMask
    radius_m: float
    radius_px: int
    obstacle_pixels: int
    inflated_pixels: int

    @property
    def label(self) -> str:
        return f"障碍/未知膨胀 {self.radius_m:.2f}m"


def create_inflation_overlay(metadata: MapMetadata, radius_m: float = DEFAULT_ROUTE_INFLATION_RADIUS_M) -> InflationOverlay | None:
    import numpy as np

    safety_mask = create_safety_mask(metadata, radius_m)
    if safety_mask is None:
        return None

    height, width = safety_mask.occupied.shape
    rgba = np.zeros((height, width, 4), dtype=np.uint8)
    rgba[safety_mask.inflated] = np.array([245, 158, 11, 22], dtype=np.uint8)
    boundary = safety_mask.inflated & ~_erode_mask(safety_mask.inflated)
    rgba[boundary] = np.array([220, 38, 38, 96], dtype=np.uint8)

    image = QImage(rgba.data, width, height, width * 4, QImage.Format_RGBA8888).copy()
    return InflationOverlay(
        pixmap=QPixmap.fromImage(image),
        safety_mask=safety_mask,
        radius_m=radius_m,
        radius_px=max(1, int(math.ceil(radius_m / metadata.resolution))),
        obstacle_pixels=int(np.count_nonzero(safety_mask.occupied | safety_mask.unknown)),
        inflated_pixels=int(np.count_nonzero(safety_mask.inflated)),
    )


def create_safety_mask(metadata: MapMetadata, radius_m: float = DEFAULT_ROUTE_INFLATION_RADIUS_M) -> SafetyMask | None:
    if metadata.resolution <= 0 or radius_m <= 0:
        return None
    try:
        import cv2
        import numpy as np
    except Exception:
        return None

    gray = cv2.imread(str(metadata.image_path), cv2.IMREAD_GRAYSCALE)
    if gray is None or gray.size == 0:
        return None

    if metadata.negate:
        occupancy = gray.astype(np.float32) / 255.0
    else:
        occupancy = (255.0 - gray.astype(np.float32)) / 255.0
    occupied = occupancy >= max(0.0, min(1.0, metadata.occupied_thresh))
    free = occupancy <= max(0.0, min(1.0, metadata.free_thresh))
    unknown = ~(occupied | free)
    blocked = occupied | unknown

    obstacle_pixels = int(np.count_nonzero(blocked))
    if obstacle_pixels <= 0:
        return None

    radius_px = max(1, int(math.ceil(radius_m / metadata.resolution)))
    kernel_size = radius_px * 2 + 1
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (kernel_size, kernel_size))
    inflated = cv2.dilate(blocked.astype(np.uint8), kernel, iterations=1).astype(bool) & free
    return SafetyMask(occupied=occupied, unknown=unknown, inflated=inflated)


def _erode_mask(mask: Any) -> Any:
    try:
        import cv2
        import numpy as np
    except Exception:
        return mask
    return cv2.erode(mask.astype(np.uint8), np.ones((3, 3), dtype=np.uint8), iterations=1).astype(bool)
