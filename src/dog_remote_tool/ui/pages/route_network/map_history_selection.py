from __future__ import annotations

from pathlib import Path

from dog_remote_tool.modules import mapping
from dog_remote_tool.ui import map_helpers


class RouteNetworkMapHistorySelectionMixin:
    def selected_history_map_pgm(self) -> str:
        data = self.history_map_selector.currentData()
        return str(data) if data else ""

    def select_history_map(self, remote_pgm: str) -> bool:
        index = self.history_map_selector.findData(remote_pgm)
        if index < 0:
            return False
        if self.history_map_selector.currentIndex() == index:
            self.on_history_map_changed()
            return True
        self.history_map_selector.setCurrentIndex(index)
        return True

    def local_paths_for_history(self, remote_pgm: str) -> tuple[Path, Path, Path]:
        profile = self.profile()
        local_dir = map_helpers.local_map_preview_dir(
            profile.key,
            profile.host,
            remote_pgm,
            mapping.DEFAULT_LOCAL_MAP_DIR,
        )
        return local_dir / "map.pgm", local_dir / "map.yaml", local_dir / "map.geojson"
