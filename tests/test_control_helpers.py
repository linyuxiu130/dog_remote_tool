import sys

import numpy as np

from dog_remote_tool.core.profiles import get_product
from dog_remote_tool.core.shell import CommandSpec
from dog_remote_tool.modules import control
from dog_remote_tool.ui.pages.control import arc_helpers as control_arc_helpers
from dog_remote_tool.ui.pages.control import arc as control_arc
from dog_remote_tool.ui.pages.control import helpers as control_helpers
from dog_remote_tool.ui.pages.control import input_helpers as control_input_helpers
from dog_remote_tool.ui.pages.control import l2_gamepad as control_l2_gamepad
from dog_remote_tool.ui.pages.control import l1_sdk as control_l1_sdk
from dog_remote_tool.ui.pages.control import l1_layout as control_l1_layout
from dog_remote_tool.ui.pages.control import layout as control_layout
from dog_remote_tool.ui.pages.control import lifecycle as control_lifecycle
from dog_remote_tool.ui.pages.control import runtime as control_runtime
from dog_remote_tool.ui.pages.control import state as control_state
from dog_remote_tool.ui.pages.control import speed_helpers as control_speed_helpers
from dog_remote_tool.ui.pages.control import stream_helpers as control_stream_helpers
from dog_remote_tool.ui.pages.control import telemetry as control_telemetry
from dog_remote_tool.ui.pages.control import telemetry_helpers as control_telemetry_helpers
from dog_remote_tool.ui.pages.control import video as control_video
from dog_remote_tool.ui.pages.control import video_sources as control_video_sources
from dog_remote_tool.ui.pages.control.page import ControlPage
from PyQt5.QtGui import QImage
from PyQt5.QtWidgets import QApplication
from helpers import FakeOutput as _FakeOutput, FakeSignal as _FakeSignal


def test_control_video_fullscreen_methods_are_not_exposed():
    assert not hasattr(ControlPage, "open_video_fullscreen")
    assert not hasattr(ControlPage, "open_header_video")
    assert not hasattr(ControlPage, "switch_l1_video_focus")
    assert not hasattr(ControlPage, "_start_l1_pip_video_stream")
    assert not hasattr(ControlPage, "l1_pip_rtsp_worker_finished")
    assert not hasattr(ControlPage, "refresh_fullscreen_keyboard_status")


def test_control_state_initialization_comes_from_state_mixin():
    assert ControlPage._init_control_state is control_state.ControlStateMixin._init_control_state


class _FakeLabel:
    def __init__(self):
        self.text = ""
        self.object_name = ""
        self.cleared = 0
        self.pixmap_value = None
        self.visible = False

    def setText(self, text):
        self.text = text

    def setObjectName(self, name):
        self.object_name = name

    def clear(self):
        self.cleared += 1
        self.pixmap_value = None

    def setPixmap(self, pixmap):
        self.pixmap_value = pixmap

    def winId(self):
        return 12345

    def pixmap(self):
        return self.pixmap_value

    def position_overlays(self):
        return None

    def show(self):
        self.visible = True

    def hide(self):
        self.visible = False


class _FakePixmap:
    def __init__(self, null=False):
        self.null = null

    def isNull(self):
        return self.null

    def copy(self):
        return self



class _FakeStreamProcess:
    NotRunning = 0
    Running = 2
    MergedChannels = 1

    def __init__(self, _parent=None, output=b""):
        self.readyReadStandardOutput = _FakeSignal()
        self.errorOccurred = _FakeSignal()
        self.finished = _FakeSignal()
        self.program = ""
        self.arguments = []
        self.channel_mode = None
        self.deleted = False
        self.state_value = self.NotRunning
        self.writes = []
        self.output = output
        self.error_text = "fake process error"
        self.closed_write_channel = False
        self.wait_calls = []
        self.terminate_calls = 0
        self.kill_calls = 0

    def setProgram(self, program):
        self.program = program

    def setArguments(self, arguments):
        self.arguments = arguments

    def setProcessChannelMode(self, mode):
        self.channel_mode = mode

    def start(self):
        self.state_value = self.Running

    def state(self):
        return self.state_value

    def write(self, data):
        self.writes.append(data)

    def readAllStandardOutput(self):
        output = self.output
        self.output = b""
        return output

    def errorString(self):
        return self.error_text

    def terminate(self):
        self.terminate_calls += 1
        self.state_value = self.NotRunning

    def waitForFinished(self, timeout_ms):
        self.wait_calls.append(timeout_ms)
        return True

    def kill(self):
        self.kill_calls += 1
        self.state_value = self.NotRunning

    def closeWriteChannel(self):
        self.closed_write_channel = True

    def deleteLater(self):
        self.deleted = True


class _FakeTimer:
    def __init__(self):
        self.started = 0
        self.stopped = 0

    def start(self):
        self.started += 1

    def stop(self):
        self.stopped += 1


class _FakeStopSlot:
    def __init__(self):
        self.stopped = 0
        self.stopped_async = 0

    def stop(self):
        self.stopped += 1

    def stop_async(self):
        self.stopped_async += 1


class _FakeSlider:
    def __init__(self, value=0, minimum=0, maximum=350):
        self._value = value
        self._minimum = minimum
        self._maximum = maximum
        self.values = []

    def value(self):
        return self._value

    def minimum(self):
        return self._minimum

    def maximum(self):
        return self._maximum

    def setValue(self, value):
        self._value = value
        self.values.append(value)


class _FakeRunner:
    def __init__(self):
        self.output = _FakeOutput()
        self.technical_output = _FakeOutput()
        self.commands = []

    def run(self, command, display_command=None, **kwargs):
        self.commands.append((command, display_command, kwargs))
        return len(self.commands)


class _FakeControlStreamPage:
    def __init__(self, *, active=True):
        self.runner = _FakeRunner()
        self.page_active = active
        self.l1_sdk_stream_process = None
        self.gamepad_stream_process = None
        self.l2_telemetry_process = None
        self.l1_sdk_stream_request_id = 0
        self.gamepad_stream_request_id = 0
        self.l2_telemetry_request_id = 0
        self.l1_sdk_stream_timer = _FakeTimer()
        self.gamepad_stream_timer = _FakeTimer()
        self.l1_pressed_keys = {"w"}
        self.gamepad_pressed_keys = {"a"}
        self.l1_sdk_stream_buffer = "old"
        self.gamepad_stream_buffer = "old"
        self.l2_telemetry_buffer = "old"
        self.l1_sdk_stream_ready = True
        self.l1_sdk_limits = (0.6, 0.3, 0.8)
        self.gamepad_stream_ready = True
        self.l2_telemetry_ready = True
        self.l1_sdk_last_vector = (1, 2, 3)
        self.gamepad_stream_last_vector = (1, 2, 3, 4)
        self.gamepad_inplace_mode = True
        self.l1_sdk_stream_status = _FakeLabel()
        self.gamepad_stream_status = _FakeLabel()
        self.l2_current_forward_label = _FakeLabel()
        self.l2_current_strafe_label = _FakeLabel()
        self.l2_current_turn_label = _FakeLabel()
        self.l2_current_mode_label = _FakeLabel()
        self.l1_start_stream_btn = _FakeLabel()
        self.start_stream_btn = _FakeLabel()
        self.label_statuses = []
        self.low_load_states = []
        self.events = []
        self.focus_reasons = []
        self.stopped_payloads = []
        self.video_stops = 0
        self.l1_resets = 0
        self.arc_status_slot = _FakeStopSlot()

    def profile(self):
        return type("Profile", (), {"target": "robot@192.168.1.2", "key": "xg2_s100"})()

    def l1_sdk_path(self):
        return "/home/robot/sdk"

    def realtime_max_axis_value(self):
        return 70

    def l1_sdk_linear_speed_value(self):
        return ControlPage.l1_sdk_linear_speed_value(self)

    def l1_sdk_angular_speed_value(self):
        return ControlPage.l1_sdk_angular_speed_value(self)

    def robot_sdk_linear_speed_value(self):
        return ControlPage.robot_sdk_linear_speed_value(self)

    def robot_sdk_angular_speed_value(self):
        return ControlPage.robot_sdk_angular_speed_value(self)

    def stop_l1_sdk_stream(self, *, wait_for_exit=False):
        return ControlPage.stop_l1_sdk_stream(self, wait_for_exit=wait_for_exit)

    def stop_gamepad_stream(self, *, wait_for_exit=False):
        return ControlPage.stop_gamepad_stream(self, wait_for_exit=wait_for_exit)

    def stop_video_stream(self):
        self.video_stops += 1
        return False

    def stop_l2_telemetry_stream(self, *, wait_for_exit=False):
        return ControlPage.stop_l2_telemetry_stream(self, wait_for_exit=wait_for_exit)

    def keyboard_stream_running(self):
        return ControlPage.keyboard_stream_running(self)

    def send_gamepad_neutral(self):
        return ControlPage.send_gamepad_neutral(self)

    def current_l2_gamepad_vector(self):
        return ControlPage.current_l2_gamepad_vector(self)

    def _write_gamepad_stream(self, payload):
        return ControlPage._write_gamepad_stream(self, payload)

    def _write_l1_sdk_stream(self, payload):
        return ControlPage._write_l1_sdk_stream(self, payload)

    def read_l1_sdk_stream_output(self, process, request_id):
        return ControlPage.read_l1_sdk_stream_output(self, process, request_id)

    def l1_sdk_stream_finished(self, process, request_id, code, status):
        return ControlPage.l1_sdk_stream_finished(self, process, request_id, code, status)

    def read_gamepad_stream_output(self, process, request_id):
        return ControlPage.read_gamepad_stream_output(self, process, request_id)

    def gamepad_stream_finished(self, process, request_id, code, status):
        return ControlPage.gamepad_stream_finished(self, process, request_id, code, status)

    def read_l2_telemetry_output(self, process, request_id):
        return ControlPage.read_l2_telemetry_output(self, process, request_id)

    def l2_telemetry_finished(self, process, request_id, code, status):
        return ControlPage.l2_telemetry_finished(self, process, request_id, code, status)

    def _stop_json_stream_process(self, process, payloads, timeout_ms=2000, *, wait_for_exit=False):
        self.stopped_payloads.append((payloads, wait_for_exit))
        process.state_value = _FakeStreamProcess.NotRunning

    def _set_label_status(self, label, state):
        self.label_statuses.append((label, state))

    def _set_control_low_load(self, enabled):
        self.low_load_states.append(enabled)

    def _log_control_event(self, event, payload):
        self.events.append((event, payload))

    def setFocus(self, reason):
        self.focus_reasons.append(reason)

    def reset_l1_telemetry(self):
        self.l1_resets += 1

    def update_l1_target_speed_labels(self):
        return True

    def reset_l2_telemetry(self):
        return ControlPage.reset_l2_telemetry(self)


