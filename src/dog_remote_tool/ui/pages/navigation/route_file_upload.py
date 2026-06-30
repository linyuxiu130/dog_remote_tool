from __future__ import annotations

import shutil
from pathlib import Path

from PyQt5.QtCore import QTimer
from PyQt5.QtWidgets import QFileDialog, QMessageBox

from dog_remote_tool.modules.navigation import route_network
from dog_remote_tool.ui.pages.navigation.map_history import NavigationMapHistoryMixin
from dog_remote_tool.ui.pages.navigation.page_refs import navigation_page_class


class NavigationRouteFileUploadMixin:
    def confirm_replace_remote_route(self, remote_pgm: str, remote_route: str) -> bool:
        if getattr(self, "route_file_states", {}).get(remote_pgm) is not True:
            return True
        result = QMessageBox.question(
            self,
            "替换远端路网",
            f"机器人当前地图目录已存在 map.geojson：\n{remote_route}\n\n是否用本地路网替换？",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        return result == QMessageBox.Yes

    def upload_selected_route_geojson(self, source_path: str | Path | None = None) -> bool:
        if isinstance(source_path, bool):
            source_path = None
        remote_pgm = self.selected_map_pgm()
        if not remote_pgm:
            QMessageBox.information(self, "未选择历史图", "请先选择一个历史图。")
            return False
        local_route = NavigationMapHistoryMixin.local_route_geojson_path(self, remote_pgm)
        if local_route is None:
            QMessageBox.information(self, "未选择历史图", "请先选择一个历史图。")
            return False
        default_path = str(local_route if local_route.exists() else Path.home())
        if source_path is None:
            source_path, _selected_filter = QFileDialog.getOpenFileName(
                self,
                "选择要上传的路网 GeoJSON",
                default_path,
                "GeoJSON (*.geojson *.json);;所有文件 (*)",
            )
            if not source_path:
                return False
        source = Path(source_path)
        if not source.exists():
            QMessageBox.warning(self, "路网文件不存在", f"无法找到要上传的路网文件：{source}")
            return False
        try:
            local_route.parent.mkdir(parents=True, exist_ok=True)
            if source.resolve() != local_route.resolve():
                shutil.copyfile(source, local_route)
        except OSError as exc:
            QMessageBox.warning(self, "选择路网失败", f"无法复制本地路网文件：{exc}")
            return False
        page = navigation_page_class()
        remote_route = route_network.route_geojson_for_remote_map(remote_pgm)
        self.route_geojson_path.setText(remote_route)
        page._log_route_event(self, f"[路网] 已选择待上传路网：{source} -> {local_route}")
        page.handle_local_route_geojson_updated(self, remote_pgm, local_route)
        states = getattr(self, "route_file_states", None)
        if states is not None and states.get(remote_pgm) is None:
            refresh = getattr(self, "refresh_route_file_state", None)
            if callable(refresh):
                refresh(remote_pgm)
            self.nav_status_note.setText("已选择本地路网，正在检查远端是否已有 map.geojson，检查完成后再上传")
            self.refresh_workspace_from_page()
            return False
        if not page.confirm_replace_remote_route(self, remote_pgm, remote_route):
            self.nav_status_note.setText("已取消上传，远端路网未替换")
            self.refresh_workspace_from_page()
            return False
        local_dir = self.local_preview_dir(remote_pgm)
        local_pgm = local_dir / "map.pgm"
        local_yaml = local_dir / "map.yaml"
        if local_pgm.exists() and local_yaml.exists():
            spec = route_network.upload_map_route_files_command(
                self.profile(),
                str(local_pgm),
                str(local_yaml),
                str(local_route),
                remote_pgm,
            )
            upload_detail = "本地地图和路网"
        else:
            spec = route_network.upload_route_file_command(self.profile(), str(local_route), remote_route)
            upload_detail = "本地路网"
        started = self.run_route_file_spec(spec, "上传路网中")
        if not started:
            return False
        self.nav_status_note.setText("路网上传中，完成后会自动检查机器人历史图目录")
        page._log_route_event(self, f"[路网] 上传{upload_detail}到机器人：{remote_route}")
        QTimer.singleShot(1800, lambda remote=remote_pgm: page.refresh_route_file_state(self, remote))
        self.refresh_workspace_from_page()
        return True
