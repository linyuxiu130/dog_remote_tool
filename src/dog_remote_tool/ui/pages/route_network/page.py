from __future__ import annotations

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QSplitter

from dog_remote_tool.core.runner import ProcessRunner
from dog_remote_tool.modules.navigation.route_network import MapMetadata, RouteGraph, ValidationIssue
from dog_remote_tool.ui.components import CommandPage, DeviceBar
from dog_remote_tool.ui.process_utils import ProcessSlot
from dog_remote_tool.ui.route_inflation_overlay import create_inflation_overlay
from dog_remote_tool.ui.route_map_canvas import RouteMapCanvas
from .actions import RouteNetworkActionsMixin
from .inflation import RouteNetworkInflationMixin
from .layout import RouteNetworkLayoutMixin
from .map_history import RouteMapHistoryCard, RouteNetworkMapHistoryMixin
from .state import RouteNetworkStateMixin


# Tests patch this symbol through dog_remote_tool.ui.pages.route_network.page.
_ROUTE_NETWORK_PAGE_MONKEYPATCH_EXPORTS = (create_inflation_overlay,)


class RouteNetworkPage(
    RouteNetworkLayoutMixin,
    RouteNetworkMapHistoryMixin,
    RouteNetworkStateMixin,
    RouteNetworkActionsMixin,
    RouteNetworkInflationMixin,
    CommandPage,
):
    def __init__(self, runner: ProcessRunner, device_bar: DeviceBar) -> None:
        super().__init__("路网编辑与下发", runner, device_bar)
        self.controls_panel.hide()
        self.graph = RouteGraph()
        self.map_metadata: MapMetadata | None = None
        self.last_issues: list[ValidationIssue] = []
        self.current_tool = "select"
        self._opening_editor = False
        self._updating_properties = False
        self.current_pose_slot = ProcessSlot(self, reserve_runner=False)
        self.pose_stream_slot = ProcessSlot(self, stop_timeout_ms=300, reserve_runner=False)
        self.pose_stream_buffer = ""
        self.robot_pose: tuple[float, float, float] | None = None
        self.history_map_slot = ProcessSlot(self, reserve_runner=False)
        self.history_map_fetch_slot = ProcessSlot(self, reserve_runner=False)
        self.history_route_fetch_slot = ProcessSlot(self, reserve_runner=False)
        self.history_map_thumbnail_slot = ProcessSlot(self, reserve_runner=False)
        self.history_map_details: dict[str, str] = {}
        self.history_map_entries_signature: tuple[tuple[str, str, str], ...] = ()
        self.page_active = False
        self.history_map_list_loaded_once = False
        self.history_map_cards: dict[str, RouteMapHistoryCard] = {}
        self.history_map_thumbnail_queue: list[str] = []
        self.pending_history_action = ""
        self.pending_history_route_action = ""
        self.require_remote_route_pull_before_edit = False
        self.route_saved_callback = None
        self.inflation_radius_m: float | None = None
        self.active_editor_dialog = None
        self.pending_route_upload_task_id: int | None = None

        self.body.addWidget(self._make_top_panel())
        self.body.addWidget(self._make_info_strip())

        splitter = QSplitter(Qt.Horizontal)
        splitter.setChildrenCollapsible(False)
        self.toolbar = self._make_toolbar()
        self.toolbar.hide()
        self.canvas = RouteMapCanvas()
        self.canvas.editing_enabled = False
        self.canvas.set_display_options(show_nodes=False, show_node_labels=False, show_direction_arrows=False)
        self.canvas.hover_text = "点击地图打开全屏编辑器"
        self.canvas.setStyleSheet("background:#f8fbff;border:1px solid #d7e2ef;border-radius:8px;")
        self.canvas.selection_changed.connect(self.update_properties)
        self.canvas.graph_changed.connect(self.on_graph_changed)
        self.canvas.point_picked.connect(self.on_point_picked)
        self.canvas.cursor_moved.connect(self.on_cursor_moved)
        self.right_panel = self._make_right_panel()
        self.right_panel.hide()
        splitter.addWidget(self.canvas)
        splitter.setSizes([1])
        self.body.addWidget(splitter, 1)
        self.set_tool("select")
        self.update_scale_info()
        self.runner.task_finished_detail.connect(self.handle_route_runner_finished)

    def shutdown_processes(self) -> None:
        self.page_active = False
        self.pose_stream_buffer = ""
        for slot_name in (
            "current_pose_slot",
            "pose_stream_slot",
            "history_map_slot",
            "history_map_fetch_slot",
            "history_route_fetch_slot",
            "history_map_thumbnail_slot",
        ):
            slot = getattr(self, slot_name, None)
            if slot is not None:
                slot.stop()

    def activate_page(self) -> None:
        if self.page_active:
            return
        self.page_active = True
        if not self.history_map_list_loaded_once:
            self.refresh_history_map_list()

    def deactivate_page(self) -> None:
        self.page_active = False
        self.history_map_slot.stop()
        self.history_map_thumbnail_slot.stop()
