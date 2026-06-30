from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import threading
import time

from PyQt5.QtCore import QMutex, QMutexLocker, QObject, Qt, QThread, QTimer, pyqtSignal, pyqtSlot
from PyQt5.QtGui import QImage, QPainter, QPixmap
from PyQt5.QtWidgets import QComboBox, QFrame, QLabel, QPushButton, QSizePolicy, QVBoxLayout, QWidget

from dog_remote_tool.modules import control
from dog_remote_tool.ui.log_panel import LogPanel
from dog_remote_tool.ui.pages.control import helpers as control_helpers
from dog_remote_tool.ui.pages.control.stream_ui import set_button_role


RTSP_TRANSPORT = "tcp"
RTSP_BACKEND_GSTREAMER = "GStreamer low-latency"
RTSP_DISPLAY_INTERVAL_MS = 16
RTSP_OPEN_RETRY_SECONDS = 6.0
RTSP_OPEN_RETRY_INTERVAL_SECONDS = 0.15
RTSP_READ_RECONNECT_FAILURES = 180
RTSP_READ_RECONNECT_SECONDS = 4.0
RTSP_DISPLAY_WIDTH = 960
RTSP_DISPLAY_HEIGHT = 540
GSTREAMER_H264_DECODER = "avdec_h264"
GSTREAMER_OPEN_STDERR_LIMIT = 65536
_GSTREAMER_OPEN_STDERR_LOCK = threading.Lock()


def _gst_location(value: str) -> str:
    return value.replace(" ", "%20")


def _gstreamer_plugin_paths() -> tuple[str, ...]:
    paths: list[str] = []
    for key in ("GST_PLUGIN_PATH_1_0", "GST_PLUGIN_PATH", "GST_PLUGIN_SYSTEM_PATH_1_0"):
        value = os.environ.get(key, "")
        if value:
            paths.extend(item for item in value.split(os.pathsep) if item)
    paths.extend(
        (
            "/usr/lib/x86_64-linux-gnu/gstreamer-1.0",
            "/usr/lib/gstreamer-1.0",
        )
    )
    return tuple(dict.fromkeys(paths))


def _gstreamer_libav_plugin_available() -> bool:
    return any(os.path.exists(os.path.join(path, "libgstlibav.so")) for path in _gstreamer_plugin_paths())


def gstreamer_h264_decoder_name() -> str | None:
    if _gstreamer_libav_plugin_available():
        return GSTREAMER_H264_DECODER
    if not shutil.which("gst-inspect-1.0"):
        return None
    try:
        result = subprocess.run(
            ["gst-inspect-1.0", GSTREAMER_H264_DECODER],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=1.0,
        )
    except Exception:
        return None
    if result.returncode == 0:
        return GSTREAMER_H264_DECODER
    return None


def gstreamer_rtsp_pipeline(url: str) -> str:
    return (
        "rtspsrc "
        f"location={_gst_location(url)} "
        "protocols=tcp "
        "latency=0 "
        "drop-on-latency=true "
        "buffer-mode=none "
        "ntp-sync=false "
        "do-retransmission=false "
        "tcp-timeout=2000000 "
        "! rtph264depay request-keyframe=true wait-for-keyframe=true "
        f"! {GSTREAMER_H264_DECODER} output-corrupt=false "
        "! videoconvert n-threads=1 "
        "! videoscale n-threads=1 "
        f"! video/x-raw,format=BGR,width={RTSP_DISPLAY_WIDTH},height={RTSP_DISPLAY_HEIGHT} "
        "! appsink drop=true max-buffers=1 sync=false async=false enable-last-sample=false"
    )


def gstreamer_h264_decoder_available() -> bool:
    return gstreamer_h264_decoder_name() is not None


def _open_gstreamer_capture(cv2, pipeline: str):
    with _GSTREAMER_OPEN_STDERR_LOCK:
        saved_stderr_fd = os.dup(2)
        with tempfile.TemporaryFile() as stderr_file:
            try:
                os.dup2(stderr_file.fileno(), 2)
                capture = cv2.VideoCapture(pipeline, cv2.CAP_GSTREAMER)
            finally:
                os.dup2(saved_stderr_fd, 2)
                os.close(saved_stderr_fd)
            stderr_file.seek(0)
            stderr = stderr_file.read(GSTREAMER_OPEN_STDERR_LIMIT).decode(errors="replace")
    return capture, stderr.strip()