class _FakeControlSpeedPage:
    def __init__(self, started=False):
        self.started = started
        self.l1_sdk_stream_status = _FakeLabel()
        self.gamepad_stream_status = _FakeLabel()
        self.l1_sdk_stream_process = None
        self.gamepad_stream_process = None
        self.l1_pressed_keys = set()
        self.commands = []
        self.label_statuses = []

    def profile(self):
        return type("Profile", (), {"target": "robot@192.168.1.2"})()

    def set_command(self, spec):
        self.commands.append(spec)
        return self.started

    def l1_sdk_path(self):
        return "/home/robot/sdk"

    def _set_label_status(self, label, state):
        self.label_statuses.append((label, state))


class _FakeVideoPage:
    def __init__(self, output: bytes):
        self.runner = _FakeRunner()
        self.video_stream_process = _FakeStreamProcess(output=output)
        self.video_stream_request_id = 7
        self.video_stream_buffer = ""
        self.video_stream_kind = "main"
        self.body_video_view = _FakeLabel()
        self.l1_video_view = _FakeLabel()
        self.body_video_pip_view = _FakeLabel()
        self.frames = []

    def profile(self):
        return get_product("xg2_s100")

    def _video_view_for_kind(self, kind):
        return {
            "body": self.body_video_view,
            "main": self.body_video_view,
            "l1": self.l1_video_view,
            "body_pip": self.body_video_pip_view,
        }[kind]

    def _set_video_status_text(self, label, text, *, replace_pixmap=False):
        return ControlPage._set_video_status_text(self, label, text, replace_pixmap=replace_pixmap)

    def _set_video_pixmap(self, label, pixmap):
        label.setText("")
        label.setPixmap(pixmap)

    def _rtsp_view_for_label(self, label):
        return ControlPage._rtsp_view_for_label(self, label)

    def _video_display_kind(self, stream_kind):
        return ControlPage._video_display_kind(self, stream_kind)

    def _swap_body_video_pixmaps(self):
        return ControlPage._swap_body_video_pixmaps(self)

    def _label_text(self, label):
        return ControlPage._label_text(self, label)

    def _copy_label_pixmap(self, label):
        return ControlPage._copy_label_pixmap(self, label)

    def update_rtsp_frame(self, stream_kind, image):
        self.frames.append((stream_kind, image))

    def _refresh_rtsp_frame_timer(self):
        return None


class _FakeLatestFrameWorker:
    def __init__(self, stream_kind, image):
        self.stream_kind = stream_kind
        self.image = image
        self.calls = []

    def latest_frame(self, last_sequence):
        self.calls.append(last_sequence)
        return 3, self.image


class _FakeDrainCapture:
    def __init__(self, grabs_before_fail=20):
        self.grabs_before_fail = grabs_before_fail
        self.grabs = 0
        self.retrieves = 0
        self.reads = 0

    def grab(self):
        if self.grabs >= self.grabs_before_fail:
            return False
        self.grabs += 1
        return True

    def retrieve(self):
        self.retrieves += 1
        return True, "latest"

    def read(self):
        self.reads += 1
        return True, "direct"


class _FakeOpenCapture:
    def __init__(self, opened=False):
        self.opened = opened
        self.released = False

    def isOpened(self):
        return self.opened

    def release(self):
        self.released = True


def test_video_rtsp_messages_are_written_to_log():
    page = _FakeVideoPage(b"")

    ControlPage.log_rtsp_message(page, "视频", "RTSP 已连接")
    ControlPage.log_rtsp_error(page, "视频", "RTSP 读取失败")

    assert page.runner.output.lines == ["[视频] RTSP 已连接\n", "[视频] ERROR: RTSP 读取失败\n"]
    assert page.body_video_view.text == "视频读取失败，请检查视频服务或网络。"


def test_video_rtsp_decode_options_are_low_latency():
    assert control_video.RTSP_TRANSPORT == "tcp"
    assert control_video.RTSP_BACKEND_GSTREAMER == "GStreamer low-latency"
    assert control_video.RTSP_DISPLAY_INTERVAL_MS == 16
    assert control_video.RTSP_OPEN_RETRY_INTERVAL_SECONDS == 0.15
    assert control_video.RTSP_DISPLAY_WIDTH == 960
    assert control_video.RTSP_DISPLAY_HEIGHT == 540
    assert control_video.GSTREAMER_H264_DECODER == "avdec_h264"


def test_video_gstreamer_rtsp_pipeline_drops_stale_frames():
    pipeline = control_video.gstreamer_rtsp_pipeline("rtsp://192.168.234.1:8554/front")

    assert "rtspsrc" in pipeline
    assert "protocols=tcp" in pipeline
    assert "latency=0" in pipeline
    assert "drop-on-latency=true" in pipeline
    assert "buffer-mode=none" in pipeline
    assert "rtph264depay" in pipeline
    assert "request-keyframe=true" in pipeline
    assert "wait-for-keyframe=true" in pipeline
    assert "avdec_h264 output-corrupt=false" in pipeline
    assert "videoscale" in pipeline
    assert "video/x-raw,format=BGR,width=960,height=540" in pipeline
    assert "appsink drop=true max-buffers=1 sync=false" in pipeline


def test_video_gstreamer_decoder_probe_checks_known_h264_decoders(monkeypatch):
    inspected = []

    monkeypatch.setattr(control_video, "_gstreamer_libav_plugin_available", lambda: False)
    monkeypatch.setattr(control_video.shutil, "which", lambda _name: "/usr/bin/gst-inspect-1.0")

    def fake_run(command, **_kwargs):
        inspected.append(command[-1])
        return type("Result", (), {"returncode": 0 if command[-1] == "avdec_h264" else 1})()

    monkeypatch.setattr(control_video.subprocess, "run", fake_run)

    assert control_video.gstreamer_h264_decoder_name() == "avdec_h264"
    assert inspected == ["avdec_h264"]
    inspected.clear()
    assert control_video.gstreamer_h264_decoder_available() is True
    assert inspected == ["avdec_h264"]


