from __future__ import annotations

from dog_remote_tool.modules import bag
from dog_remote_tool.ui.pages.bag.recording_refs import bag_page_module


class BagRecordingSizeMixin:
    def refresh_current_bag_size(self, force: bool = False) -> bool:
        if not self.page_active:
            return False
        if (not force and not self.is_recording) or not self.current_bag_paths or self.is_reading_bag_size:
            return False
        self.is_reading_bag_size = True
        self.bag_size_request_id += 1
        request_id = self.bag_size_request_id
        paths = self.current_bag_paths[:]
        bag_page_module().threading.Thread(
            target=self._current_bag_size_worker,
            args=(self.current_record_backend(), paths, request_id),
            daemon=True,
        ).start()
        return True

    def _current_bag_size_worker(self, backend: bag.BagBackend, paths: list[str], request_id: int) -> None:
        try:
            size = backend.remote_bags_size(paths)
            text = bag.format_size(size)
        except Exception:
            text = "读取失败"
        self.bag_size_done.emit(text, request_id)

    def _current_bag_size_finished(self, text: str, request_id: int) -> bool:
        if request_id != self.bag_size_request_id:
            return False
        self.is_reading_bag_size = False
        if self.current_bag_paths:
            self.current_bag_size_label.setText(text)
        return True
