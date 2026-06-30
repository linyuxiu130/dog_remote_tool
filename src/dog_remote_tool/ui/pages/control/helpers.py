from __future__ import annotations

from dog_remote_tool.core.parsers import parse_key_values
from dog_remote_tool.ui.pages.control.arc_helpers import (
    ARC_APP_CHARGING_STATES,
    ARC_APP_READY_STATES,
    ARC_CHARGING_DOCK_STATES,
    ARC_READY_STATES,
    arc_remote_action_state,
)
from dog_remote_tool.ui.pages.control.input_helpers import (
    ANGULAR_SPEED_DEFAULT_RADPS,
    ANGULAR_SPEED_MAX_RADPS,
    ANGULAR_SPEED_MIN_RADPS,
    ANGULAR_SPEED_STEP_RADPS,
    DIRECTION_KEYS,
    L1_ACTION_KEYS,
    L2_ACTION_KEYS,
    LINEAR_SPEED_DEFAULT_MPS,
    LINEAR_SPEED_MAX_MPS,
    LINEAR_SPEED_MIN_MPS,
    LINEAR_SPEED_STEP_MPS,
    ROBOT_REMOTE_ANGULAR_SPEED_DEFAULT_RADPS,
    clamp_stream_speed,
    direction_key,
    l1_action_key,
    l1_velocity_vector,
    l2_action_key,
    l2_action_payload,
    l2_gamepad_vector,
    robot_sdk_velocity_vector,
    stepped_stream_speed,
    stream_set_payload,
)
from dog_remote_tool.ui.pages.control.speed_helpers import stepped_slider_value
from dog_remote_tool.ui.pages.control.stream_helpers import (
    L1_ACTION_LABELS,
    consume_control_json_stream,
    l1_stream_log_line,
    l1_stream_ready_log,
    l2_stream_log_line,
    l2_stream_result_inplace_mode,
    split_control_stream_line,
    split_control_stream_lines,
)
from dog_remote_tool.ui.pages.control.telemetry_helpers import l1_telemetry_text, l2_telemetry_text
from dog_remote_tool.ui.pages.control.video_sources import VIDEO_SOURCE_OPTIONS, video_source_options


parse_key_value_lines = parse_key_values


__all__ = [
    "ARC_APP_CHARGING_STATES",
    "ARC_APP_READY_STATES",
    "ARC_CHARGING_DOCK_STATES",
    "ARC_READY_STATES",
    "ANGULAR_SPEED_DEFAULT_RADPS",
    "ANGULAR_SPEED_MAX_RADPS",
    "ANGULAR_SPEED_MIN_RADPS",
    "ANGULAR_SPEED_STEP_RADPS",
    "DIRECTION_KEYS",
    "L1_ACTION_KEYS",
    "L1_ACTION_LABELS",
    "L2_ACTION_KEYS",
    "LINEAR_SPEED_DEFAULT_MPS",
    "LINEAR_SPEED_MAX_MPS",
    "LINEAR_SPEED_MIN_MPS",
    "LINEAR_SPEED_STEP_MPS",
    "ROBOT_REMOTE_ANGULAR_SPEED_DEFAULT_RADPS",
    "VIDEO_SOURCE_OPTIONS",
    "arc_remote_action_state",
    "clamp_stream_speed",
    "consume_control_json_stream",
    "direction_key",
    "l1_action_key",
    "l1_stream_log_line",
    "l1_stream_ready_log",
    "l1_telemetry_text",
    "l1_velocity_vector",
    "l2_action_key",
    "l2_action_payload",
    "l2_gamepad_vector",
    "l2_stream_log_line",
    "l2_stream_result_inplace_mode",
    "l2_telemetry_text",
    "parse_key_value_lines",
    "robot_sdk_velocity_vector",
    "split_control_stream_line",
    "split_control_stream_lines",
    "stepped_slider_value",
    "stepped_stream_speed",
    "stream_set_payload",
    "video_source_options",
]
