from __future__ import annotations

from pathlib import Path

from PyQt5.QtCore import QProcess

from dog_remote_tool.core.shell import CommandSpec
from dog_remote_tool.modules import mapping


def _mapping_page_class():
    from dog_remote_tool.ui.pages.mapping.page import MappingPage

    return MappingPage


def _mapping_page_module():
    from dog_remote_tool.ui.pages.mapping import page as mapping_page

    return mapping_page


class MappingPreviewMixin:
    def fetch_selected_map_preview(self, force: bool = False) -> bool:
        if not self.preview_autoload_enabled:
            return False
        return self.fetch_map_preview(force=force)

    def mapping_probe_process_running(self) -> bool:
        return self.status_slot.is_running()

    def fetch_map_preview(self, force: bool = False) -> bool:
        page = _mapping_page_class()
        mapping_page = _mapping_page_module()
        if not self.mapping_supported():
            self.preview_status.setText("当前设备不支持地图预览")
            return False
        if not force and self.mapping_probe_process_running():
            self.preview_status.setText("等待设备状态刷新完成后加载地图预览")
            return False
        if self.map_fetch_slot.is_running():
            if not force:
                self.preview_status.setText("map.pgm 正在拉取中")
                return False
            self.map_fetch_slot.stop()
        remote_pgm = self.selected_remote_map_pgm()
        if not remote_pgm:
            mapping_page.QMessageBox.information(self, "未选择地图", "请等待地图列表自动加载后选择一个 map.pgm。")
            return False
        profile = self.profile()
        local_dir = self.local_preview_dir(remote_pgm, profile)
        self.fetching_preview_remote_pgm = remote_pgm
        self.preview_file = str(local_dir / "map.pgm")
        if not force and page._local_map_preview_cache_ready(self, local_dir):
            self.preview_status.setText("使用本地地图预览缓存")
            return page._load_map_preview_from_local(self, remote_pgm, cached=True)
        command = mapping.fetch_map_preview_files_command(profile, remote_pgm, str(local_dir))
        self.preview_status.setText("正在拉取远端 map.pgm / map.yaml")
        if hasattr(self, "edit_map_pgm_button"):
            self.edit_map_pgm_button.setEnabled(False)
        process, request_id = self.map_fetch_slot.start_spec(
            CommandSpec("拉取地图预览", command, concurrency="parallel", locks=("mapping-preview",))
        )
        if process is None:
            return False
        process.readyReadStandardOutput.connect(lambda: self.read_map_fetch_output(process, request_id))
        process.finished.connect(lambda exit_code, _status: self.map_fetch_finished(process, exit_code, request_id))
        process.start()
        return True

    def read_map_fetch_output(self, process: QProcess, request_id: int) -> bool:
        return self.map_fetch_slot.read_available_output(process, request_id)

    def map_fetch_finished(self, process: QProcess, exit_code: int, request_id: int) -> bool:
        page = _mapping_page_class()
        mapping_page = _mapping_page_module()
        output = self.map_fetch_slot.finish(process, request_id)
        if output is None:
            return False
        fetched_remote_pgm = self.fetching_preview_remote_pgm
        self.fetching_preview_remote_pgm = ""
        if fetched_remote_pgm != self.selected_remote_map_pgm():
            self.fetch_selected_map_preview(force=True)
            return True
        if exit_code != 0:
            detail = output.strip()
            self.preview_status.setText("map.pgm 拉取失败，请查看执行日志")
            if detail:
                self.preview_status.setToolTip(detail)
                self.runner.output.emit(f"[WARN] 地图预览拉取失败：\n{detail}\n")
            else:
                self.preview_status.setToolTip("远端可能还没有完成存图，或当前网络/权限无法读取 map.pgm/map.yaml")
                self.runner.output.emit("[WARN] 地图预览拉取失败：远端可能还没有完成存图，或当前网络/权限无法读取 map.pgm/map.yaml。\n")
            return True
        return page._load_map_preview_from_local(self, fetched_remote_pgm, cached=False)

    def _local_map_preview_cache_ready(self, local_dir: Path) -> bool:
        return (local_dir / "map.pgm").is_file() and (local_dir / "map.yaml").is_file()

    def _load_map_preview_from_local(self, remote_pgm: str, *, cached: bool) -> bool:
        page = _mapping_page_class()
        mapping_page = _mapping_page_module()
        pixmap = mapping_page.QPixmap(self.preview_file)
        if pixmap.isNull():
            self.preview_status.setText("地图预览已拉取，但本机无法读取")
            return True
        self.fetching_preview_remote_pgm = ""
        self.preview_remote_pgm = remote_pgm or self.selected_remote_map_pgm()
        self.preview_pixmap = pixmap
        if hasattr(self, "edit_map_pgm_button"):
            self.edit_map_pgm_button.setEnabled(True)
        page.update_map_card_thumbnail(self, self.preview_remote_pgm, Path(self.preview_file).parent)
        prefix = "已加载本地缓存" if cached else "已加载"
        self.preview_status.setText(f"{prefix}：{pixmap.width()}x{pixmap.height()}")
        return True