def rtsp_read_should_reconnect(failed_reads: int, last_frame_at: float, now: float) -> bool:
    return failed_reads >= RTSP_READ_RECONNECT_FAILURES or now - last_frame_at >= RTSP_READ_RECONNECT_SECONDS


class RtspVideoWorker(QObject):
    log_ready = pyqtSignal(str, str)
    error_ready = pyqtSignal(str, str)
    finished = pyqtSignal(str)

    def __init__(self, stream_kind: str, url: str, label: str) -> None:
        super().__init__()
        self.stream_kind = stream_kind
        self.url = url
        self.label = label
        self._running = True
        self._capture_lock = threading.Lock()
        self._capture = None
        self._frame_mutex = QMutex()
        self._latest_frame: QImage | None = None
        self._latest_sequence = 0

    @pyqtSlot()
    def run(self) -> None:
        try:
            import cv2
        except Exception as exc:
            self.error_ready.emit(self.label, f"无法导入 OpenCV: {exc}")
            self.finished.emit(self.stream_kind)
            return

        capture, backend, open_diagnostics = self._open_capture_with_retry(cv2)
        if not self._running:
            if capture is not None:
                self._release_capture(capture)
            self.finished.emit(self.stream_kind)
            return
        self._set_capture(capture)
        if not capture.isOpened():
            self.error_ready.emit(self.label, f"RTSP 打开失败: {self.url}")
            if not gstreamer_h264_decoder_available():
                self.error_ready.emit(self.label, "缺少 GStreamer H264 解码插件 avdec_h264")
            if open_diagnostics:
                self.error_ready.emit(self.label, f"GStreamer 打开诊断: {open_diagnostics}")
            self._release_capture(capture)
            self.finished.emit(self.stream_kind)
            return

        self.log_ready.emit(self.label, f"RTSP 已连接({backend}): {self.url}")
        failed_reads = 0
        last_frame_at = time.monotonic()
        try:
            while self._running:
                ok, frame = self._read_latest_frame(capture, backend)
                if not ok or frame is None:
                    if not self._running:
                        break
                    failed_reads += 1
                    now = time.monotonic()
                    if failed_reads in {90, 180}:
                        self.error_ready.emit(self.label, f"RTSP 读取失败({failed_reads}): {self.url}")
                    if rtsp_read_should_reconnect(failed_reads, last_frame_at, now):
                        self.log_ready.emit(self.label, "视频连接中断，正在重连。")
                        self._release_capture(capture)
                        capture, backend, open_diagnostics = self._open_capture_with_retry(cv2)
                        if not self._running:
                            break
                        self._set_capture(capture)
                        if capture is None or not capture.isOpened():
                            self.error_ready.emit(self.label, "视频重连失败，请检查视频服务或网络。")
                            if open_diagnostics:
                                self.error_ready.emit(self.label, f"GStreamer 打开诊断: {open_diagnostics}")
                            break
                        failed_reads = 0
                        last_frame_at = time.monotonic()
                        self.log_ready.emit(self.label, "视频已重连。")
                    time.sleep(0.02)
                    continue
                failed_reads = 0
                last_frame_at = time.monotonic()
                rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                height, width, channels = rgb.shape
                image = QImage(rgb.data, width, height, channels * width, QImage.Format_RGB888).copy()
                locker = QMutexLocker(self._frame_mutex)
                self._latest_frame = image
                self._latest_sequence += 1
                del locker
        finally:
            self._release_capture(capture)
            self.finished.emit(self.stream_kind)

    def stop(self) -> None:
        self._running = False
        self._release_capture()

    def _set_capture(self, capture) -> None:
        with self._capture_lock:
            self._capture = capture

    def _release_capture(self, capture=None) -> None:
        with self._capture_lock:
            target = capture if capture is not None else self._capture
            if target is None:
                return
            if target is self._capture:
                self._capture = None
        try:
            target.release()
        except Exception:
            pass

    def _open_capture(self, cv2):
        pipeline = gstreamer_rtsp_pipeline(self.url)
        capture, diagnostics = _open_gstreamer_capture(cv2, pipeline)
        if capture.isOpened():
            return capture, RTSP_BACKEND_GSTREAMER, ""
        return capture, RTSP_BACKEND_GSTREAMER, diagnostics

    def _open_capture_with_retry(self, cv2):
        deadline = time.monotonic() + RTSP_OPEN_RETRY_SECONDS
        last_capture = None
        backend = RTSP_BACKEND_GSTREAMER
        diagnostics = ""
        attempts = 0
        while self._running:
            attempts += 1
            capture, backend, diagnostics = self._open_capture(cv2)
            if capture.isOpened():
                if last_capture is not None:
                    self._release_capture(last_capture)
                if attempts > 1:
                    self.log_ready.emit(self.label, f"RTSP 第 {attempts} 次连接成功: {self.url}")
                return capture, backend, diagnostics
            if last_capture is not None:
                self._release_capture(last_capture)
            last_capture = capture
            if time.monotonic() >= deadline:
                break
            if attempts == 1:
                self.log_ready.emit(self.label, f"RTSP 等待视频服务就绪: {self.url}")
            time.sleep(RTSP_OPEN_RETRY_INTERVAL_SECONDS)
        return last_capture, backend, diagnostics

    def _read_latest_frame(self, capture, backend: str):
        return capture.read()

    def latest_frame(self, last_sequence: int) -> tuple[int, QImage | None]:
        locker = QMutexLocker(self._frame_mutex)
        if self._latest_sequence == last_sequence or self._latest_frame is None:
            del locker
            return last_sequence, None
        sequence = self._latest_sequence
        image = self._latest_frame.copy()
        del locker
        return sequence, image


