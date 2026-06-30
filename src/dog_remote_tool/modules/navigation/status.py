from __future__ import annotations

from dog_remote_tool.core.parsers import parse_key_values as _parse_key_values
from dog_remote_tool.modules.navigation import status_labels


LIFECYCLE_SERVICES = (
    "/map_server/get_state",
    "/planner_server/get_state",
    "/controller_server/get_state",
    "/behavior_server/get_state",
    "/collision_monitor/get_state",
    "/bt_navigator/get_state",
    "/waypoint_follower/get_state",
    "/velocity_optimizer/get_state",
    "/local_costmap/local_costmap/get_state",
    "/global_costmap/global_costmap/get_state",
)
NAVIGATION_STATE_TEXT = status_labels.NAVIGATION_STATE_TEXT
ACTIVE_SUBSTATE_TEXT = status_labels.ACTIVE_SUBSTATE_TEXT
TASK_STATUS_TEXT = status_labels.TASK_STATUS_TEXT
LOCALIZATION_STATE_TEXT = status_labels.LOCALIZATION_STATE_TEXT
PERCEPTION_STATE_TEXT = status_labels.PERCEPTION_STATE_TEXT
parse_key_values = _parse_key_values


def _state_text(values: dict[str, str], code: str, prefix: str) -> str:
    return values.get(str(code), f"{prefix}{code}" if code else "--")


def navigation_state_text(code: str) -> str:
    return _state_text(NAVIGATION_STATE_TEXT, code, "状态")


def active_substate_text(code: str) -> str:
    return _state_text(ACTIVE_SUBSTATE_TEXT, code, "子状态")


def task_status_text(code: str) -> str:
    return _state_text(TASK_STATUS_TEXT, code, "任务")


def localization_state_text(code: str) -> str:
    return _state_text(LOCALIZATION_STATE_TEXT, code, "定位")


def localization_state_display_text(code: str, description: str = "", code_field: str = "status") -> str:
    normalized = str(code)
    desc = description.strip()
    desc_lower = desc.lower()
    if ("running normally" in desc_lower or "system is normal" in desc_lower or "正常" in desc) and not (
        "lost" in desc_lower or "fail" in desc_lower or "failed" in desc_lower or "丢失" in desc or "失败" in desc
    ):
        return "连续定位正常"
    if normalized == "6":
        if code_field == "state":
            return "连续定位正常"
        if "active" in desc_lower or "running normally" in desc_lower or "正常" in desc:
            return "连续定位正常"
        if "lost" in desc_lower or "丢失" in desc:
            return "定位丢失"
    if normalized == "8" or "fail" in desc_lower or "failed" in desc_lower or "失败" in desc:
        return "重定位失败"
    return localization_state_text(normalized)


def perception_state_text(code: str) -> str:
    return _state_text(PERCEPTION_STATE_TEXT, code, "感知")


def navigation_user_status_summary(values: dict[str, str], include_metrics: bool = True) -> str:
    app_nav_status = values.get("APP_NAV_STATUS", "").strip()
    if app_nav_status:
        return f"导航状态：{app_nav_status}"
    text = values.get("TEXT", "").strip()
    return f"导航状态：{text}" if text else "导航状态：等待刷新"


from dog_remote_tool.modules.navigation.status_summary import summarize_status as _summarize_status

summarize_status = _summarize_status
