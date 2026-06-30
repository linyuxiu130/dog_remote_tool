from __future__ import annotations

from datetime import datetime
import json
from typing import Any

from dog_remote_tool.modules.navigation import route_network


class RouteMapCanvasHistoryMixin:
    history_records: list[dict[str, Any]]
    history_enabled: bool
    history_limit: int
    _history_suspended: bool

    def push_history(self, action: str) -> None:
        if not self.history_enabled or self._history_suspended:
            return
        snapshot = json.loads(json.dumps(route_network.graph_to_geojson(self.graph), ensure_ascii=False))
        self.history_records.append(
            {
                "time": datetime.now().strftime("%H:%M:%S"),
                "action": action,
                "nodes": len(self.graph.nodes),
                "edges": len(self.graph.edges),
                "snapshot": snapshot,
            }
        )
        if len(self.history_records) > self.history_limit:
            self.history_records = self.history_records[-self.history_limit :]
        self.history_changed.emit()

    def undo_last_history(self) -> bool:
        if not self.history_records:
            return False
        record = self.history_records.pop()
        self._restore_history_snapshot(record["snapshot"])
        self.history_changed.emit()
        return True

    def revert_to_history(self, row: int) -> bool:
        if row < 0 or row >= len(self.history_records):
            return False
        record = self.history_records[row]
        self._restore_history_snapshot(record["snapshot"])
        self.history_records = self.history_records[:row]
        self.history_changed.emit()
        return True

    def _restore_history_snapshot(self, snapshot: dict[str, Any]) -> None:
        self._history_suspended = True
        try:
            source_path = self.graph.source_path
            self.graph = route_network.route_graph_from_geojson(snapshot)
            self.graph.source_path = source_path
            self.graph.dirty = True
            self.selected_type = ""
            self.selected_id = None
            self.pending_node_id = None
            self.dragging_node_id = None
            self.drag_history_recorded = False
            self.path_edge_ids = set()
            self.graph_changed.emit()
            self.selection_changed.emit("", -1)
            self.update()
        finally:
            self._history_suspended = False