class ControlVideoPanel(QFrame):
    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        height = self.height()
        if height > 0:
            parent_width = self.parentWidget().width() if self.parentWidget() is not None else 0
            target_width = max(640, int(height * 16 / 9))
            if parent_width > 0:
                target_width = min(parent_width, target_width)
            if self.minimumWidth() != target_width or self.maximumWidth() != target_width:
                self.setMinimumWidth(target_width)
                self.setMaximumWidth(target_width)


class ControlVideoView(QLabel):
    def __init__(self, text: str) -> None:
        super().__init__(text)
        self.pip_overlay: QLabel | None = None

    def set_pip_overlay(self, overlay: QLabel) -> None:
        self.pip_overlay = overlay
        self.position_overlays()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self.position_overlays()

    def position_speed_overlay(self) -> None:
        self.position_overlays()

    def position_overlays(self) -> None:
        self.position_pip_overlay()

    def position_pip_overlay(self) -> None:
        overlay = self.pip_overlay
        if overlay is None:
            return
        if not overlay.isVisible():
            return
        margin = 20
        width = max(240, min(390, int(self.width() * 0.30)))
        height = max(96, int(width * 9 / 16))
        overlay.setGeometry(margin, margin, width, height)
        overlay.raise_()


class ControlVideoPipView(QLabel):
    def __init__(self, owner, text: str, parent: QWidget, switch_method: str = "switch_body_video_focus") -> None:
        super().__init__(text, parent)
        self.owner = owner
        self.switch_method = switch_method

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.LeftButton:
            switch = getattr(self.owner, self.switch_method, None)
            if callable(switch):
                try:
                    switch()
                except Exception as exc:
                    log_error = getattr(self.owner, "log_rtsp_error", None)
                    if callable(log_error):
                        log_error("视频", f"小窗切换失败: {exc}")
            event.accept()
            return
        super().mousePressEvent(event)


