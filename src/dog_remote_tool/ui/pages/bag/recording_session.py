from __future__ import annotations

from datetime import datetime

from dog_remote_tool.core.durations import format_seconds
from dog_remote_tool.modules import bag
from dog_remote_tool.ui.pages.bag.record_metadata import empty_record_context, record_context
from dog_remote_tool.ui.pages.bag.recording_refs import bag_page_class, bag_page_module
from dog_remote_tool.ui.widget_roles import widget_text


class BagRecordingSessionMixin:
    def start_recording(self) -> bool:
        bag_page = bag_page_module()
        if self.is_recording or self.is_starting_recording:
            bag_page.QMessageBox.warning(self, "警告", "正在录制中，请先停止当前录制")
            return False
        try:
            profile = self.profile()
            product = self.product
            backend = bag.BagBackend(profile, product, self._log)
            plan = backend.build_record_plan(
                self.remote_path.text().strip(),
                self.storage_combo.currentText(),
                self.cache_spin.value(),
                self.topic_plan(),
            )
        except Exception as exc:
            bag_page.QMessageBox.critical(self, "错误", str(exc))
            return False
        self._apply_record_context(
            record_context(
                plan.remote_paths,
                product,
                plan.storage,
                self.cache_spin.value(),
                profile=profile,
                topics=plan.topics,
                themes=[self._topic_display_name(key) for key in self.selected_keys()],
                started_at=datetime.now(),
            )
        )
        self.is_starting_recording = True
        self.is_recording = False
        self.stop_requested = False
        self.record_start_request_id += 1
        request_id = self.record_start_request_id
        self.start_time = None
        self.start_btn.setEnabled(False)
        self.resume_btn.setEnabled(False)
        self.stop_btn.setEnabled(False)
        self.record_status_label.setText("启动录制...")
        self._set_pull_progress_visible(False)
        self._set_record_detail_visible(True)
        self._set_current_bag_paths(plan.remote_paths)
        self.current_bag_size_label.setText("查询中...")
        self._set_pull_progress_value(0, animated=False)
        self._log(f"开始录制到 {product}...")
        for path in plan.remote_paths:
            self._log(f"Bag保存路径: {path}")
        self._log(f"录制Topic数量: {len(plan.topics)} 个")
        bag_page.threading.Thread(
            target=self._recording_worker,
            args=(backend, plan.command, plan.remote_paths, request_id),
            daemon=True,
        ).start()
        return True

    def _recording_worker(self, backend: bag.BagBackend, command: str, remote_paths: list[str], request_id: int) -> None:
        try:
            self._log("启动远端后台录制进程...")
            ok, error = backend.start_remote_recording(command, remote_paths)
            self.record_start_done.emit(ok, error, request_id)
        except Exception as exc:
            self.record_start_done.emit(False, f"异常: {exc}", request_id)

    def _record_start_finished(self, success: bool, error: str, request_id: int) -> bool:
        if request_id != self.record_start_request_id:
            return False
        self.is_starting_recording = False
        if not success:
            self.is_recording = False
            self._apply_record_context(empty_record_context())
            self.start_btn.setEnabled(True)
            self.stop_btn.setEnabled(False)
            self._update_resume_button()
            self.duration_label.setText("00:00:00")
            self.record_status_label.setText("启动失败")
            self._set_current_bag_paths([])
            self._log(f"✗ 远端录制启动失败: {error or '未知错误'}")
            bag_page_module().QMessageBox.warning(self, "录制启动失败", error or "远端录制启动失败")
            return True
        self.is_recording = True
        self.start_time = bag_page_module().time.time()
        self.stop_requested = False
        self.start_btn.setEnabled(False)
        self.resume_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self.record_status_label.setText("正在录制...")
        self.duration_timer.start()
        self.bag_size_timer.start()
        self.refresh_current_bag_size()
        self.refresh_remote_bags(auto=False)
        self._log("[录制] 本地工具可关闭，远端录制会继续运行；重新打开后可刷新并接管。")
        return True

    def stop_recording(self) -> bool:
        if not self.is_recording:
            return False
        self._log("正在停止录制...")
        self.record_status_label.setText("正在停止...")
        self.stop_btn.setEnabled(False)
        self.stop_requested = True
        self.record_stop_request_id += 1
        request_id = self.record_stop_request_id
        backend = self.current_record_backend()
        paths = self.current_bag_paths[:]
        topics = self.current_record_topics[:]
        bag_page_module().threading.Thread(
            target=self._stop_recording_worker,
            args=(backend, paths, topics, request_id),
            daemon=True,
        ).start()
        return True

    def _stop_recording_worker(self, backend: bag.BagBackend, paths: list[str], topics: list[str], request_id: int) -> None:
        try:
            if not backend.stop_remote_recording(paths):
                self._cleanup_local_recording_process()
                self.record_done.emit(False, "远端停止录制失败", request_id)
                return
            self._cleanup_local_recording_process()
            if not backend.wait_remote_bags_finalized(paths, timeout=180):
                self.record_done.emit(False, "远端Bag未完成收尾", request_id)
                return
            quick_check_summary = self._quick_check_remote_recording(backend, paths, topics)
            self.record_done.emit(True, quick_check_summary, request_id)
        except Exception as exc:
            self.record_done.emit(False, f"停止录制异常: {exc}", request_id)

    def _quick_check_remote_recording(self, backend: bag.BagBackend, paths: list[str], topics: list[str]) -> str:
        try:
            validation = backend.validate_remote_recorded_topics(paths, topics)
        except Exception as exc:
            summary = f"话题快速检查失败: {exc}"
            self._log(f"[录后检查] {summary}")
            return summary
        summary = str(validation.get("summary") or "")
        state = "正常" if validation.get("ok") else "异常"
        self._log(f"[录后检查] {state}: {summary}")
        details = list(validation.get("details") or [])
        for detail in details[:8]:
            self._log(f"[录后检查] {detail}")
        if len(details) > 8:
            self._log(f"[录后检查] 其余 {len(details) - 8} 条详情已省略")
        return summary

    def _cleanup_local_recording_process(self) -> bool:
        process = self.recording_process
        if not process:
            return False
        if process.poll() is not None:
            self.recording_process = None
            return True
        try:
            process.terminate()
            process.wait(timeout=5)
            self._log("[录制] 本地录制连接已退出")
            self.recording_process = None
            return True
        except bag_page_module().subprocess.TimeoutExpired:
            self._log("[录制] 本地录制连接未正常退出，已结束该连接")
        try:
            if process.poll() is None:
                process.kill()
                process.wait(timeout=5)
            self.recording_process = None
        except Exception:
            pass
        return True

    def _recording_finished(self, success: bool, error: str, request_id: int) -> bool:
        if request_id != self.record_stop_request_id:
            return False
        self.stop_requested = False
        self.is_starting_recording = False
        self.is_recording = False
        if success:
            self.current_record_finished_at = datetime.now()
            if self.start_time:
                self.current_record_duration_seconds = max(0, int(bag_page_module().time.time() - self.start_time))
        self.duration_timer.stop()
        self.bag_size_timer.stop()
        self.start_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self._update_resume_button()
        self.duration_label.setText("00:00:00")
        if success:
            self.record_status_label.setText("录制完成")
            self._log("✓ 录制完成")
            self.refresh_remote_bags(auto=False)
            if bag_page_class().auto_pull_after_record_enabled(self):
                self.record_status_label.setText("录制完成，自动回传中")
                self.pull_current_recording(delete_remote_on_success=False)
            else:
                self.record_status_label.setText("录制完成，待手动回传")
        else:
            self.record_status_label.setText("录制异常")
            self._log(f"⚠ 录制任务异常: {error or '未知错误'}")
            bag_page_module().QMessageBox.warning(
                self,
                "录制异常",
                f"录制任务异常: {error or '未知错误'}\n\nBag 文件可能已生成，请在远端 Bag 列表中确认后手动回传。",
            )
        return True

    def _update_duration(self) -> bool:
        if not self.is_recording or not self.start_time:
            return False
        elapsed = int(bag_page_module().time.time() - self.start_time)
        text = format_seconds(elapsed)
        current = widget_text(self.duration_label)
        self.duration_label.setText(text)
        return current != text
