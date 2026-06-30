from __future__ import annotations

from dog_remote_tool.ui.pages.bag.recording_refs import bag_page_module


class BagRecordingLifecycleMixin:
    def _profile_changed(self, _profile) -> bool:
        self.remote_topic_request_id += 1
        self.topic_check_request_id += 1
        self.remote_bags_request_id += 1
        self.bag_size_request_id += 1
        self.pull_request_id += 1
        self.delete_request_id += 1
        self.is_checking_topics = False
        self.is_scanning_remote_topics = False
        self.is_refreshing_remote = False
        self.is_reading_bag_size = False
        self.reload_topic_config()
        self.remote_topic_rows = []
        if self.remote_topic_dialog is not None:
            self.remote_topic_dialog.set_busy(False)
            self.remote_topic_dialog.clear_rows()
            self.remote_topic_dialog.set_status("设备已切换，请刷新")
        self.remote_topic_btn.setEnabled(True)
        self.topic_check_label.setText("设备已切换")
        self._set_label_status(self.topic_check_label, "warn")
        self._refresh_remote_topic_theme_combo()
        if self.page_active:
            self.refresh_remote_bags(auto=True)
        return True

    def activate_page(self) -> bool:
        if self.page_active:
            return False
        self.page_active = True
        if self.is_recording:
            self.duration_timer.start()
            self.bag_size_timer.start()
        bag_page_module().QTimer.singleShot(150, lambda: self.refresh_remote_bags(auto=True))
        return True

    def deactivate_page(self) -> bool:
        changed = self.page_active
        self.page_active = False
        self.duration_timer.stop()
        self.bag_size_timer.stop()
        return changed

    def choose_local_dir(self) -> bool:
        bag_page = bag_page_module()
        path = bag_page.QFileDialog.getExistingDirectory(
            self,
            "选择本地回传目录",
            self.local_dir.text().strip() or bag_page.os.path.expanduser("~"),
        )
        if path:
            self.local_dir.setText(path)
            return True
        return False

    def shutdown_processes(self) -> bool:
        self.page_active = False
        self.remote_topic_request_id += 1
        self.topic_check_request_id += 1
        self.remote_bags_request_id += 1
        self.bag_size_request_id += 1
        self.pull_request_id += 1
        self.delete_request_id += 1
        self.record_start_request_id += 1
        self.record_stop_request_id += 1
        self.duration_timer.stop()
        self.bag_size_timer.stop()
        self._cleanup_local_recording_process()
        return True