class ControlVideoMixin:
    def _make_video_panel(self, stream_kind: str) -> tuple[QFrame, QComboBox, QLabel, QPushButton]:
        panel = ControlVideoPanel()
        panel.setObjectName("ControlVideoPanel")
        panel.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        source_combo = QComboBox()
        source_combo.hide()
        source_combo.setMinimumWidth(160)
        source_combo.currentIndexChanged.connect(lambda _index, kind=stream_kind: self.video_source_changed(kind))
        start_btn = QPushButton("视频开")
        start_btn.setObjectName("SoftPrimary")
        start_btn.setMinimumWidth(88)
        start_btn.clicked.connect(lambda _checked=False, kind=stream_kind: self.toggle_video_stream(kind))

        video_view = ControlVideoView("")
        video_view.setObjectName("ControlVideoViewport")
        video_view.setAlignment(Qt.AlignCenter)
        video_view.setMinimumHeight(320)
        video_view.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        video_view.setWordWrap(True)
        if stream_kind == "body":
            pip_view = ControlVideoPipView(self, "", video_view, "switch_body_video_focus")
            pip_view.setObjectName("ControlVideoPipViewport")
            pip_view.setAlignment(Qt.AlignCenter)
            pip_view.setCursor(Qt.PointingHandCursor)
            pip_view.setToolTip("点击切换主画面/副画面")
            pip_view.hide()
            video_view.set_pip_overlay(pip_view)
            self.body_video_pip_view = pip_view

        layout.addWidget(video_view, 1)
        return panel, source_combo, video_view, start_btn

    def refresh_video_sources(self) -> bool:
        sources = control_helpers.video_source_options(getattr(self.profile(), "key", ""))
        changed = False
        for combo in (getattr(self, "body_video_source_combo", None), getattr(self, "l1_video_source_combo", None)):
            if combo is None:
                continue
            current_data = combo.currentData()
            existing = [(combo.itemText(index), combo.itemData(index)) for index in range(combo.count())]
            if existing != sources:
                combo.blockSignals(True)
                combo.clear()
                for label, source in sources:
                    combo.addItem(label, source)
                index = combo.findData(current_data)
                combo.setCurrentIndex(index if index >= 0 else 0)
                combo.blockSignals(False)
                changed = True
            if combo is getattr(self, "body_video_source_combo", None):
                self._refresh_body_pip_source()
            self._refresh_video_label(combo)
        return changed

    def _video_source_button_text(self, label: str) -> str:
        return label[:-2] if label.endswith("相机") else label

    def _refresh_video_label(self, combo: QComboBox) -> None:
        if combo is self._video_combo_for_kind(self.video_stream_kind) and self.video_stream_process is not None:
            return
        if combo is getattr(self, "body_video_source_combo", None):
            self.body_video_view.setText("")
            self._refresh_body_pip_label()
        elif combo is getattr(self, "l1_video_source_combo", None):
            self.l1_video_view.setText("")

    def video_source_changed(self, stream_kind: str) -> bool:
        combo = self._video_combo_for_kind(stream_kind)
        if stream_kind == "body":
            self.body_video_display_swapped = False
            self._refresh_body_pip_source()
        self._refresh_video_label(combo)
        if self.video_stream_kind == stream_kind and self.video_stream_process is not None:
            self.stop_video_stream()
            return self.start_video_stream(stream_kind)
        return False

    def _refresh_body_pip_source(self) -> bool:
        combo = getattr(self, "body_video_source_combo", None)
        pip_view = getattr(self, "body_video_pip_view", None)
        if combo is None or pip_view is None:
            return False
        if combo.count() < 2:
            self.body_video_pip_topic = ""
            self.body_video_pip_label = ""
            pip_view.hide()
            return False
        rear_index = self._body_video_source_index(("后", "rear"), fallback=1)
        front_index = self._body_video_source_index(("前", "front"), fallback=0)
        current_source = combo.currentData()
        pip_index = front_index if current_source == combo.itemData(rear_index) else rear_index
        self.body_video_pip_topic = str(combo.itemData(pip_index) or "")
        self.body_video_pip_label = self._video_source_button_text(combo.itemText(pip_index)) or "副画面"
        if getattr(self, "body_pip_video_stream_process", None) is None:
            pip_view.hide()
        self._refresh_body_pip_label()
        position_overlay = getattr(self.body_video_view, "position_overlays", None)
        if callable(position_overlay):
            position_overlay()
        return bool(self.body_video_pip_topic)

    def _body_video_source_index(self, keywords: tuple[str, ...], *, fallback: int) -> int:
        combo = self.body_video_source_combo
        for index in range(combo.count()):
            text = f"{combo.itemText(index)} {combo.itemData(index) or ''}".lower()
            if any(keyword.lower() in text for keyword in keywords):
                return index
        if combo.count() <= 0:
            return -1
        return max(0, min(fallback, combo.count() - 1))

    def _refresh_body_pip_label(self) -> None:
        pip_view = getattr(self, "body_video_pip_view", None)
        if pip_view is None:
            return
        if getattr(self, "body_pip_video_stream_process", None) is not None:
            return
        pip_view.setText("")

    def switch_body_video_focus(self) -> bool:
        pip_topic = getattr(self, "body_video_pip_topic", "")
        pip_process = getattr(self, "body_pip_video_stream_process", None)
        if not pip_topic or pip_process is None:
            return False
        self.body_video_display_swapped = not getattr(self, "body_video_display_swapped", False)
        self._swap_body_video_pixmaps()
        return True

    def _video_combo_for_kind(self, stream_kind: str) -> QComboBox:
        return self.l1_video_source_combo if stream_kind == "l1" else self.body_video_source_combo

    def _video_view_for_kind(self, stream_kind: str) -> QLabel:
        if stream_kind == "body_pip":
            return self.body_video_pip_view
        return self.l1_video_view if stream_kind == "l1" else self.body_video_view

    def _video_button_for_kind(self, stream_kind: str) -> QPushButton:
        return self.l1_video_btn if stream_kind == "l1" else self.body_video_btn

    def toggle_video_stream(self, stream_kind: str) -> bool:
        if self.video_stream_kind == stream_kind and self.video_stream_process is not None:
            return self.stop_video_stream()
        self.stop_video_stream()
        return self.start_video_stream(stream_kind)

    def video_stream_running(self, stream_kind: str) -> bool:
        thread = getattr(self, "video_stream_thread", None)
        return bool(self.video_stream_kind == stream_kind and thread is not None and thread.isRunning())

    def start_video_stream(self, stream_kind: str) -> bool:
        if not self.page_active:
            return False
        combo = self._video_combo_for_kind(stream_kind)
        source = combo.currentData()
        if not source:
            return False
        url = control.control_video_rtsp_url(self.profile(), str(source))
        if not url:
            return False
        self.video_stream_request_id += 1
        self.video_stream_buffer = ""
        self.video_stream_kind = stream_kind
        if stream_kind == "body":
            self.body_video_display_swapped = False
        view = self._video_view_for_kind(stream_kind)
        self._set_video_status_text(view, "", replace_pixmap=True)
        button = self._video_button_for_kind(stream_kind)
        set_button_role(button, "视频关", "Danger")
        self._prepare_rtsp_source(str(source), url)
        thread, worker = self._start_rtsp_worker(stream_kind, url, "视频")
        self.video_stream_thread = thread
        self.video_stream_worker = worker
        self.video_stream_last_sequence = 0
        self.video_stream_process = thread
        self._refresh_rtsp_frame_timer()
        if stream_kind == "body":
            self._start_body_pip_video_stream()
        return True

    def stop_video_stream(self) -> bool:
        pip_was_running = self._stop_body_pip_video_stream()
        thread = getattr(self, "video_stream_thread", None)
        worker = getattr(self, "video_stream_worker", None)
        was_running = thread is not None and thread.isRunning()
        stream_kind = getattr(self, "video_stream_kind", "")
        self.video_stream_request_id = getattr(self, "video_stream_request_id", 0) + 1
        self.video_stream_process = None
        self.video_stream_thread = None
        self.video_stream_worker = None
        self.video_stream_last_sequence = 0
        self.video_stream_buffer = ""
        self.video_stream_kind = ""
        if stream_kind == "body":
            self.body_video_display_swapped = False
        self._stop_rtsp_worker(thread, worker)
        self._refresh_rtsp_frame_timer()
        if stream_kind:
            set_button_role(self._video_button_for_kind(stream_kind), "视频开", "SoftPrimary")
            self._refresh_video_label(self._video_combo_for_kind(stream_kind))
        return was_running or pip_was_running

    def _start_body_pip_video_stream(self) -> bool:
        if not self.page_active:
            return False
        if not self._refresh_body_pip_source():
            return False
        source = getattr(self, "body_video_pip_topic", "")
        if not source:
            return False
        url = control.control_video_rtsp_url(self.profile(), str(source))
        if not url:
            return False
        self._stop_body_pip_video_stream(clear_label=False)
        self.body_pip_video_stream_request_id += 1
        self.body_pip_video_stream_buffer = ""
        pip_view = self.body_video_pip_view
        self._set_video_status_text(pip_view, "", replace_pixmap=True)
        pip_view.hide()
        thread, worker = self._start_rtsp_worker("body_pip", url, "后视视频")
        self.body_pip_video_stream_thread = thread
        self.body_pip_video_stream_worker = worker
        self.body_pip_video_stream_last_sequence = 0
        self.body_pip_video_stream_process = thread
        self._refresh_rtsp_frame_timer()
        return True

    def _stop_body_pip_video_stream(self, *, clear_label: bool = True) -> bool:
        thread = getattr(self, "body_pip_video_stream_thread", None)
        worker = getattr(self, "body_pip_video_stream_worker", None)
        was_running = thread is not None and thread.isRunning()
        self.body_pip_video_stream_request_id = getattr(self, "body_pip_video_stream_request_id", 0) + 1
        self.body_pip_video_stream_process = None
        self.body_pip_video_stream_thread = None
        self.body_pip_video_stream_worker = None
        self.body_pip_video_stream_last_sequence = 0
        self.body_pip_video_stream_buffer = ""
        self._stop_rtsp_worker(thread, worker)
        self.body_video_pip_view.hide()
        self._refresh_rtsp_frame_timer()
        if clear_label:
            self._refresh_body_pip_label()
        return was_running

    def _start_rtsp_worker(self, stream_kind: str, url: str, label: str) -> tuple[QThread, RtspVideoWorker]:
        thread = QThread(self)
        worker = RtspVideoWorker(stream_kind, url, label)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.log_ready.connect(self.log_rtsp_message)
        worker.error_ready.connect(self.log_rtsp_error)
        if stream_kind == "body_pip":
            worker.finished.connect(lambda _kind: self.body_pip_rtsp_worker_finished())
        else:
            worker.finished.connect(lambda kind: self.rtsp_worker_finished(kind))
        worker.finished.connect(thread.quit)
        worker.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.start()
        return thread, worker

    def _refresh_rtsp_frame_timer(self) -> None:
        timer = getattr(self, "rtsp_frame_timer", None)
        if timer is None:
            return
        running = any(
            thread is not None and thread.isRunning()
            for thread in (
                getattr(self, "video_stream_thread", None),
                getattr(self, "body_pip_video_stream_thread", None),
            )
        )
        is_active = timer.isActive() if hasattr(timer, "isActive") else False
        if running and not is_active:
            timer.start()
        elif not running and is_active:
            timer.stop()

    def flush_latest_rtsp_frames(self) -> None:
        worker = getattr(self, "video_stream_worker", None)
        if worker is not None:
            sequence, image = worker.latest_frame(getattr(self, "video_stream_last_sequence", 0))
            self.video_stream_last_sequence = sequence
            if image is not None:
                self.update_rtsp_frame(getattr(worker, "stream_kind", "body"), image)
        pip_worker = getattr(self, "body_pip_video_stream_worker", None)
        if pip_worker is not None:
            sequence, image = pip_worker.latest_frame(getattr(self, "body_pip_video_stream_last_sequence", 0))
            self.body_pip_video_stream_last_sequence = sequence
            if image is not None:
                self.update_rtsp_frame("body_pip", image)
    def _stop_rtsp_worker(self, thread, worker) -> None:
        if worker is not None:
            worker.stop()
        if thread is not None and thread.isRunning():
            thread.quit()
            QTimer.singleShot(1200, lambda t=thread: self._terminate_rtsp_thread_if_running(t))

    def _terminate_rtsp_thread_if_running(self, thread) -> None:
        try:
            if thread is not None and thread.isRunning():
                thread.terminate()
        except RuntimeError:
            return

    def _prepare_rtsp_source(self, source: str, url: str) -> None:
        command = control.control_video_stream_command(self.profile(), source)
        self.runner.run(
            command,
            "准备视频",
            concurrency="parallel",
            locks=("rtsp-video",),
        )

    def update_rtsp_frame(self, stream_kind: str, image: QImage) -> None:
        pixmap = QPixmap.fromImage(image)
        if pixmap.isNull():
            return
        display_kind = self._video_display_kind(stream_kind)
        view = self._video_view_for_kind(display_kind)
        if display_kind == "body_pip":
            view.show()
        self._set_video_pixmap(view, pixmap)

    def _video_display_kind(self, stream_kind: str) -> str:
        if stream_kind not in {"body", "body_pip"}:
            return stream_kind
        if not getattr(self, "body_video_display_swapped", False):
            return stream_kind
        return "body_pip" if stream_kind == "body" else "body"

    def _swap_body_video_pixmaps(self) -> None:
        main_view = getattr(self, "body_video_view", None)
        pip_view = getattr(self, "body_video_pip_view", None)
        if main_view is None or pip_view is None:
            return
        main_pixmap = self._copy_label_pixmap(main_view)
        pip_pixmap = self._copy_label_pixmap(pip_view)
        main_text = self._label_text(main_view)
        pip_text = self._label_text(pip_view)
        if pip_pixmap is not None and not pip_pixmap.isNull():
            main_view.setPixmap(pip_pixmap)
            main_view.setText("")
        else:
            main_view.clear()
            main_view.setText(pip_text)
        if main_pixmap is not None and not main_pixmap.isNull():
            pip_view.setPixmap(main_pixmap)
            pip_view.setText("")
        else:
            pip_view.clear()
            pip_view.setText(main_text)
        position_overlay = getattr(main_view, "position_overlays", None)
        if callable(position_overlay):
            position_overlay()

    def _label_text(self, label: QLabel) -> str:
        text = getattr(label, "text", "")
        return str(text()) if callable(text) else str(text)

    def _copy_label_pixmap(self, label: QLabel) -> QPixmap | None:
        pixmap = label.pixmap()
        if pixmap is None or pixmap.isNull():
            return None
        return pixmap.copy()

    def _set_video_pixmap(self, label: QLabel, pixmap: QPixmap) -> None:
        target_size = label.contentsRect().size()
        if target_size.width() > 0 and target_size.height() > 0:
            pixmap = self._video_pixmap_with_letterbox_fill(pixmap, target_size)
        label.setText("")
        label.setPixmap(pixmap)
        position_overlay = getattr(label, "position_overlays", None)
        if callable(position_overlay):
            position_overlay()

    def _set_video_status_text(self, label: QLabel | None, text: str, *, replace_pixmap: bool = False) -> None:
        if label is None:
            return
        pixmap = label.pixmap()
        if not replace_pixmap and pixmap is not None and not pixmap.isNull():
            return
        label.clear()
        label.setText(text)
        position_overlay = getattr(label, "position_overlays", None)
        if callable(position_overlay):
            position_overlay()

    def _rtsp_view_for_label(self, label: str) -> QLabel | None:
        if label == "后视视频":
            return getattr(self, "body_video_pip_view", None)
        if label == "视频":
            stream_kind = getattr(self, "video_stream_kind", "") or "body"
            return self._video_view_for_kind(stream_kind)
        return None

    def _video_pixmap_with_letterbox_fill(self, source: QPixmap, target_size) -> QPixmap:
        foreground = source.scaled(target_size, Qt.KeepAspectRatio, Qt.FastTransformation)
        fg_x = max(0, (target_size.width() - foreground.width()) // 2)
        fg_y = max(0, (target_size.height() - foreground.height()) // 2)
        canvas = QPixmap(target_size)
        canvas.fill(Qt.black)
        painter = QPainter(canvas)
        painter.drawPixmap(fg_x, fg_y, foreground)
        painter.end()
        return canvas

    def log_rtsp_message(self, label: str, message: str) -> None:
        self.runner.output.emit(f"[{label}] {message}\n")

    def log_rtsp_error(self, label: str, message: str) -> None:
        self.runner.output.emit(f"[{label}] ERROR: {message}\n")
        visible_message = LogPanel.clean_text(message).strip() or "视频连接异常"
        self._set_video_status_text(self._rtsp_view_for_label(label), visible_message)

    def rtsp_worker_finished(self, stream_kind: str, code: int = 0) -> None:
        if stream_kind != self.video_stream_kind:
            return
        self.video_stream_process = None
        self.video_stream_thread = None
        self.video_stream_worker = None
        self.video_stream_last_sequence = 0
        self.video_stream_buffer = ""
        self.video_stream_kind = ""
        if stream_kind:
            set_button_role(self._video_button_for_kind(stream_kind), "视频开", "SoftPrimary")
            if code != 0:
                self._video_view_for_kind(stream_kind).setText(f"视频已断开({code})")
        if stream_kind == "body":
            self.body_video_display_swapped = False
            self._stop_body_pip_video_stream()
        self._refresh_rtsp_frame_timer()

    def body_pip_rtsp_worker_finished(self, code: int = 0) -> None:
        self.body_pip_video_stream_process = None
        self.body_pip_video_stream_thread = None
        self.body_pip_video_stream_worker = None
        self.body_pip_video_stream_last_sequence = 0
        self.body_pip_video_stream_buffer = ""
        self.body_video_pip_view.hide()
        self._refresh_rtsp_frame_timer()
