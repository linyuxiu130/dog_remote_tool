from __future__ import annotations

import base64
from dataclasses import dataclass
import json
import threading
import time

from PyQt5.QtCore import QMutex, QMutexLocker, QObject, QProcess, Qt, QThread, QTimer, pyqtSignal, pyqtSlot
from PyQt5.QtGui import QImage, QPainter, QPixmap
from PyQt5.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QSizePolicy, QVBoxLayout, QWidget

from dog_remote_tool.core.shell import CommandSpec
from dog_remote_tool.modules import control, navigation
from dog_remote_tool.ui.log_panel import LogPanel
from dog_remote_tool.ui.pages.control import video as control_video
from dog_remote_tool.ui.pages.control.stream_ui import set_button_role


NAV_CAMERA_DISPLAY_INTERVAL_MS = 16
NAV_CAMERA_OVERLAY_MAX_AGE_MS = 500
NAV_CAMERA_RTSP_OPEN_TIMEOUT_SECONDS = 5.0
NAV_CAMERA_READ_FAILURE_REPORT_COUNTS = (90, 180, 300)
NAV_CAMERA_READ_RECONNECT_FAILURES = 180
NAV_CAMERA_READ_RECONNECT_SECONDS = 4.0


@dataclass(frozen=True)
class NavigationOverlaySnapshot:
    width: int
    height: int
    global_points: tuple[tuple[float, float], ...]
    local_points: tuple[tuple[float, float], ...]
    received_at: float
    stamp: float = 0.0
    global_topic: str = ""
    local_topic: str = ""

    def is_fresh(self, now: float | None = None, max_age_ms: int = NAV_CAMERA_OVERLAY_MAX_AGE_MS) -> bool:
        now = time.monotonic() if now is None else now
        return (now - self.received_at) * 1000.0 <= max_age_ms


def _point_pairs(value) -> tuple[tuple[float, float], ...]:
    if not isinstance(value, list):
        return ()
    points: list[tuple[float, float]] = []
    for item in value:
        if not isinstance(item, list) or len(item) < 2:
            continue
        try:
            points.append((float(item[0]), float(item[1])))
        except (TypeError, ValueError):
            continue
    return tuple(points)


def parse_navigation_overlay_line(line: str, *, received_at: float | None = None) -> NavigationOverlaySnapshot | None:
    prefix = "NAV_CAMERA_OVERLAY_JSON="
    if not line.startswith(prefix):
        return None
    encoded = line[len(prefix) :].strip()
    try:
        payload = json.loads(base64.b64decode(encoded.encode("ascii")).decode("utf-8"))
    except (ValueError, json.JSONDecodeError):
        return None
    try:
        width = int(payload.get("width") or 1920)
        height = int(payload.get("height") or 1080)
    except (TypeError, ValueError):
        width, height = 1920, 1080
    return NavigationOverlaySnapshot(
        width=max(1, width),
        height=max(1, height),
        global_points=_point_pairs(payload.get("global")),
        local_points=_point_pairs(payload.get("local")),
        received_at=time.monotonic() if received_at is None else received_at,
        stamp=float(payload.get("stamp") or 0.0),
        global_topic=str(payload.get("global_topic") or ""),
        local_topic=str(payload.get("local_topic") or ""),
    )


def consume_navigation_overlay_output(
    buffer: str,
    chunk: str,
    *,
    received_at: float | None = None,
) -> tuple[str, list[NavigationOverlaySnapshot]]:
    text = buffer + chunk
    lines = text.split("\n")
    remaining = lines.pop() if not text.endswith("\n") else ""
    snapshots = []
    for line in lines:
        snapshot = parse_navigation_overlay_line(line.strip(), received_at=received_at)
        if snapshot is not None:
            snapshots.append(snapshot)
    return remaining, snapshots


