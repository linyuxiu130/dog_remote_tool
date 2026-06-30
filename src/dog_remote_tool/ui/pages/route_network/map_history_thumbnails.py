from __future__ import annotations

from pathlib import Path

from PyQt5.QtCore import QProcess

from dog_remote_tool.core.shell import CommandSpec
from dog_remote_tool.modules import mapping


class RouteNetworkMapHistoryThumbnailsMixin:
    def preload_history_map_card_thumbnails(self, entries: list[tuple[str, str, str]]) -> None:
        if self.history_map_thumbnail_slot.is_running():
            return
        queue = []
        for _label, remote_pgm, _detail in entries[:5]:
            local_pgm, local_yaml, _local_geojson = self.local_paths_for_history(remote_pgm)
            if local_pgm.exists() and local_yaml.exists():
                self.update_history_map_card_thumbnail(remote_pgm, local_pgm.parent)
            else:
                queue.append(remote_pgm)
        self.history_map_thumbnail_queue = queue
        self.fetch_next_history_map_card_thumbnail()

    def fetch_next_history_map_card_thumbnail(self) -> bool:
        if self.history_map_thumbnail_slot.is_running():
            return False
        while self.history_map_thumbnail_queue:
            remote_pgm = self.history_map_thumbnail_queue.pop(0)
            if remote_pgm not in self.history_map_cards:
                continue
            local_pgm, local_yaml, _local_geojson = self.local_paths_for_history(remote_pgm)
            if local_pgm.exists() and local_yaml.exists():
                self.update_history_map_card_thumbnail(remote_pgm, local_pgm.parent)
                continue
            process, request_id = self.history_map_thumbnail_slot.start_spec(
                CommandSpec(
                    "拉取路网地图缩略图",
                    mapping.fetch_map_preview_files_command(self.profile(), remote_pgm, str(local_pgm.parent)),
                    concurrency="parallel",
                    locks=("route-map-fetch",),
                )
            )
            if process is None:
                return False
            process.readyReadStandardOutput.connect(lambda: self.read_history_map_thumbnail_output(process, request_id))
            process.finished.connect(
                lambda exit_code, _status, remote=remote_pgm, path=local_pgm.parent: self.history_map_thumbnail_finished(
                    process, exit_code, remote, path, request_id
                )
            )
            process.start()
            return True
        return False

    def read_history_map_thumbnail_output(self, process: QProcess, request_id: int) -> bool:
        return self.history_map_thumbnail_slot.read_available_output(process, request_id)

    def history_map_thumbnail_finished(self, process: QProcess, exit_code: int, remote_pgm: str, local_dir: Path, request_id: int) -> bool:
        output = self.history_map_thumbnail_slot.finish(process, request_id)
        if output is None:
            return False
        if exit_code == 0:
            self.update_history_map_card_thumbnail(remote_pgm, local_dir)
        self.fetch_next_history_map_card_thumbnail()
        return True
