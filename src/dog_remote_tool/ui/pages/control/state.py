from __future__ import annotations

from dog_remote_tool.modules import control
from dog_remote_tool.ui.pages.control import helpers as control_helpers
from dog_remote_tool.ui.process_utils import ProcessSlot


def _control_page_module():
    from dog_remote_tool.ui.pages.control import page as control_page

    return control_page


class ControlStateMixin:
    def _init_control_state(self) -> None:
        control_page = _control_page_module()
        self.controls_panel.hide()
        self.page_active = False
        self.gamepad_stream_process = None
        self.gamepad_pressed_keys: set[str] = set()
        self.gamepad_stream_ready = False
        self.gamepad_stream_buffer = ""
        self.gamepad_stream_request_id = 0
        self.gamepad_inplace_mode = False
        self.gamepad_stream_last_vector: tuple[int | float, int | float, int | float, int | float] | None = None
        self.robot_sdk_linear_speed_mps = control_helpers.LINEAR_SPEED_DEFAULT_MPS
        self.robot_sdk_angular_speed_radps = control_helpers.ROBOT_REMOTE_ANGULAR_SPEED_DEFAULT_RADPS
        self.l2_telemetry_process = None
        self.l2_telemetry_buffer = ""
        self.l2_telemetry_ready = False
        self.l2_telemetry_request_id = 0
        self.arc_status_slot = ProcessSlot(self, reserve_runner=False)
        self.arc_action = ""
        self.runner.task_finished_detail.connect(self.on_runner_task_finished)
        self.video_stream_process = None
        self.video_stream_thread = None
        self.video_stream_worker = None
        self.video_stream_last_sequence = 0
        self.video_stream_request_id = 0
        self.video_stream_buffer = ""
        self.video_stream_kind = ""
        self.body_pip_video_stream_process = None
        self.body_pip_video_stream_thread = None
        self.body_pip_video_stream_worker = None
        self.body_pip_video_stream_last_sequence = 0
        self.body_pip_video_stream_request_id = 0
        self.body_pip_video_stream_buffer = ""
        self.body_video_pip_topic = ""
        self.body_video_pip_label = "后视"
        self.body_video_display_swapped = False
        self.rtsp_frame_timer = control_page.QTimer(self)
        self.rtsp_frame_timer.setInterval(16)
        self.rtsp_frame_timer.timeout.connect(self.flush_latest_rtsp_frames)
        self.gamepad_stream_timer = control_page.QTimer(self)
        self.gamepad_stream_timer.setInterval(20)
        self.gamepad_stream_timer.timeout.connect(self.send_gamepad_stream_target)
        self.l1_sdk_stream_process = None
        self.l1_sdk_stream_buffer = ""
        self.l1_sdk_stream_request_id = 0
        self.l1_pressed_keys: set[str] = set()
        self.l1_sdk_stream_ready = False
        self.l1_sdk_last_vector: tuple[int | float, int | float, int | float] | None = None
        self.l1_sdk_linear_speed_mps = control_helpers.LINEAR_SPEED_DEFAULT_MPS
        self.l1_sdk_angular_speed_radps = control_helpers.ANGULAR_SPEED_DEFAULT_RADPS
        self.l1_sdk_limits = (
            float(control.L1_SDK_MODES["zsl-1w"]["vx_max"]),
            float(control.L1_SDK_MODES["zsl-1w"]["vy_max"]),
            float(control.L1_SDK_MODES["zsl-1w"]["yaw_max"]),
        )
        self.l1_sdk_stream_timer = control_page.QTimer(self)
        self.l1_sdk_stream_timer.setInterval(40)
        self.l1_sdk_stream_timer.timeout.connect(self.send_l1_sdk_stream_target)
        self.setFocusPolicy(control_page.Qt.StrongFocus)
        app = control_page.QApplication.instance()
        if app is not None:
            app.installEventFilter(self)
