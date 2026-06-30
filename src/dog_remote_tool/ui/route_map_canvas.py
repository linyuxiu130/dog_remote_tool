from __future__ import annotations

from typing import Any

from PyQt5.QtCore import QPointF, Qt, pyqtSignal
from PyQt5.QtGui import QPixmap
from PyQt5.QtWidgets import QWidget

from ..modules.navigation import route_network
from ..modules.navigation.route_network import MapMetadata, RouteGraph
from .route_map_canvas_drawing import RouteMapCanvasDrawingMixin
from .route_map_canvas_editing import RouteMapCanvasEditingMixin
from .route_map_canvas_events import RouteMapCanvasEventMixin
from .route_map_canvas_history import RouteMapCanvasHistoryMixin
from .route_map_canvas_painting import RouteMapCanvasPaintingMixin
from .route_map_canvas_state import RouteMapCanvasStateMixin
from .route_map_canvas_view import RouteMapCanvasViewMixin
from . import route_map_canvas_geometry as _canvas_geometry

_offset_polyline = _canvas_geometry.offset_polyline
_point_to_polyline_distance = _canvas_geometry.point_to_polyline_distance
_point_to_segment_distance = _canvas_geometry.point_to_segment_distance


class RouteMapCanvas(
    RouteMapCanvasEventMixin,
    RouteMapCanvasEditingMixin,
    RouteMapCanvasHistoryMixin,
    RouteMapCanvasStateMixin,
    RouteMapCanvasViewMixin,
    RouteMapCanvasPaintingMixin,
    RouteMapCanvasDrawingMixin,
    QWidget,
):
    selection_changed = pyqtSignal(str, int)
    graph_changed = pyqtSignal()
    history_changed = pyqtSignal()
    point_picked = pyqtSignal(float, float)
    cursor_moved = pyqtSignal(float, float)

    def __init__(self) -> None:
        super().__init__()
        self.setMinimumSize(420, 360)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setObjectName("RouteCanvas")
        self.pixmap: QPixmap | None = None
        self.map_metadata: MapMetadata | None = None
        self.graph = RouteGraph()
        self.mode = "select"
        self.selected_type = ""
        self.selected_id: int | None = None
        self.pending_node_id: int | None = None
        self.dragging_node_id: int | None = None
        self.drag_history_recorded = False
        self.snap_distance = 0.25
        self.node_hit_pixels = 14
        self.edge_hit_pixels = 12
        self.editing_enabled = True
        self.new_edge_passable_width = route_network.DEFAULT_ROUTE_PASSABLE_WIDTH
        self.show_nodes = True
        self.show_node_labels = False
        self.show_direction_arrows = True
        self.view_zoom = 1.0
        self.view_center_px: QPointF | None = None
        self.min_zoom = 1.0
        self.max_zoom = 12.0
        self.panning = False
        self.pan_last_pos: QPointF | None = None
        self.pan_button = None
        self.space_pressed = False
        self.history_enabled = True
        self.history_limit = 80
        self.history_records: list[dict[str, Any]] = []
        self._history_suspended = False
        self.path_edge_ids: set[int] = set()
        self.issue_targets: set[tuple[str, int]] = set()
        self.issue_target_levels: dict[tuple[str, int], str] = {}
        self.inflation_overlay: QPixmap | None = None
        self.inflation_overlay_label = ""
        self.show_inflation_overlay = True
        self.robot_pose: tuple[float, float, float] | None = None
        self.hover_text = "打开 map.yaml 与 map.geojson 后开始编辑"