class NavigationOverlayStore:
    def __init__(self) -> None:
        self._mutex = QMutex()
        self._snapshot: NavigationOverlaySnapshot | None = None

    def update(self, snapshot: NavigationOverlaySnapshot) -> None:
        locker = QMutexLocker(self._mutex)
        self._snapshot = snapshot
        del locker

    def clear(self) -> None:
        locker = QMutexLocker(self._mutex)
        self._snapshot = None
        del locker

    def latest(self, *, max_age_ms: int = NAV_CAMERA_OVERLAY_MAX_AGE_MS) -> NavigationOverlaySnapshot | None:
        locker = QMutexLocker(self._mutex)
        snapshot = self._snapshot
        del locker
        if snapshot is None or not snapshot.is_fresh(max_age_ms=max_age_ms):
            return None
        return snapshot


def navigation_camera_read_should_reconnect(failed_reads: int, last_frame_at: float, now: float) -> bool:
    return (
        failed_reads >= NAV_CAMERA_READ_RECONNECT_FAILURES
        or now - last_frame_at >= NAV_CAMERA_READ_RECONNECT_SECONDS
    )


class NavigationCameraWorker(QObject):
    log_ready = pyqtSignal(str, str)
    error_ready = pyqtSignal(str, str)
    finished = pyqtSignal(int)

    def __init__(self, url: str, overlay_store: NavigationOverlayStore) -> None:
        super().__init__()
        self.url = url
        self.overlay_store = overlay_store
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
            self.error_ready.emit("导航视角", f"无法导入 OpenCV: {exc}")
            self.finished.emit(2)
            return
        capture, diagnostics = self._open_capture_with_retry(cv2)
        if capture is None:
            self.finished.emit(3)
            return
        self._set_capture(capture)
        if not capture.isOpened():
            self.error_ready.emit("导航视角", f"RTSP 打开失败: {self.url}")
            if diagnostics:
                self.error_ready.emit("导航视角", f"GStreamer 打开诊断: {diagnostics}")
            self._release_capture(capture)
            self.finished.emit(3)
            return
        self.log_ready.emit("导航视角", f"RTSP 已连接: {self.url}")
        failed_reads = 0
        reported_read_stall = False
        last_frame_at = time.monotonic()
        exit_code = 0
        try:
            while self._running:
                ok, frame = capture.read()
                if not ok or frame is None:
                    if not self._running:
                        break
                    failed_reads += 1
                    now = time.monotonic()
                    if failed_reads in NAV_CAMERA_READ_FAILURE_REPORT_COUNTS:
                        reported_read_stall = True
                        self.error_ready.emit("导航视角", f"RTSP 读取失败({failed_reads})")
                    if navigation_camera_read_should_reconnect(failed_reads, last_frame_at, now):
                        self.log_ready.emit("导航视角", "视频连接中断，正在重连。")
                        self._release_capture(capture)
                        capture, diagnostics = self._open_capture_with_retry(cv2)
                        if not self._running:
                            break
                        self._set_capture(capture)
                        if capture is None or not capture.isOpened():
                            self.error_ready.emit("导航视角", "视频重连失败，请检查视频服务或网络。")
                            if diagnostics:
                                self.error_ready.emit("导航视角", f"GStreamer 打开诊断: {diagnostics}")
                            exit_code = 3
                            break
                        failed_reads = 0
                        reported_read_stall = False
                        last_frame_at = time.monotonic()
                        self.log_ready.emit("导航视角", "视频已重连。")
                    time.sleep(0.02)
                    continue
                if reported_read_stall:
                    self.log_ready.emit("导航视角", "导航视角已恢复")
                    reported_read_stall = False
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
            self.finished.emit(exit_code)

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

    def _open_capture_with_retry(self, cv2):
        capture = None
        diagnostics = ""
        deadline = time.monotonic() + NAV_CAMERA_RTSP_OPEN_TIMEOUT_SECONDS
        while self._running:
            capture, diagnostics = control_video._open_gstreamer_capture(
                cv2,
                control_video.gstreamer_rtsp_pipeline(self.url),
            )
            if capture.isOpened():
                return capture, diagnostics
            capture.release()
            if time.monotonic() >= deadline:
                return capture, diagnostics
            time.sleep(0.25)
        return None, diagnostics

    def latest_frame(self, last_sequence: int) -> tuple[int, QImage | None]:
        locker = QMutexLocker(self._frame_mutex)
        if self._latest_sequence == last_sequence or self._latest_frame is None:
            del locker
            return last_sequence, None
        sequence = self._latest_sequence
        image = self._latest_frame.copy()
        del locker
        return sequence, image

