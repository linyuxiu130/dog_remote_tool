from __future__ import annotations

from PyQt5.QtWidgets import QMessageBox

from dog_remote_tool.modules import bag


def _bag_page_module():
    from dog_remote_tool.ui.pages.bag import page as bag_page

    return bag_page


class BagRemoteTopicActionsMixin:
    def show_remote_topic_dialog(self) -> bool:
        if self.remote_topic_dialog is None:
            self._build_remote_topic_dialog()
        if self.remote_topic_dialog is None:
            return False
        self.remote_topic_dialog.show()
        self.remote_topic_dialog.raise_()
        self.remote_topic_dialog.activateWindow()
        if self.remote_topic_rows:
            self._populate_remote_topic_table(self.remote_topic_rows)
        elif not self.is_scanning_remote_topics:
            self._start_remote_topic_scan()
        return True

    def _build_remote_topic_dialog(self) -> bool:
        dialog = _bag_page_module().RemoteTopicDialog(
            self.profile(),
            self,
            self._start_remote_topic_scan,
            self._remote_topic_view_changed,
        )
        dialog.finished.connect(self._remote_topic_dialog_closed)
        self.remote_topic_dialog = dialog
        self._refresh_remote_topic_theme_combo()
        return True

    def _remote_topic_dialog_closed(self) -> bool:
        if self.remote_topic_dialog is None:
            return False
        self.remote_topic_dialog = None
        return True

    def _start_remote_topic_scan(self) -> bool:
        if self.is_scanning_remote_topics:
            return False
        self.is_scanning_remote_topics = True
        self.remote_topic_btn.setEnabled(False)
        if self.remote_topic_dialog is not None:
            self.remote_topic_dialog.set_busy(True)
            self.remote_topic_dialog.set_status("读取列表...")
            self.remote_topic_dialog.clear_rows()
        self.remote_topic_rows = []
        self.remote_topic_request_id += 1
        request_id = self.remote_topic_request_id
        backend = self.backend()
        self._log("[远端Topic] 开始读取当前存在的Topic列表")
        _bag_page_module().threading.Thread(target=self._remote_topic_list_worker, args=(backend, request_id), daemon=True).start()
        return True

    def _remote_topic_list_worker(self, backend: bag.BagBackend, request_id: int) -> None:
        try:
            rows = backend.list_remote_topics()
            self.remote_topic_list_done.emit(rows, "", request_id, backend)
        except Exception as exc:
            self.remote_topic_list_done.emit([], str(exc), request_id, backend)

    def _remote_topic_list_finished(self, rows: list, error: str, request_id: int, backend: bag.BagBackend) -> bool:
        if request_id != self.remote_topic_request_id:
            return False
        if error:
            self.is_scanning_remote_topics = False
            self.remote_topic_btn.setEnabled(True)
            if self.remote_topic_dialog is not None:
                self.remote_topic_dialog.set_busy(False)
                self.remote_topic_dialog.set_status("读取失败")
            self._log(f"[远端Topic] 列表读取失败: {error[:240]}")
            if self.remote_topic_dialog is not None:
                QMessageBox.warning(self.remote_topic_dialog, "远端Topic", f"读取失败：\n{error[:500]}")
            return True
        self.remote_topic_rows = rows
        self._populate_remote_topic_table(rows)
        if self.remote_topic_dialog is not None:
            self.remote_topic_dialog.set_status(f"已列出 {len(rows)} 个，正在采样 Hz...")
        self._log(f"[远端Topic] 已列出 {len(rows)} 个Topic，开始批量采样Hz")
        _bag_page_module().threading.Thread(target=self._remote_topic_scan_worker, args=(backend, request_id), daemon=True).start()
        return True

    def _remote_topic_scan_worker(self, backend: bag.BagBackend, request_id: int) -> None:
        try:
            rows = backend.inspect_remote_topics()
            self.remote_topics_done.emit(rows, "", request_id)
        except Exception as exc:
            self.remote_topics_done.emit([], str(exc), request_id)

    def _remote_topic_scan_finished(self, rows: list, error: str, request_id: int) -> bool:
        if request_id != self.remote_topic_request_id:
            return False
        self.is_scanning_remote_topics = False
        self.remote_topic_btn.setEnabled(True)
        if self.remote_topic_dialog is not None:
            self.remote_topic_dialog.set_busy(False)
        if error:
            if self.remote_topic_dialog is not None:
                self.remote_topic_dialog.set_status("读取失败")
            self._log(f"[远端Topic] 读取失败: {error[:240]}")
            if self.remote_topic_dialog is not None:
                QMessageBox.warning(self.remote_topic_dialog, "远端Topic", f"读取失败：\n{error[:500]}")
            return True
        self.remote_topic_rows = rows
        self._populate_remote_topic_table(rows)
        ok_count = sum(1 for item in rows if item.get("hz") is not None)
        self._log(f"[远端Topic] 完成: 共 {len(rows)} 个Topic，取到Hz {ok_count} 个")
        return True

    def _refresh_remote_topic_theme_combo(self) -> bool:
        if self.remote_topic_dialog is None:
            return False
        self.remote_topic_dialog.refresh_theme_combo(self.record_topics, self._topic_display_name)
        return True

    def _remote_topic_view_changed(self) -> bool:
        return self._populate_remote_topic_table(self.remote_topic_rows)

    def _populate_remote_topic_table(self, rows: list[dict]) -> bool:
        if self.remote_topic_dialog is None:
            return False
        self.remote_topic_dialog.populate_rows(rows, self.record_topics, self._topic_display_name, set(self.selected_keys()))
        return True

    def check_selected_topics(self) -> bool:
        plan = self.topic_plan()
        if not plan.all_topics or self.is_checking_topics:
            return False
        self.is_checking_topics = True
        self.topic_check_request_id += 1
        request_id = self.topic_check_request_id
        self.topic_check_btn.setEnabled(False)
        self.topic_check_label.setText("检查中...")
        self._set_label_status(self.topic_check_label, "warn")
        backend = self.backend()
        self._log(f"[话题检查] 开始检查，共 {len(plan.all_topics)} 个Topic")
        _bag_page_module().threading.Thread(target=self._topic_check_worker, args=(backend, plan.all_topics, request_id), daemon=True).start()
        return True

    def _topic_check_worker(self, backend: bag.BagBackend, topics: list[str], request_id: int) -> None:
        try:
            passed, failed = backend.check_topics(topics, lambda done, total, topic: self.topic_progress.emit(done, total, topic, request_id))
            if failed:
                try:
                    remote_rows = backend.list_remote_topics()
                    failed = bag.add_topic_suggestions(failed, remote_rows)
                except Exception as exc:
                    self._log(f"[话题检查] 候选Topic读取失败: {str(exc)[:200]}")
            self.topic_done.emit(passed, failed, request_id)
        except Exception as exc:
            self.topic_done.emit([], [f"检查异常: {exc}"], request_id)

    def _topic_check_progress(self, done: int, total: int, topic: str, request_id: int) -> bool:
        if request_id != self.topic_check_request_id:
            return False
        self.topic_check_label.setText(f"检查中 {done}/{total} {topic}")
        return True

    def _topic_check_finished(self, passed: list, failed: list, request_id: int) -> bool:
        if request_id != self.topic_check_request_id:
            return False
        self.is_checking_topics = False
        self._topic_selection_changed()
        total = len(passed) + len(failed)
        if failed and passed:
            self.topic_check_label.setText(f"部分异常 {len(failed)}/{total}")
            self._set_label_status(self.topic_check_label, "warn")
            QMessageBox.warning(self, "话题检查", "部分Topic数据异常：\n" + "\n".join(failed[:8]))
        elif failed:
            self.topic_check_label.setText(f"异常 {len(failed)} 个")
            self._set_label_status(self.topic_check_label, "bad")
            QMessageBox.critical(self, "话题检查", "所选Topic检查异常：\n" + "\n".join(failed[:8]))
        else:
            self.topic_check_label.setText(f"正常 {len(passed)} 个")
            self._set_label_status(self.topic_check_label, "ok")
            QMessageBox.information(self, "话题检查", f"所选Topic数据正常，共 {len(passed)} 个")
        self._log(f"[话题检查] 完成: 正常 {len(passed)} 个, 异常 {len(failed)} 个")
        return True