def test_video_gstreamer_decoder_probe_returns_false_without_inspect(monkeypatch):
    monkeypatch.setattr(control_video, "_gstreamer_libav_plugin_available", lambda: False)
    monkeypatch.setattr(control_video.shutil, "which", lambda _name: None)

    assert control_video.gstreamer_h264_decoder_available() is False


def test_video_gstreamer_decoder_probe_uses_bundled_plugin(monkeypatch):
    monkeypatch.setattr(control_video, "_gstreamer_libav_plugin_available", lambda: True)
    monkeypatch.setattr(control_video.shutil, "which", lambda _name: None)

    assert control_video.gstreamer_h264_decoder_name() == "avdec_h264"
    assert control_video.gstreamer_h264_decoder_available() is True


def test_video_gstreamer_backend_reads_directly():
    worker = control_video.RtspVideoWorker("body", "rtsp://example/front", "视频")
    capture = _FakeDrainCapture()

    ok, frame = worker._read_latest_frame(capture, "GStreamer low-latency")

    assert ok is True
    assert frame == "direct"
    assert capture.grabs == 0
    assert capture.reads == 1


def test_video_read_failures_trigger_reconnect_by_count_or_time(monkeypatch):
    monkeypatch.setattr(control_video, "RTSP_READ_RECONNECT_FAILURES", 3)
    monkeypatch.setattr(control_video, "RTSP_READ_RECONNECT_SECONDS", 4.0)

    assert control_video.rtsp_read_should_reconnect(2, 10.0, 13.0) is False
    assert control_video.rtsp_read_should_reconnect(3, 10.0, 11.0) is True
    assert control_video.rtsp_read_should_reconnect(1, 10.0, 14.1) is True


def test_video_open_retries_until_rtsp_service_is_ready(monkeypatch):
    worker = control_video.RtspVideoWorker("body", "rtsp://example/front", "视频")
    all_captures = [_FakeOpenCapture(False), _FakeOpenCapture(False), _FakeOpenCapture(True)]
    captures = list(all_captures)

    monkeypatch.setattr(control_video, "RTSP_OPEN_RETRY_INTERVAL_SECONDS", 0)
    monkeypatch.setattr(worker, "_open_capture", lambda _cv2: (captures.pop(0), "fake", "not ready"))

    capture, backend, diagnostics = worker._open_capture_with_retry(object())

    assert capture.isOpened() is True
    assert backend == "fake"
    assert diagnostics == "not ready"
    assert captures == []
    assert all_captures[0].released is True
    assert all_captures[1].released is True
    assert all_captures[2].released is False


def test_video_worker_does_not_report_read_failure_after_stop(monkeypatch):
    worker = control_video.RtspVideoWorker("body", "rtsp://example/front", "视频")
    errors = []

    class FakeCapture:
        def __init__(self):
            self.released = False

        def isOpened(self):
            return True

        def read(self):
            worker.stop()
            return False, None

        def release(self):
            self.released = True

    class FakeCv2:
        COLOR_BGR2RGB = 1

    capture = FakeCapture()
    monkeypatch.setitem(sys.modules, "cv2", FakeCv2)
    monkeypatch.setattr(worker, "_open_capture_with_retry", lambda _cv2: (capture, "fake", ""))
    worker.error_ready.connect(lambda label, message: errors.append((label, message)))

    worker.run()

    assert errors == []
    assert capture.released is True


def test_video_worker_reconnects_after_sustained_empty_frames(monkeypatch):
    worker = control_video.RtspVideoWorker("body", "rtsp://example/front", "视频")
    logs = []

    class FakeCapture:
        def __init__(self, frames):
            self.frames = list(frames)
            self.released = False

        def isOpened(self):
            return True

        def read(self):
            if not self.frames:
                return False, None
            frame = self.frames.pop(0)
            if frame is None:
                return False, None
            return True, frame

        def release(self):
            self.released = True

    first_capture = FakeCapture([None, None, None])
    second_capture = FakeCapture([np.zeros((2, 2, 3), dtype=np.uint8)])
    captures = [first_capture, second_capture]

    class FakeCv2:
        COLOR_BGR2RGB = 1

        @staticmethod
        def cvtColor(frame, _code):
            worker.stop()
            return frame

    monkeypatch.setitem(sys.modules, "cv2", FakeCv2)
    monkeypatch.setattr(control_video, "RTSP_READ_RECONNECT_FAILURES", 2)
    monkeypatch.setattr(control_video, "RTSP_READ_RECONNECT_SECONDS", 999.0)
    monkeypatch.setattr(worker, "_open_capture_with_retry", lambda _cv2: (captures.pop(0), "fake", ""))
    monkeypatch.setattr(control_video.time, "sleep", lambda _seconds: None)
    worker.log_ready.connect(lambda label, message: logs.append((label, message)))

    worker.run()

    assert first_capture.released is True
    assert second_capture.released is True
    assert ("视频", "视频已重连。") in logs
    sequence, image = worker.latest_frame(0)
    assert sequence == 1
    assert image is not None


def test_video_flush_pulls_latest_frame_without_signal_backlog():
    page = _FakeVideoPage(b"")
    main_image = object()
    pip_image = object()
    page.video_stream_worker = _FakeLatestFrameWorker("body", main_image)
    page.body_pip_video_stream_worker = _FakeLatestFrameWorker("body_pip", pip_image)
    page.video_stream_last_sequence = 1
    page.body_pip_video_stream_last_sequence = 2

    ControlPage.flush_latest_rtsp_frames(page)

    assert page.video_stream_last_sequence == 3
    assert page.body_pip_video_stream_last_sequence == 3
    assert page.frames == [("body", main_image), ("body_pip", pip_image)]


def test_pip_video_frame_shows_overlay_only_after_first_frame():
    app = QApplication.instance() or QApplication([])
    page = _FakeVideoPage(b"")
    page.body_video_pip_view.hide()
    image = QImage(2, 2, QImage.Format_RGB888)

    ControlPage.update_rtsp_frame(page, "body_pip", image)

    assert app is not None
    assert page.body_video_pip_view.visible is True
    assert page.body_video_pip_view.pixmap() is not None


def test_pip_video_finished_hides_unconnected_overlay():
    page = _FakeVideoPage(b"")
    page.body_video_pip_view.show()

    ControlPage.body_pip_rtsp_worker_finished(page)

    assert page.body_video_pip_view.visible is False
    assert page.body_pip_video_stream_process is None


def test_body_pip_click_toggles_display_without_changing_source():
    page = _FakeVideoPage(b"")
    page.body_video_pip_topic = "back"
    page.body_pip_video_stream_process = object()
    page.body_video_display_swapped = False
    page.body_video_view = _FakeLabel()
    page.body_video_pip_view = _FakeLabel()
    main_pixmap = _FakePixmap()
    pip_pixmap = _FakePixmap()
    page.body_video_view.setPixmap(main_pixmap)
    page.body_video_pip_view.setPixmap(pip_pixmap)

    assert ControlPage.switch_body_video_focus(page) is True
    assert page.body_video_display_swapped is True
    assert page.body_video_view.pixmap() is pip_pixmap
    assert page.body_video_pip_view.pixmap() is main_pixmap

    assert ControlPage.switch_body_video_focus(page) is True
    assert page.body_video_display_swapped is False
    assert page.body_video_view.pixmap() is main_pixmap
    assert page.body_video_pip_view.pixmap() is pip_pixmap


def test_body_video_display_kind_follows_swap_state():
    page = _FakeVideoPage(b"")

    page.body_video_display_swapped = False
    assert ControlPage._video_display_kind(page, "body") == "body"
    assert ControlPage._video_display_kind(page, "body_pip") == "body_pip"
    assert ControlPage._video_display_kind(page, "l1") == "l1"

    page.body_video_display_swapped = True
    assert ControlPage._video_display_kind(page, "body") == "body_pip"
    assert ControlPage._video_display_kind(page, "body_pip") == "body"
    assert ControlPage._video_display_kind(page, "l1") == "l1"


def test_arc_remote_action_state_prefers_undock_when_docked():
    action, label, enabled, status = control_helpers.arc_remote_action_state(
        {"ARC_DOCK_STATE": "2", "ARC_DOCK_TEXT": "充电中", "ARC_DOCK_DETECTED": "1"}
    )

    assert (action, label, enabled) == ("undock", "出桩", True)
    assert status == "充电中"


def test_arc_remote_action_state_shows_dock_only_when_detected():
    detected = control_helpers.arc_remote_action_state({"ARC_DOCK_STATE": "5", "ARC_DOCK_TEXT": "被动", "ARC_DOCK_DETECTED": "1"})
    missing = control_helpers.arc_remote_action_state({"ARC_DOCK_STATE": "5", "ARC_DOCK_TEXT": "被动", "ARC_DOCK_DETECTED": "0"})

    assert detected == ("dock", "回充", True, "已识别充电桩")
    assert missing == ("", "回充", False, "被动，未识别充电桩")


