from dog_remote_tool.ui.status_styles import style_for_state
from dog_remote_tool.ui import map_history_helpers
from dog_remote_tool.ui import mapping_status_summary as _mapping_status_summary


MAPPING_OPERATION_STYLES = {
    "idle": ("#ffffff", "#46566b", "#e3eaf3"),
    "running": ("#eef7ff", "#245b84", "#c7e2f8"),
    "saving": ("#fff8ed", "#8b4513", "#f5dec0"),
    "done": ("#edf8f0", "#22623a", "#c9ead2"),
    "blocked": ("#fff1f2", "#9f2d2d", "#f2c7c7"),
}
MAPPING_STATUS_STYLES = {
    "mapping": ("#edf8f0", "#22623a", "#c9ead2"),
    "ready": ("#eef7ff", "#245b84", "#c7e2f8"),
    "starting": ("#fff8ed", "#8b4513", "#f5dec0"),
    "saving": ("#fff8ed", "#8b4513", "#f5dec0"),
    "success": ("#edf8f0", "#22623a", "#c9ead2"),
    "stopped": ("#ffffff", "#46566b", "#e3eaf3"),
    "error": ("#fff1f2", "#9f2d2d", "#f2c7c7"),
    "unknown": ("#fff1f2", "#9f2d2d", "#f2c7c7"),
}
format_history_map_size = map_history_helpers.format_history_map_size
history_map_display = map_history_helpers.history_map_display
history_map_label_prefix = map_history_helpers.history_map_label_prefix
history_map_timestamp_label = map_history_helpers.history_map_timestamp_label
compact_history_map_label = map_history_helpers.compact_history_map_label
is_history_map_pgm = map_history_helpers.is_history_map_pgm
format_disk_detail = map_history_helpers.format_disk_detail
parse_history_map_entries = map_history_helpers.parse_history_map_entries
parse_history_map_disk_detail = map_history_helpers.parse_history_map_disk_detail
local_map_preview_dir = map_history_helpers.local_map_preview_dir
local_map_pull_target_dir = map_history_helpers.local_map_pull_target_dir

MappingStatusSummary = _mapping_status_summary.MappingStatusSummary
parse_mapping_status_values = _mapping_status_summary.parse_mapping_status_values
summarize_mapping_status = _mapping_status_summary.summarize_mapping_status


def mapping_operation_style(state: str) -> tuple[str, str, str]:
    return style_for_state(MAPPING_OPERATION_STYLES, state, "idle")


def mapping_status_style(state: str) -> tuple[str, str, str]:
    return style_for_state(MAPPING_STATUS_STYLES, state)

