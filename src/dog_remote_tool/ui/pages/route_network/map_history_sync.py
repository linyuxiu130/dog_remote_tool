from __future__ import annotations

from pathlib import PurePosixPath

from PyQt5.QtGui import QPixmap

from dog_remote_tool.modules.navigation.route_network import RouteGraph, route_geojson_for_remote_map


class RouteNetworkMapHistorySyncMixin:
    def sync_selected_history_paths(self, load_existing: bool = False) -> bool:
        remote_pgm = self.selected_history_map_pgm()
        if not remote_pgm:
            self.selected_history_detail.setText("远端目录：--")
            return False
        detail = self.history_map_details.get(remote_pgm, f"远端目录：{PurePosixPath(remote_pgm).parent}")
        self.selected_history_detail.setText(detail)
        _local_pgm, local_yaml, local_geojson = self.local_paths_for_history(remote_pgm)
        self.remote_route_path.setText(route_geojson_for_remote_map(remote_pgm))
        self.map_path.setText(str(local_yaml))
        self.geojson_path.setText(str(local_geojson))
        if not load_existing:
            return True
        if local_yaml.exists():
            self.load_map(str(local_yaml))
        else:
            self.map_metadata = None
            self.canvas.set_map(QPixmap(), None)
        if local_geojson.exists():
            self.load_geojson(str(local_geojson))
        else:
            self.graph = RouteGraph()
            self.canvas.set_graph(self.graph)
            self.issue_list.clear()
            self.issue_summary.setText("未发现本地路网")
            self.canvas.set_issues([])
            self.update_scale_info()
        return True