class NavigationCameraView(QLabel):
    clicked = pyqtSignal()

    def __init__(self) -> None:
        super().__init__("导航视角待连接")
        self.setAlignment(Qt.AlignCenter)
        self.setWordWrap(True)
        self.setCursor(Qt.PointingHandCursor)
        self.setMinimumHeight(180)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setStyleSheet("background:#020617;border:1px solid #d7e2ef;border-radius:8px;color:#dbeafe;")

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.LeftButton:
            self.clicked.emit()
            event.accept()
            return
        super().mousePressEvent(event)


class NavigationCameraOverlayMixin:
    def _build_navigation_camera_panel(self) -> QFrame:
        panel = QFrame()
        panel.setObjectName("NavigationCameraPanel")
        panel.setMinimumWidth(360)
        panel.setMaximumWidth(420)
        panel.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Expanding)
        panel.setStyleSheet(
            "QFrame#NavigationCameraPanel{background:#ffffff;border:1px solid #e3eaf3;border-radius:8px;}"
        )
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)
        toolbar = QFrame()
        toolbar_layout = QVBoxLayout(toolbar)
        toolbar_layout.setContentsMargins(0, 0, 0, 0)
        toolbar_layout.setSpacing(6)
        self.nav_camera_toggle_button = QPushButton("视角开")
        self.nav_camera_toggle_button.setObjectName("SoftPrimary")
        self.nav_camera_toggle_button.clicked.connect(self.toggle_navigation_camera_overlay)
        self.nav_camera_size_button = QPushButton("放大")
        self.nav_camera_size_button.clicked.connect(self.toggle_navigation_camera_size)
        button_row = QWidget()
        button_layout = QHBoxLayout(button_row)
        button_layout.setContentsMargins(0, 0, 0, 0)
        button_layout.setSpacing(8)
        button_layout.addWidget(self.nav_camera_toggle_button, 1)
        button_layout.addWidget(self.nav_camera_size_button, 1)
        toolbar_layout.addWidget(button_row)
        self.nav_camera_status_label = QLabel("RGB 实时画面")
        self.nav_camera_status_label.setObjectName("Muted")
        self.nav_camera_status_label.setAlignment(Qt.AlignCenter)
        toolbar_layout.addWidget(self.nav_camera_status_label)
        self.nav_camera_view = NavigationCameraView()
        self.nav_camera_view.clicked.connect(self.toggle_navigation_camera_size)
        layout.addWidget(toolbar)
        layout.addWidget(self.nav_camera_view, 1)
        return panel

    def toggle_navigation_camera_size(self) -> bool:
        expanded = not bool(getattr(self, "nav_camera_expanded", False))
        self.nav_camera_expanded = expanded
        panel = getattr(self, "nav_camera_panel", None)
        if panel is not None:
            panel.setMinimumWidth(620 if expanded else 360)
            panel.setMaximumWidth(760 if expanded else 420)
        if hasattr(self, "nav_camera_size_button"):
            self.nav_camera_size_button.setText("缩小" if expanded else "放大")
        return expanded

    def toggle_navigation_camera_overlay(self) -> bool:
        if getattr(self, "nav_camera_video_thread", None) is not None:
            return self.stop_navigation_camera_overlay()
        return self.start_navigation_camera_overlay()

    def start_navigation_camera_overlay(self) -> bool:
        if not getattr(self, "page_active", False):
            return False
        if getattr(self, "nav_camera_video_thread", None) is not None:
            return False
        url = control.control_video_rtsp_url(self.profile(), "front")
        if not url:
            return False
        self._set_navigation_camera_text("正在连接导航视角")
        set_button_role(self.nav_camera_toggle_button, "视角关", "Danger")
        self._prepare_navigation_camera_rtsp(url)
        thread = QThread(self)
        worker = NavigationCameraWorker(url, self.nav_camera_overlay_store)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.log_ready.connect(self.log_navigation_camera_message)
        worker.error_ready.connect(self.log_navigation_camera_error)
        worker.finished.connect(self.navigation_camera_worker_finished)
        worker.finished.connect(thread.quit)
        worker.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        self.nav_camera_video_thread = thread
        self.nav_camera_video_worker = worker
        self.nav_camera_video_last_sequence = 0
        thread.start()
        self._refresh_navigation_camera_timer()
        return True

    def stop_navigation_camera_overlay(self) -> bool:
        thread = getattr(self, "nav_camera_video_thread", None)
        worker = getattr(self, "nav_camera_video_worker", None)
        was_running = thread is not None and thread.isRunning()
        self.nav_camera_video_thread = None
        self.nav_camera_video_worker = None
        self.nav_camera_video_last_sequence = 0
        if worker is not None:
            worker.stop()
        if thread is not None and thread.isRunning():
            thread.quit()
            QTimer.singleShot(1200, lambda t=thread: self._terminate_navigation_camera_thread_if_running(t))
        self.stop_navigation_camera_overlay_stream()
        self.nav_camera_overlay_store.clear()
        self._refresh_navigation_camera_timer()
        if hasattr(self, "nav_camera_toggle_button"):
            set_button_role(self.nav_camera_toggle_button, "视角开", "SoftPrimary")
        self._set_navigation_camera_text("导航视角已关闭")
        return was_running

    def _terminate_navigation_camera_thread_if_running(self, thread) -> None:
        try:
            if thread is not None and thread.isRunning():
                thread.terminate()
        except RuntimeError:
            return

    def _prepare_navigation_camera_rtsp(self, url: str) -> None:
        command = control.control_video_stream_command(self.profile(), "front")
        QProcess.startDetached("bash", ["-lc", f"{{ {command}; }} >/dev/null 2>&1"])

    def start_navigation_camera_overlay_stream(self) -> bool:
        slot = getattr(self, "nav_camera_overlay_slot", None)
        if slot is None or slot.is_running():
            return False
        self.nav_camera_overlay_buffer = ""
        process, request_id = slot.start_spec(
            CommandSpec(
                "导航相机叠加流",
                navigation.navigation_camera_overlay_stream_command(self.profile()),
                concurrency="parallel",
                locks=("navigation-camera-overlay-stream",),
            )
        )
        if process is None:
            return False
        process.readyReadStandardOutput.connect(lambda: self.read_navigation_camera_overlay_output(process, request_id))
        process.finished.connect(lambda _code, _status: self.navigation_camera_overlay_stream_finished(process, request_id))
        process.start()
        return True

    def stop_navigation_camera_overlay_stream(self) -> bool:
        self.nav_camera_overlay_buffer = ""
        slot = getattr(self, "nav_camera_overlay_slot", None)
        return bool(slot is not None and slot.stop())

    def read_navigation_camera_overlay_output(self, process, request_id: int) -> None:
        chunk = self.nav_camera_overlay_slot.read_available_text(process, request_id)
        if not chunk:
            return
        self.nav_camera_overlay_buffer, snapshots = consume_navigation_overlay_output(
            self.nav_camera_overlay_buffer,
            chunk,
            received_at=time.monotonic(),
        )
        for snapshot in snapshots:
            self.nav_camera_overlay_store.update(snapshot)
            if hasattr(self, "nav_camera_status_label"):
                parts = []
                if snapshot.global_points:
                    parts.append(f"全局 {len(snapshot.global_points)}")
                if snapshot.local_points:
                    parts.append(f"局部 {len(snapshot.local_points)}")
                self.nav_camera_status_label.setText(" / ".join(parts) if parts else "等待轨迹")

    def navigation_camera_overlay_stream_finished(self, process, request_id: int) -> None:
        output = self.nav_camera_overlay_slot.finish(process, request_id)
        if output is None:
            return
        if getattr(self, "page_active", False) and getattr(self, "nav_camera_video_thread", None) is not None:
            QTimer.singleShot(1500, self.start_navigation_camera_overlay_stream)

    def flush_latest_navigation_camera_frame(self) -> None:
        worker = getattr(self, "nav_camera_video_worker", None)
        if worker is None:
            return
        sequence, image = worker.latest_frame(getattr(self, "nav_camera_video_last_sequence", 0))
        self.nav_camera_video_last_sequence = sequence
        if image is None:
            return
        pixmap = QPixmap.fromImage(image)
        if pixmap.isNull():
            return
        self._set_navigation_camera_pixmap(pixmap)

    def _set_navigation_camera_pixmap(self, pixmap: QPixmap) -> None:
        self._set_navigation_camera_label_pixmap(self.nav_camera_view, pixmap)
        dialog = getattr(self, "workspace_dialog", None)
        workspace_label = getattr(dialog, "camera_view", None)
        if workspace_label is not None:
            self._set_navigation_camera_label_pixmap(workspace_label, pixmap)

    def _set_navigation_camera_label_pixmap(self, label, pixmap: QPixmap) -> None:
        target_size = label.contentsRect().size()
        target_pixmap = pixmap
        if target_size.width() > 0 and target_size.height() > 0:
            if str(getattr(label, "objectName", lambda: "")()) == "WorkspaceCameraOverlay":
                target_pixmap = pixmap.scaled(target_size, Qt.IgnoreAspectRatio, Qt.FastTransformation)
            else:
                target_pixmap = self._navigation_camera_pixmap_fit(pixmap, target_size)
        label.setText("")
        label.setPixmap(target_pixmap)

    def _set_navigation_camera_text(self, text: str) -> None:
        if hasattr(self, "nav_camera_view"):
            self.nav_camera_view.setText(text)

    def _navigation_camera_pixmap_fit(self, source: QPixmap, target_size) -> QPixmap:
        foreground = source.scaled(target_size, Qt.KeepAspectRatio, Qt.FastTransformation)
        fg_x = max(0, (target_size.width() - foreground.width()) // 2)
        fg_y = max(0, (target_size.height() - foreground.height()) // 2)
        canvas = QPixmap(target_size)
        canvas.fill(Qt.black)
        painter = QPainter(canvas)
        painter.drawPixmap(fg_x, fg_y, foreground)
        painter.end()
        return canvas

    def _refresh_navigation_camera_timer(self) -> None:
        timer = getattr(self, "nav_camera_frame_timer", None)
        if timer is None:
            return
        thread = getattr(self, "nav_camera_video_thread", None)
        running = thread is not None and thread.isRunning()
        if running and not timer.isActive():
            timer.start()
        elif not running and timer.isActive():
            timer.stop()

    def navigation_camera_worker_finished(self, code: int = 0) -> None:
        self.nav_camera_video_thread = None
        self.nav_camera_video_worker = None
        self.nav_camera_video_last_sequence = 0
        self._refresh_navigation_camera_timer()
        self.stop_navigation_camera_overlay_stream()
        if hasattr(self, "nav_camera_toggle_button"):
            set_button_role(self.nav_camera_toggle_button, "视角开", "SoftPrimary")
        if code != 0:
            self._set_navigation_camera_text(f"导航视角已断开({code})")

    def log_navigation_camera_message(self, label: str, message: str) -> None:
        if hasattr(self, "nav_camera_status_label"):
            self.nav_camera_status_label.setText(LogPanel.clean_text(message).strip() or "导航视角已连接")

    def log_navigation_camera_error(self, label: str, message: str) -> None:
        self.runner.output.emit(f"[{label}] ERROR: {message}\n")