def test_arc_remote_action_state_shows_dock_when_arc_app_is_standby():
    state = control_helpers.arc_remote_action_state(
        {
            "ARC_DOCK_STATE": "0",
            "ARC_DOCK_TEXT": "空闲",
            "ARC_STATE": "0",
            "ARC_TEXT": "待机",
            "ARC_DOCK_DETECTED": "0",
            "ARC_APP_ALG_STATUS": "StandBy",
            "ARC_APP_DOCK_STATUS": "StandBy",
        }
    )

    assert state == ("dock", "回充", True, "ARC 正常，未确认识别充电桩")


def test_arc_remote_action_state_uses_app_charging_status():
    action, label, enabled, status = control_helpers.arc_remote_action_state(
        {"ARC_DOCK_STATE": "0", "ARC_DOCK_TEXT": "空闲", "ARC_APP_ALG_STATUS": "Charging"}
    )

    assert (action, label, enabled, status) == ("undock", "出桩", True, "充电中")


def test_arc_remote_action_state_does_not_use_non_charging_dock_state_for_undock():
    state = control_helpers.arc_remote_action_state(
        {
            "ARC_DOCK_STATE": "1",
            "ARC_DOCK_TEXT": "已入桩",
            "ARC_STATE": "0",
            "ARC_TEXT": "待机",
            "ARC_DOCK_DETECTED": "1",
            "ARC_APP_ALG_STATUS": "StandBy",
            "ARC_APP_DOCK_STATUS": "StandBy",
        }
    )

    assert state == ("dock", "回充", True, "已识别充电桩")


def test_control_page_refreshes_arc_status_after_any_arc_task(monkeypatch):
    scheduled = []
    monkeypatch.setattr(
        "dog_remote_tool.ui.pages.control.page.QTimer.singleShot",
        lambda delay, callback: scheduled.append((delay, callback)),
    )
    page = type("Page", (), {"page_active": True, "refreshes": 0})()
    page.arc_controls_supported = lambda: True
    page.refresh_remote_arc_status = lambda: setattr(page, "refreshes", page.refreshes + 1) or True

    ControlPage.on_runner_task_finished(page, 1, 0, "执行：ARC 有图回充")

    assert [delay for delay, _callback in scheduled] == [100, 1500, 4000]
    for _delay, callback in scheduled:
        callback()
    assert page.refreshes == 3


def test_parse_key_value_lines_ignores_non_status_output():
    values = control_helpers.parse_key_value_lines("noise\nARC_DOCK_STATE=2\nARC_DOCK_TEXT=充电中\n")

    assert values == {"ARC_DOCK_STATE": "2", "ARC_DOCK_TEXT": "充电中"}


class _FakeTelemetryResetPage:
    def __init__(self, *, l1_values=None, l2_values=None):
        l1_values = l1_values or ("1", "2", "3", "4")
        l2_values = l2_values or ("1", "2", "3", "4")
        self.l1_linear_speed_label = _FakeLabel()
        self.l1_translate_speed_label = _FakeLabel()
        self.l1_angular_speed_label = _FakeLabel()
        self.l1_ctrl_mode_label = _FakeLabel()
        self.l2_current_forward_label = _FakeLabel()
        self.l2_current_strafe_label = _FakeLabel()
        self.l2_current_turn_label = _FakeLabel()
        self.l2_current_mode_label = _FakeLabel()
        for label, text in zip(
            (
                self.l1_linear_speed_label,
                self.l1_translate_speed_label,
                self.l1_angular_speed_label,
                self.l1_ctrl_mode_label,
            ),
            l1_values,
        ):
            label.setText(text)
        for label, text in zip(
            (
                self.l2_current_forward_label,
                self.l2_current_strafe_label,
                self.l2_current_turn_label,
                self.l2_current_mode_label,
            ),
            l2_values,
        ):
            label.setText(text)


class _FakeTargetSpeedLabelPage:
    def __init__(self, *, l1_values=None, l2_values=None, profile_key=None, l1_angular_speed=None, robot_angular_speed=None):
        l1_values = l1_values or ("old", "old", "old", "old")
        l2_values = l2_values or ("old", "old", "old", "old")
        self.profile_key = profile_key
        self.l1_sdk_limits = (1.0, 0.5, 2.0)
        self.l1_sdk_linear_speed_mps = 0.6
        if l1_angular_speed is not None:
            self.l1_sdk_angular_speed_radps = l1_angular_speed
        self.robot_sdk_linear_speed_mps = 0.6
        if robot_angular_speed is not None:
            self.robot_sdk_angular_speed_radps = robot_angular_speed
        self.l1_target_forward_label = _FakeLabel()
        self.l1_target_strafe_label = _FakeLabel()
        self.l1_target_turn_label = _FakeLabel()
        self.l1_sdk_limit_label = _FakeLabel()
        self.realtime_speed_slider = object()
        self.l2_target_forward_label = _FakeLabel()
        self.l2_target_strafe_label = _FakeLabel()
        self.l2_target_turn_label = _FakeLabel()
        self.l2_remote_limit_label = _FakeLabel()
        for label, text in zip(
            (
                self.l1_target_forward_label,
                self.l1_target_strafe_label,
                self.l1_target_turn_label,
                self.l1_sdk_limit_label,
            ),
            l1_values,
        ):
            label.setText(text)
        for label, text in zip(
            (
                self.l2_target_forward_label,
                self.l2_target_strafe_label,
                self.l2_target_turn_label,
                self.l2_remote_limit_label,
            ),
            l2_values,
        ):
            label.setText(text)

    def profile(self):
        return get_product(self.profile_key or "xg2_s100")

    def realtime_speed_axis_value(self):
        return 60


def test_control_telemetry_reset_returns_change_result():
    empty = object()

    assert ControlPage.reset_l1_telemetry(empty) is False
    assert ControlPage.reset_l2_telemetry(empty) is False

    page = _FakeTelemetryResetPage()

    assert ControlPage.reset_l1_telemetry(page) is True
    assert page.l1_linear_speed_label.text == "前后 --"
    assert page.l1_translate_speed_label.text == "横移 --"
    assert page.l1_angular_speed_label.text == "角速度 --"
    assert page.l1_ctrl_mode_label.text == "控制模式 --"
    assert ControlPage.reset_l1_telemetry(page) is False

    assert ControlPage.reset_l2_telemetry(page) is True
    assert page.l2_current_forward_label.text == "--"
    assert page.l2_current_strafe_label.text == "横移 --"
    assert page.l2_current_turn_label.text == "角速度 --"
    assert page.l2_current_mode_label.text == "来源 --"
    assert ControlPage.reset_l2_telemetry(page) is False


def test_control_target_speed_label_updates_return_change_result():
    empty = object()

    assert ControlPage.update_l1_target_speed_labels(empty) is False
    assert ControlPage.update_l2_target_speed_labels(empty) is False

    page = _FakeTargetSpeedLabelPage()

    assert ControlPage.update_l1_target_speed_labels(page) is True
    assert page.l1_target_forward_label.text == "前后 0.60 m/s"
    assert page.l1_target_strafe_label.text == "横移 0.50 m/s"
    assert page.l1_target_turn_label.text == "转向 0.80 rad/s"
    assert page.l1_sdk_limit_label.text == "上限 线速度 3.0 m/s / 角速度 3.0 rad/s"
    assert ControlPage.update_l1_target_speed_labels(page) is False

    assert ControlPage.update_l2_target_speed_labels(page) is True
    assert page.l2_target_forward_label.text == "前后 0.60 m/s"
    assert page.l2_target_strafe_label.text == "横移 0.60 m/s"
    assert page.l2_target_turn_label.text == "转向 0.80 rad/s"
    assert page.l2_remote_limit_label.text == "上限 线速度 3.0 m/s / 角速度 3.0 rad/s"
    assert ControlPage.update_l2_target_speed_labels(page) is False

    robot_page = _FakeTargetSpeedLabelPage(profile_key="zg3588")
    assert ControlPage.update_l2_target_speed_labels(robot_page) is True
    assert robot_page.l2_target_forward_label.text == "前后 0.60 m/s"
    assert robot_page.l2_target_strafe_label.text == "横移 0.60 m/s"
    assert robot_page.l2_target_turn_label.text == "转向 0.80 rad/s"
    assert robot_page.l2_remote_limit_label.text == "上限 线速度 3.0 m/s / 角速度 3.0 rad/s"

    default_robot_page = _FakeTargetSpeedLabelPage(profile_key="zg3588", robot_angular_speed=None)
    assert ControlPage.update_l2_target_speed_labels(default_robot_page) is True
    assert default_robot_page.l2_target_turn_label.text == "转向 0.80 rad/s"


