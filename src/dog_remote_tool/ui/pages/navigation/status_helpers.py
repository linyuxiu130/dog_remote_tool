from __future__ import annotations

import re

from dog_remote_tool.ui.status_styles import style_for_state


STATUS_STYLES = {
    "active": ("#edf8f0", "#22623a", "#c9ead2"),
    "ready": ("#eef7ff", "#245b84", "#c7e2f8"),
    "success": ("#edf8f0", "#22623a", "#c9ead2"),
    "starting": ("#fff8ed", "#8b4513", "#f5dec0"),
    "paused": ("#fff8ed", "#8b4513", "#f5dec0"),
    "cancelled": ("#ffffff", "#46566b", "#e3eaf3"),
    "blocked": ("#fff1f2", "#9f2d2d", "#f2c7c7"),
    "error": ("#fff1f2", "#9f2d2d", "#f2c7c7"),
    "unknown": ("#f8fafc", "#46566b", "#dbe6f2"),
}


ANSI_ESCAPE_RE = re.compile(r"(?:\x1b|\u241b)\[[0-?]*[ -/]*[@-~]")
CONTROL_CHAR_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
NAV_ACTION_READY_STYLE = (
    "background:#edf8f0;color:#22623a;border:1px solid #c9ead2;border-radius:8px;padding:8px 10px;font-weight:700;"
)
NAV_ACTION_BLOCKED_STYLE = (
    "background:#fff8ed;color:#8b4513;border:1px solid #f5dec0;border-radius:8px;padding:8px 10px;font-weight:700;"
)
NAVIGATION_COMMAND_PENDING_TEXT = {
    "加载地图中": "地图初始化下发中",
    "发送目标中": "目标下发中",
    "多点导航中": "多点目标下发中",
    "路网导航中": "路网目标下发中",
}
NAVIGATION_COMMAND_WAIT_TEXT = {
    "加载地图中": "等待远端加载当前地图",
    "发送目标中": "等待远端接收目标并进入执行中",
    "多点导航中": "等待远端接收多点目标并进入执行中",
    "路网导航中": "等待远端接收路网目标并进入执行中",
}
NAVIGATION_REMOTE_STATE_KEYS = (
    "NAV_STATE",
    "NAV_ACTIVE_SUBSTATE",
    "NAV_TASK_STATUS",
    "NAV_CURRENT_TASK_IDX",
    "NAV_DISTANCE_FROM_START",
    "NAV_ESTIMATED_DISTANCE_REMAINING",
    "NAV_ESTIMATED_TIME_REMAINING_SEC",
    "NAV_ERROR",
)


def _status_confirms_selected_map_pose_ready(values: dict[str, str], map_pcd: str) -> bool:
    if not map_pcd:
        return False
    return (
        values.get("MAP_PCD", "").strip() == map_pcd
        and values.get("MAP_OK") == "1"
        and values.get("LOCALIZATION_READY") == "1"
    )


def _status_allows_selected_map_pose_display(values: dict[str, str], map_pcd: str) -> bool:
    if not map_pcd or values.get("LOCALIZATION_READY") != "1":
        return False
    status_map = values.get("MAP_PCD", "").strip()
    if status_map and status_map != map_pcd:
        return False
    return values.get("MAP_OK", "1") == "1"


def _status_confirms_selected_map_navigation_ready(values: dict[str, str], map_pcd: str) -> bool:
    if not _status_confirms_selected_map_pose_ready(values, map_pcd):
        return False
    return values.get("NAV_PROCESS") == "1" and values.get("START_NAV_SUBSCRIBERS", "0") != "0"


def _status_style(state: str) -> tuple[str, str, str]:
    return style_for_state(STATUS_STYLES, state)


def _navigation_command_pending_text(operation: str) -> str:
    return NAVIGATION_COMMAND_PENDING_TEXT.get(operation, operation)


def _navigation_command_wait_text(operation: str) -> str:
    return NAVIGATION_COMMAND_WAIT_TEXT.get(operation, "等待远端状态回读")


def _without_remote_navigation_state(values: dict[str, str]) -> dict[str, str]:
    next_values = dict(values)
    for key in NAVIGATION_REMOTE_STATE_KEYS:
        next_values.pop(key, None)
    return next_values


def _sanitize_log_line(text: str) -> str:
    text = ANSI_ESCAPE_RE.sub("", text)
    text = text.replace("\u241b", "")
    text = CONTROL_CHAR_RE.sub("", text)
    return text


def _compact_failure_lines(output: str, *, limit: int = 8, width: int = 220) -> str:
    skip_markers = (
        "dog_remote_tool_plan_stream",
        "dog_remote_tool_pose_stream",
        "dog_remote_tool_nav_camera_overlay_stream",
        "python3 -u - <<'PY'",
        "bash -c IFS= read -r DOG_REMOTE_SUDO_PASS",
    )
    lines = []
    for raw in output.strip().splitlines():
        line = " ".join(_sanitize_log_line(raw).strip().split())
        if not line or any(marker in line for marker in skip_markers):
            continue
        if len(line) > width:
            line = line[: width - 3] + "..."
        lines.append(line)
    priority = [
        line
        for line in lines
        if any(token in line.lower() for token in ("[error]", "error", "failed", "失败", "超时", "未就绪", "exception"))
    ]
    warnings = [line for line in lines if "[WARN]" in line or "warn" in line.lower()]
    selected = (priority + warnings)[:limit]
    if not selected:
        selected = lines[-limit:]
    return "\n".join(selected)