def test_control_l2_body_telemetry_update_returns_change_result():
    empty = object()

    assert ControlPage.update_l2_body_telemetry(empty, {"linear_x": 1.0}) is False

    page = _FakeTelemetryResetPage(l2_values=("old", "old", "old", "old"))
    payload = {"linear_x": 1, "linear_y": None, "angular_z": "bad", "topic": "/odom"}

    assert ControlPage.update_l2_body_telemetry(page, payload) is True
    assert page.l2_current_forward_label.text == "1.00 m/s"
    assert page.l2_current_strafe_label.text == "横移 --"
    assert page.l2_current_turn_label.text == "角速度 --"
    assert page.l2_current_mode_label.text == "来源 /odom"
    assert ControlPage.update_l2_body_telemetry(page, payload) is False

    changed_topic = dict(payload, topic="/body")

    assert ControlPage.update_l2_body_telemetry(page, changed_topic) is True
    assert page.l2_current_mode_label.text == "来源 /body"


def test_control_l1_telemetry_update_returns_change_result():
    empty = object()

    assert ControlPage.update_l1_telemetry(empty, {"ctrl_mode": 3}) is False

    page = _FakeTelemetryResetPage(l1_values=("old", "old", "old", "old"))
    payload = {
        "body_velocity": [3, 4],
        "world_velocity": [0, 2],
        "body_gyro": [0, 0, 1.25],
        "ctrl_mode": 3,
    }

    assert ControlPage.update_l1_telemetry(page, payload) is True
    assert page.l1_linear_speed_label.text == "前后 2.00 m/s"
    assert page.l1_translate_speed_label.text == "横移 5.00 m/s"
    assert page.l1_angular_speed_label.text == "角速度 1.25 rad/s"
    assert page.l1_ctrl_mode_label.text == "控制模式 移动"
    assert ControlPage.update_l1_telemetry(page, payload) is False

    changed_mode = dict(payload, ctrl_mode=1)

    assert ControlPage.update_l1_telemetry(page, changed_mode) is True
    assert page.l1_ctrl_mode_label.text == "控制模式 站立"


def test_l1_sdk_setup_actions_mark_not_started_when_runner_rejects_start(monkeypatch):
    page = _FakeControlSpeedPage()
    monkeypatch.setattr(control, "l1_sdk_prepare_auto_command", lambda profile, path: CommandSpec("L1 SDK 准备", "prepare"))
    monkeypatch.setattr(control, "l1_sdk_deploy_command", lambda profile, local, path: CommandSpec("部署 L1 SDK", "deploy"))

    assert ControlPage.prepare_l1_sdk(page) is False
    assert page.l1_sdk_stream_status.text == "任务未启动"

    assert ControlPage.deploy_l1_sdk(page) is False
    assert page.l1_sdk_stream_status.text == "任务未启动"
    assert [command.title for command in page.commands] == ["L1 SDK 准备", "部署 L1 SDK"]
    assert page.label_statuses == [
        (page.l1_sdk_stream_status, "warn"),
        (page.l1_sdk_stream_status, "warn"),
    ]


def test_l1_sdk_basic_action_marks_not_started_when_runner_rejects_start(monkeypatch):
    page = _FakeControlSpeedPage()
    monkeypatch.setattr(
        control,
        "l1_sdk_basic_action_command",
        lambda profile, path, action: CommandSpec("L1 SDK 基础动作", f"action {action}"),
    )

    assert ControlPage.run_l1_sdk_action(page, "stand") is False
    assert page.l1_sdk_stream_status.text == "任务未启动"
    assert [command.title for command in page.commands] == ["L1 SDK 基础动作"]
    assert page.label_statuses == [(page.l1_sdk_stream_status, "warn")]


def test_l2_gamepad_action_marks_not_started_when_runner_rejects_start(monkeypatch):
    page = _FakeControlSpeedPage()
    page.profile = lambda: get_product("xg2_s100")
    events = []
    monkeypatch.setattr(
        control,
        "robot_sdk_posture_command",
        lambda profile, action: CommandSpec("robot_remote 站立", f"action {action}"),
    )
    page._log_control_event = lambda *args: events.append(args)

    assert ControlPage.run_l2_gamepad(page, "stand") is False
    assert page.gamepad_stream_status.text == "任务未启动"
    assert [command.title for command in page.commands] == ["robot_remote 站立"]
    assert page.label_statuses == [(page.gamepad_stream_status, "warn")]
    assert events == [("l2_action", {"action": "stand", "target": "robot@192.168.168.100"})]


def test_navigation_mc_mode_action_marks_not_started_when_runner_rejects_start(monkeypatch):
    page = _FakeControlSpeedPage()
    events = []
    monkeypatch.setattr(
        control,
        "navigation_mc_mode_command",
        lambda profile, mc_mode: CommandSpec("导航运控模式：对膝 WALK", f"mode {mc_mode}"),
    )
    page._log_control_event = lambda *args: events.append(args)

    assert ControlPage.run_navigation_mc_mode(page, 1) is False
    assert page.gamepad_stream_status.text == "任务未启动"
    assert [command.title for command in page.commands] == ["导航运控模式：对膝 WALK"]
    assert page.label_statuses == [(page.gamepad_stream_status, "warn")]
    assert events == [("navigation_mc_mode", {"mc_mode": 1, "target": "robot@192.168.1.2"})]


def test_robot_remote_probe_marks_not_started_when_runner_rejects_start(monkeypatch):
    page = _FakeControlSpeedPage()
    monkeypatch.setattr(control, "robot_remote_probe_command", lambda profile: CommandSpec("robot_remote 协议检查", "probe"))

    assert ControlPage.run_robot_remote_probe(page) is False
    assert page.gamepad_stream_status.text == "任务未启动"
    assert [command.title for command in page.commands] == ["robot_remote 协议检查"]
    assert page.label_statuses == [(page.gamepad_stream_status, "warn")]


def test_robot_remote_probe_marks_checking_when_runner_starts(monkeypatch):
    page = _FakeControlSpeedPage(started=True)
    monkeypatch.setattr(control, "robot_remote_probe_command", lambda profile: CommandSpec("robot_remote 协议检查", "probe"))

    assert ControlPage.run_robot_remote_probe(page) is True
    assert page.gamepad_stream_status.text == "检查中..."
    assert [command.title for command in page.commands] == ["robot_remote 协议检查"]
    assert page.label_statuses == [(page.gamepad_stream_status, "warn")]


def test_control_l1_stream_start_stop_and_toggle_return_results(monkeypatch):
    monkeypatch.setattr("dog_remote_tool.ui.pages.control.page.QProcess", _FakeStreamProcess)
    monkeypatch.setattr("dog_remote_tool.ui.pages.control.page.set_button_role", lambda button, text, role: button.setText(text))
    monkeypatch.setattr(control, "l1_control_profile", lambda profile: profile)
    monkeypatch.setattr(control, "l2_control_profile", lambda profile: None)
    monkeypatch.setattr(control, "l1_sdk_stream_command", lambda profile, path, speed, interval: f"l1 {path} {speed} {interval}")
    monkeypatch.setattr(control, "l1_sdk_prepare_auto_command", lambda profile, remote: CommandSpec("L1 SDK 准备", f"check {remote}"))
    monkeypatch.setattr(control, "l1_sdk_deploy_command", lambda profile, local, remote: CommandSpec("部署 L1 SDK", f"sync {local} {remote}"))
    page = _FakeControlStreamPage()

    assert ControlPage.start_l1_sdk_stream(page) is True
    assert page.l1_sdk_stream_process.state() == _FakeStreamProcess.Running
    assert page.l1_sdk_stream_process.arguments[0] == "-lc"
    assert "自动同步远端 SDK" not in page.l1_sdk_stream_process.arguments[1]
    assert "if check /home/robot/sdk" in page.l1_sdk_stream_process.arguments[1]
    assert "sync " in page.l1_sdk_stream_process.arguments[1]
    assert "l1 /home/robot/sdk 100 20" in page.l1_sdk_stream_process.arguments[1]
    assert page.l1_sdk_stream_timer.started == 1
    assert page.l1_sdk_stream_status.text == "连接中..."
    assert page.l1_start_stream_btn.text == "停止遥控"
    assert page.events[-1] == ("l1_stream_start", {"target": "robot@192.168.1.2"})

    assert ControlPage.toggle_l1_sdk_stream(page) is True
    assert page.l1_sdk_stream_process is None
    assert page.l1_sdk_stream_timer.stopped >= 1
    assert page.l1_sdk_stream_status.text == "未连接"
    assert page.stopped_payloads[-1] == (({"cmd": "neutral"}, {"cmd": "quit"}), False)

    inactive = _FakeControlStreamPage(active=False)

    assert ControlPage.start_l1_sdk_stream(inactive) is False
    assert inactive.l1_sdk_stream_process is None
    assert ControlPage.stop_l1_sdk_stream(inactive) is False


def test_l1_sdk_stream_routes_sdk_noise_to_technical_log():
    page = _FakeControlStreamPage()
    process = _FakeStreamProcess(
        output=(
            b"sdk_preferred=zsl-1\n"
            b'{"type":"log","message":"client bind success"}\n'
            b'{"type":"ready","selected":{"model":"zsl-1"}}\n'
        )
    )
    page.l1_sdk_stream_process = process
    page.l1_sdk_stream_request_id = 3
    page.l1_sdk_stream_buffer = ""

    ControlPage.read_l1_sdk_stream_output(page, process, 3)

    assert page.runner.output.lines == ["[L1 遥控] 遥控已连接。\n"]
    assert page.runner.technical_output.lines == [
        "[L1 遥控] sdk_preferred=zsl-1\n",
        "[L1 遥控] client bind success\n",
    ]


def test_control_l2_gamepad_stream_start_stop_and_toggle_return_results(monkeypatch):
    monkeypatch.setattr("dog_remote_tool.ui.pages.control.page.QProcess", _FakeStreamProcess)
    monkeypatch.setattr("dog_remote_tool.ui.pages.control.page.set_button_role", lambda button, text, role: button.setText(text))
    monkeypatch.setattr(control, "l1_control_profile", lambda profile: None)
    monkeypatch.setattr(control, "l2_control_profile", lambda profile: profile)
    monkeypatch.setattr(control, "body_realtime_stream_command", lambda profile, axis, interval: f"body {axis} {interval}")
    page = _FakeControlStreamPage()

    assert ControlPage.start_gamepad_stream(page) is True
    assert page.gamepad_stream_process.state() == _FakeStreamProcess.Running
    assert page.gamepad_stream_process.arguments == ["-lc", "body 70 20"]
    assert page.gamepad_stream_timer.started == 1
    assert page.gamepad_stream_status.text == "连接中..."
    assert page.start_stream_btn.text == "停止遥控"
    assert page.events[-1] == ("l2_stream_start", {"target": "robot@192.168.1.2", "interval_ms": 20})

    assert ControlPage.toggle_gamepad_stream(page) is True
    assert page.gamepad_stream_process is None
    assert page.gamepad_stream_timer.stopped >= 1
    assert page.gamepad_stream_status.text == "未连接"
    assert page.stopped_payloads[-1] == (({"cmd": "neutral"}, {"cmd": "quit"}), False)

    inactive = _FakeControlStreamPage(active=False)

    assert ControlPage.start_gamepad_stream(inactive) is False
    assert inactive.gamepad_stream_process is None
    assert ControlPage.stop_gamepad_stream(inactive) is False


def test_control_json_stream_stop_is_non_blocking(monkeypatch):
    scheduled = []
    monkeypatch.setattr(
        "dog_remote_tool.ui.pages.control.page.QTimer",
        type("Timer", (), {"singleShot": staticmethod(lambda delay, callback: scheduled.append((delay, callback)))}),
    )
    page = _FakeControlStreamPage()
    process = _FakeStreamProcess()
    process.start()

    ControlPage._stop_json_stream_process(page, process, ({"cmd": "neutral"}, {"cmd": "quit"}))

    assert process.wait_calls == []
    assert process.closed_write_channel is True
    assert process.terminate_calls == 1
    assert len(process.writes) == 2
    assert [delay for delay, _callback in scheduled] == [700, 1500]


def test_control_json_stream_stop_can_wait_for_exit(monkeypatch):
    stopped = []
    monkeypatch.setattr(
        "dog_remote_tool.ui.pages.control.page.stop_process_safely",
        lambda process, timeout_ms=1000: stopped.append((process, timeout_ms)) or setattr(process, "state_value", _FakeStreamProcess.NotRunning),
    )
    page = _FakeControlStreamPage()
    process = _FakeStreamProcess()
    process.start()

    ControlPage._stop_json_stream_process(
        page,
        process,
        ({"cmd": "neutral"}, {"cmd": "quit"}),
        timeout_ms=2500,
        wait_for_exit=True,
    )

    assert process.closed_write_channel is True
    assert len(process.writes) == 2
    assert process.terminate_calls == 0
    assert stopped == [(process, 2500)]


def test_control_shutdown_waits_for_keyboard_stream_exit(monkeypatch):
    monkeypatch.setattr("dog_remote_tool.ui.pages.control.page.set_button_role", lambda button, text, role: button.setText(text))
    page = _FakeControlStreamPage()
    page.gamepad_stream_process = _FakeStreamProcess()
    page.gamepad_stream_process.start()
    page.l1_sdk_stream_process = _FakeStreamProcess()
    page.l1_sdk_stream_process.start()

    ControlPage.shutdown_processes(page)

    assert page.page_active is False
    assert page.arc_status_slot.stopped == 1
    assert page.gamepad_stream_process is None
    assert page.l1_sdk_stream_process is None
    assert (({"cmd": "neutral"}, {"cmd": "quit"}), True) in page.stopped_payloads
    assert page.stopped_payloads.count((({"cmd": "neutral"}, {"cmd": "quit"}), True)) == 2


def test_control_deactivate_keeps_keyboard_stream_when_switching_to_mapping():
    page = _FakeControlStreamPage()
    page.gamepad_stream_process = _FakeStreamProcess()
    page.gamepad_stream_process.start()
    page.l2_telemetry_process = _FakeStreamProcess()
    page.l2_telemetry_process.start()

    ControlPage.deactivate_page(page, next_page_title="建图")

    assert page.page_active is False
    assert page.gamepad_stream_process is not None
    assert page.gamepad_stream_process.state() == _FakeStreamProcess.Running
    assert page.gamepad_stream_process.writes[-1] == b'{"cmd":"neutral"}\n'
    assert page.stopped_payloads == []
    assert page.l2_telemetry_process is None
    assert page.video_stops == 1
    assert page.low_load_states == []
    assert "[遥控] 切换到建图页面，键盘遥控保持开启。\n" in page.runner.output.lines


def test_control_deactivate_releases_keyboard_stream_when_switching_to_navigation(monkeypatch):
    monkeypatch.setattr("dog_remote_tool.ui.pages.control.page.set_button_role", lambda button, text, role: button.setText(text))
    page = _FakeControlStreamPage()
    page.gamepad_stream_process = _FakeStreamProcess()
    page.gamepad_stream_process.start()

    ControlPage.deactivate_page(page, next_page_title="导航")

    assert page.gamepad_stream_process is None
    assert page.stopped_payloads[-1] == (({"cmd": "neutral"}, {"cmd": "quit"}), False)
    assert page.low_load_states[-1] is False
    assert "[遥控] 切换到导航页面，已停止键盘遥控并释放控制权。\n" in page.runner.output.lines


def test_control_deactivate_keeps_keyboard_stream_when_switching_to_bag():
    page = _FakeControlStreamPage()
    page.gamepad_stream_process = _FakeStreamProcess()
    page.gamepad_stream_process.start()
    page.l2_telemetry_process = _FakeStreamProcess()
    page.l2_telemetry_process.start()

    ControlPage.deactivate_page(page, next_page_title="录包")

    assert page.page_active is False
    assert page.gamepad_stream_process is not None
    assert page.gamepad_stream_process.state() == _FakeStreamProcess.Running
    assert page.gamepad_stream_process.writes[-1] == b'{"cmd":"neutral"}\n'
    assert page.gamepad_pressed_keys == set()
    assert page.stopped_payloads == []
    assert page.l2_telemetry_process is None
    assert page.video_stops == 1
    assert page.low_load_states == []
    assert "[遥控] 切换到录包页面，键盘遥控保持开启。\n" in page.runner.output.lines


def test_control_deactivate_stops_keyboard_stream_on_other_pages(monkeypatch):
    monkeypatch.setattr("dog_remote_tool.ui.pages.control.page.set_button_role", lambda button, text, role: button.setText(text))
    page = _FakeControlStreamPage()
    page.gamepad_stream_process = _FakeStreamProcess()
    page.gamepad_stream_process.start()

    ControlPage.deactivate_page(page, next_page_title="定位")

    assert page.gamepad_stream_process is None
    assert page.stopped_payloads[-1] == (({"cmd": "neutral"}, {"cmd": "quit"}), False)
    assert page.low_load_states[-1] is False


def test_control_l2_telemetry_stream_start_stop_returns_results(monkeypatch):
    monkeypatch.setattr("dog_remote_tool.ui.pages.control.page.QProcess", _FakeStreamProcess)
    monkeypatch.setattr("dog_remote_tool.ui.pages.control.page.stop_process_safely", lambda process: setattr(process, "state_value", _FakeStreamProcess.NotRunning) if process else None)
    monkeypatch.setattr(control, "robot_remote_control_profile", lambda profile: profile)
    monkeypatch.setattr(control, "robot_sdk_body_telemetry_stream_command", lambda profile, interval: f"telemetry {interval}")
    page = _FakeControlStreamPage()

    assert ControlPage.start_l2_telemetry_stream(page) is True
    assert page.l2_telemetry_process.state() == _FakeStreamProcess.Running
    assert page.l2_telemetry_process.arguments == ["-lc", "telemetry 500"]
    assert page.l2_current_mode_label.text == "来源 连接中..."

    assert ControlPage.start_l2_telemetry_stream(page) is False

    assert ControlPage.stop_l2_telemetry_stream(page) is True
    assert page.l2_telemetry_process is None
    assert page.l2_telemetry_buffer == ""
    assert page.l2_telemetry_ready is False
    assert page.l2_current_forward_label.text == "--"
    assert page.l2_current_strafe_label.text == "横移 --"
    assert page.l2_current_turn_label.text == "角速度 --"
    assert page.l2_current_mode_label.text == "来源 --"

    inactive = _FakeControlStreamPage(active=False)

    assert ControlPage.start_l2_telemetry_stream(inactive) is False
    assert ControlPage.stop_l2_telemetry_stream(inactive) is False


def test_control_stream_finished_drains_tail_output(monkeypatch):
    monkeypatch.setattr("dog_remote_tool.ui.pages.control.page.set_button_role", lambda button, text, role: button.setText(text))

    l1 = _FakeControlStreamPage()
    l1.l1_sdk_stream_request_id = 4
    l1.l1_sdk_stream_buffer = ""
    l1_process = _FakeStreamProcess(output=b'{"type":"error","message":"tail l1"}')
    l1.l1_sdk_stream_process = l1_process

    ControlPage.l1_sdk_stream_finished(l1, l1_process, request_id=4, code=1, _status=None)

    assert "[L1 遥控] 错误：tail l1\n" in l1.runner.output.lines
    assert l1.l1_sdk_stream_process is None
    assert l1_process.deleted is True

    gamepad = _FakeControlStreamPage()
    gamepad.gamepad_stream_request_id = 5
    gamepad.gamepad_stream_buffer = ""
    gamepad_process = _FakeStreamProcess(output=b'{"type":"error","message":"tail l2"}')
    gamepad.gamepad_stream_process = gamepad_process

    ControlPage.gamepad_stream_finished(gamepad, gamepad_process, request_id=5, code=1, _status=None)

    assert "[实时遥控] 遥控连接失败：tail l2\n" in gamepad.runner.output.lines
    assert gamepad.gamepad_stream_process is None
    assert gamepad_process.deleted is True

    telemetry = _FakeControlStreamPage()
    telemetry.l2_telemetry_request_id = 6
    telemetry.l2_telemetry_buffer = ""
    telemetry_process = _FakeStreamProcess(output=b'{"type":"error","message":"tail telemetry"}')
    telemetry.l2_telemetry_process = telemetry_process

    ControlPage.l2_telemetry_finished(telemetry, telemetry_process, request_id=6, code=2, _status=None)

    assert "[本体速度] 速度读取失败：tail telemetry\n" in telemetry.runner.output.lines
    assert telemetry.l2_telemetry_process is None
    assert telemetry_process.deleted is True


def test_control_gamepad_neutral_returns_write_result():
    disconnected = _FakeControlStreamPage()

    assert ControlPage.send_gamepad_neutral(disconnected) is False
    assert disconnected.gamepad_pressed_keys == set()
    assert disconnected.gamepad_stream_last_vector is None
    assert disconnected.events == []

    process = _FakeStreamProcess()
    process.start()
    page = _FakeControlStreamPage()
    page.gamepad_stream_process = process

    assert ControlPage.send_gamepad_neutral(page) is True
    assert page.gamepad_pressed_keys == set()
    assert page.gamepad_stream_last_vector is None
    assert process.writes == [b'{"cmd":"neutral"}\n']
    assert page.events == [("l2_stream_command", {"cmd": "neutral"})]


def test_robot_remote_default_angular_speed_is_reduced_in_stream_payload():
    process = _FakeStreamProcess()
    process.start()
    page = _FakeControlStreamPage()
    page.gamepad_stream_process = process
    page.gamepad_stream_ready = True
    page.gamepad_pressed_keys = {"a"}
    page.gamepad_stream_last_vector = None

    ControlPage.send_gamepad_stream_target(page)

    assert process.writes == [
        b'{"cmd":"set","forward":0.0,"strafe":0.0,"turn":-0.8,"pitch":0.0,'
        b'"linear_speed":0.6,"angular_speed":0.8,"linear_limit_mps":3.0,"angular_limit_radps":3.0}\n'
    ]
    assert page.events == [
        (
            "l2_stream_command",
            {
                "cmd": "set",
                "forward": 0.0,
                "strafe": 0.0,
                "turn": -0.8,
                "pitch": 0.0,
                "linear_speed": 0.6,
                "angular_speed": 0.8,
                "linear_limit_mps": 3.0,
                "angular_limit_radps": 3.0,
            },
        )
    ]


def test_l1_default_angular_speed_is_reduced_in_stream_payload():
    process = _FakeStreamProcess()
    process.start()
    page = _FakeControlStreamPage()
    page.l1_sdk_stream_process = process
    page.l1_sdk_stream_ready = True
    page.l1_pressed_keys = {"a"}
    page.l1_sdk_last_vector = None

    ControlPage.send_l1_sdk_stream_target(page)

    assert process.writes == [
        b'{"cmd":"set","forward":0.0,"strafe":0.0,"turn":0.8,'
        b'"linear_speed":0.6,"angular_speed":0.8,"linear_limit_mps":3.0,"angular_limit_radps":3.0}\n'
    ]
    assert page.events == [
        (
            "l1_stream_command",
            {
                "cmd": "set",
                "forward": 0.0,
                "strafe": 0.0,
                "turn": 0.8,
                "linear_speed": 0.6,
                "angular_speed": 0.8,
                "linear_limit_mps": 3.0,
                "angular_limit_radps": 3.0,
            },
        )
    ]


def test_l1_velocity_vector_maps_linear_and_angular_speed():
    assert control_helpers.l1_velocity_vector({"w", "q", "a"}, 0.6, 1.0) == (0.6, 0.6, 1.0)
    assert control_helpers.l1_velocity_vector({"s", "e", "d"}, 0.6, 1.0) == (-0.6, -0.6, -1.0)
    assert control_helpers.l1_velocity_vector({"w", "s", "a", "d", "q", "e"}, 0.6, 1.0) == (0.0, 0.0, 0.0)


def test_l2_gamepad_vector_normal_and_inplace_modes():
    assert control_helpers.l2_gamepad_vector({"w", "q", "a"}, 60, False) == (-60, -60, -60, 0)
    assert control_helpers.l2_gamepad_vector({"s", "e", "d"}, 60, False) == (60, 60, 60, 0)
    assert control_helpers.l2_gamepad_vector({"w", "a"}, 60, True) == (0, 0, -60, -60)
    assert control_helpers.l2_gamepad_vector({"s", "d"}, 60, True) == (0, 0, 60, 60)


def test_robot_sdk_velocity_vector_maps_keyboard_axes():
    assert control_helpers.robot_sdk_velocity_vector({"w", "q", "a"}, 0.6, 1.0) == (-0.6, -0.6, -1.0, 0.0)
    assert control_helpers.robot_sdk_velocity_vector({"s", "e", "d"}, 0.6, 1.0) == (0.6, 0.6, 1.0, 0.0)
    assert control_helpers.robot_sdk_velocity_vector({"w", "s", "a", "d", "q", "e"}, 0.6, 1.0) == (0.0, 0.0, 0.0, 0.0)


def test_stream_set_payload_uses_common_axis_names():
    assert control_helpers.stream_set_payload((35, -10, 5)) == {
        "cmd": "set",
        "forward": 35,
        "strafe": -10,
        "turn": 5,
    }
    assert control_helpers.stream_set_payload((-60, 0, 20, 0)) == {
        "cmd": "set",
        "forward": -60,
        "strafe": 0,
        "turn": 20,
        "pitch": 0,
    }
    assert control_helpers.stream_set_payload(
        (-0.6, 0, -1.0, 0),
        linear_speed=0.6,
        angular_speed=1.0,
        linear_limit_mps=3.0,
        angular_limit_radps=3.0,
    ) == {
        "cmd": "set",
        "forward": -0.6,
        "strafe": 0,
        "turn": -1.0,
        "pitch": 0,
        "linear_speed": 0.6,
        "angular_speed": 1.0,
        "linear_limit_mps": 3.0,
        "angular_limit_radps": 3.0,
    }
    try:
        control_helpers.stream_set_payload((1, 2))
    except ValueError as exc:
        assert "实时遥控向量" in str(exc)
    else:
        raise AssertionError("invalid stream vector length should fail")


def test_control_video_source_options_match_product_family():
    l1_sources = control_helpers.video_source_options("xg3588")
    l2_sources = control_helpers.video_source_options("xg2_s100")
    zg_sources = control_helpers.video_source_options("zg_lidar_nx")
    zg_surround_sources = control_helpers.video_source_options("zg_surround_s100")
    fallback_sources = control_helpers.video_source_options("unknown")

    assert l1_sources == [("本体相机", "front")]
    assert l2_sources[0] == ("前双目", "front")
    assert ("左鱼眼", "left") in l2_sources
    assert zg_sources == [
        ("前视相机", "front"),
        ("后视相机", "back"),
    ]
    assert ("前双目", "front") in zg_surround_sources
    assert all("/image" not in source for _label, source in zg_sources + fallback_sources)
    assert fallback_sources == [("前视相机", "front")]


def test_keyboard_mapping_helpers_share_direction_and_action_rules():
    assert control_helpers.direction_key(ord("W")) == "w"
    assert control_helpers.direction_key(ord("E")) == "e"
    assert control_helpers.direction_key(ord("Z")) == ""
    assert control_helpers.l2_action_key(ord("4")) == "head"
    assert control_helpers.l2_action_key(ord("9")) == ""
    assert control_helpers.l1_action_key(ord("2")) == "lie"
    assert control_helpers.l1_action_key(ord("3")) == "passive"
    assert control_helpers.l1_action_key(ord("4")) == ""

    assert control_helpers.l2_action_payload("head") == ({"cmd": "head", "ensure_stand": True}, True)
    assert control_helpers.l2_action_payload("crawl") == ({"cmd": "crawl", "ensure_stand": True}, False)
    assert control_helpers.l2_action_payload("neutral") == ({"cmd": "neutral"}, None)


def test_stream_log_helpers_format_status_lines_and_modes():
    assert control_helpers.l1_stream_ready_log({"selected": {"model": "M1", "module": "SDK"}}) == "[L1 遥控] 遥控已连接。\n"
    assert control_helpers.l1_stream_log_line({"type": "result", "cmd": "stand", "ret": 0}) == "[L1 遥控] 动作完成：站立\n"
    assert control_helpers.l1_stream_log_line({"type": "result", "cmd": "lie", "ret": 0}) == "[L1 遥控] 动作完成：低姿态\n"
    assert control_helpers.l1_stream_log_line({"type": "result", "cmd": "passive", "ret": 0}) == "[L1 遥控] 动作完成：阻尼趴下\n"
    assert control_helpers.l1_stream_log_line({"type": "move", "ret": 3}) == "[L1 遥控] 移动指令未成功，请查看详细日志。\n"
    assert control_helpers.l1_stream_log_line({"type": "move", "ret": 0}) == ""

    assert control_helpers.l2_stream_log_line({"type": "ready", "host": "192.168.234.1"}) == "[实时遥控] 键盘遥控已就绪。\n"
    assert control_helpers.l2_stream_log_line({"type": "ready", "protocol": "robot_remote"}) == "[实时遥控] 键盘遥控已就绪。\n"
    assert control_helpers.l2_stream_log_line({"type": "result", "cmd": "head"}) == "[实时遥控] 动作完成：head\n"
    assert control_helpers.l2_stream_result_inplace_mode({"type": "result", "cmd": "head"}) is True
    assert control_helpers.l2_stream_result_inplace_mode({"type": "result", "cmd": "stand"}) is False
    assert control_helpers.l2_stream_result_inplace_mode({"type": "ready"}) is None


def test_l2_telemetry_runtime_messages_hide_exit_codes():
    assert (
        control_telemetry._user_telemetry_message("telemetry stream exited code=1; retrying in 2.0s")
        == "速度读取中断，正在重试。"
    )
    assert (
        control_telemetry._user_telemetry_message("telemetry stream exited too often code=1", error=True)
        == "速度读取中断，请查看详细日志。"
    )
    assert control_telemetry._user_telemetry_message("速度正常") == "速度正常"


def test_split_control_stream_lines_handles_concatenated_json():
    assert control_helpers.split_control_stream_lines('log\n{"a":1}{"b":2}\n\n') == ["log", '{"a":1}', '{"b":2}']
    assert control_helpers.split_control_stream_lines('{"message":"a}{b"}{"type":"ready"}\nplain }{ log\n') == [
        '{"message":"a}{b"}',
        '{"type":"ready"}',
        "plain }{ log",
    ]


def test_consume_control_json_stream_parses_payloads_and_raw_lines():
    remaining, events = control_helpers.consume_control_json_stream("", 'plain\n{"type":"ready"}\n[1]\n')

    assert remaining == ""
    assert events == [
        (None, "plain"),
        ({"type": "ready"}, '{"type":"ready"}'),
        (None, "[1]"),
    ]


def test_consume_control_json_stream_keeps_partial_line():
    remaining, events = control_helpers.consume_control_json_stream("", '{"type":"ready"}\n{"type"', keep_partial=True)

    assert remaining == '{"type"'
    assert events == [({"type": "ready"}, '{"type":"ready"}')]

    remaining, events = control_helpers.consume_control_json_stream(remaining, ':"telemetry"}\n', keep_partial=True)
    assert remaining == ""
    assert events == [({"type": "telemetry"}, '{"type":"telemetry"}')]


def test_consume_control_json_stream_emits_complete_tail_json_without_newline():
    remaining, events = control_helpers.consume_control_json_stream("", '{"type":"ready"}', keep_partial=True)

    assert remaining == ""
    assert events == [({"type": "ready"}, '{"type":"ready"}')]

    remaining, events = control_helpers.consume_control_json_stream("", '{"type":"ready"}{"type"', keep_partial=True)
    assert remaining == '{"type"'
    assert events == [({"type": "ready"}, '{"type":"ready"}')]


def test_telemetry_text_helpers():
    assert control_helpers.l1_telemetry_text(
        {
            "body_velocity": [3, 4],
            "world_velocity": [0, 2],
            "body_gyro": [0, 0, 1.25],
            "ctrl_mode": 3,
        }
    ) == (
        "前后 2.00 m/s",
        "横移 5.00 m/s",
        "角速度 1.25 rad/s",
        "控制模式 移动",
    )

    assert control_helpers.l2_telemetry_text({"linear_x": 1, "linear_y": None, "angular_z": "bad", "topic": "/odom"}) == (
        "1.00 m/s",
        "横移 --",
        "角速度 --",
        "来源 /odom",
    )
    assert control_helpers.l2_telemetry_text({"linear_x": 0.03, "linear_y": -0.03, "angular_z": 0.03}) == (
        "0.00 m/s",
        "横移 0.00 m/s",
        "角速度 0.00 rad/s",
        "来源 --",
    )


def test_stepped_slider_value_rounds_and_clamps():
    assert control_helpers.stepped_slider_value(37, 5, 5, 5, 100) == 40
    assert control_helpers.stepped_slider_value(98, 5, 5, 5, 100) == 100
    assert control_helpers.stepped_slider_value(7, -5, 5, 5, 100) == 5
