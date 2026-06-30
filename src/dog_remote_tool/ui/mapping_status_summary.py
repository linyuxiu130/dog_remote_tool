from __future__ import annotations

from dataclasses import dataclass
import re

from dog_remote_tool.core.parsers import parse_key_values
from dog_remote_tool.core.profiles import ProductProfile
from dog_remote_tool.core.text import compact_lines
from dog_remote_tool.modules import mapping
from dog_remote_tool.ui.map_history_helpers import format_disk_detail


@dataclass(frozen=True)
class MappingStatusSummary:
    values: dict[str, str]
    state: str
    text: str
    detail: str
    alg_status: str
    failed: bool = False


def _status_detail_text(state: str, text: str, alg_status: str) -> str:
    if alg_status:
        return text
    if state == "unknown":
        return "未读取到远端状态"
    return text or "未知"


def _compact_latest_map(remote_map: str) -> str:
    if not remote_map:
        return "--"
    match = re.search(r"/history_map/(\d{4})_(\d{2})_(\d{2})_(\d{2})_(\d{2})_(\d{2})/", remote_map)
    if match:
        _year, month, day, hour, minute, _second = match.groups()
        return f"{month}-{day} {hour}:{minute}"
    return remote_map.rsplit("/", 1)[-1]


def _disk_available_text(values: dict[str, str]) -> str:
    disk_detail = format_disk_detail(
        values.get("DISK_AVAILABLE", ""),
        values.get("DISK_SIZE", ""),
        values.get("DISK_USED_PERCENT", ""),
        values.get("DISK_TARGET", ""),
    )
    if not disk_detail:
        return "--"
    for part in disk_detail.split("；"):
        if part.startswith("可用空间 "):
            return part.removeprefix("可用空间 ")
    return "--"


def parse_mapping_status_values(output: str) -> dict[str, str]:
    return parse_key_values(output)


def summarize_mapping_status(
    profile: ProductProfile,
    output: str,
    exit_code: int,
    operation_title: str = "",
) -> MappingStatusSummary:
    values = parse_key_values(output)
    if exit_code != 0 and "STATUS" not in values:
        detail = compact_lines(output)
        return MappingStatusSummary(
            values=values,
            state="unknown",
            text="读取失败",
            detail=detail or f"状态命令退出码 {exit_code}",
            alg_status="",
            failed=True,
        )

    details = []
    if exit_code != 0:
        details.append(f"状态命令退出码 {exit_code}")
    alg_status = values.get("ALG_MAPPING_STATUS", "")
    alg_error_code = values.get("SLAM_ERROR_CODE", "")
    alg_error_msg = values.get("SLAM_ERROR_MSG", "")
    if alg_error_code:
        error_detail = f"错误码 {alg_error_code}"
        if alg_error_msg:
            error_detail += f"：{alg_error_msg}"
        details.append(f"状态：{error_detail}")
    state = values.get("STATUS", "unknown")
    text = values.get("TEXT", "未知")
    derived_status = mapping.mapping_status_from_alg_status(profile, alg_status, alg_error_code, alg_error_msg)
    if derived_status:
        state, text = derived_status
    if operation_title and "保存" in operation_title and state == "ready":
        state, text = "saving", "保存确认中"
    latest_map = values.get("LATEST_MAP", "")
    latest_age = values.get("LATEST_MAP_AGE", "")
    try:
        latest_age_seconds = int(float(latest_age)) if latest_age else 999999
    except ValueError:
        latest_age_seconds = 999999
    recent_save = state in {"ready", "unknown", "saving"} and latest_map and latest_age_seconds <= 120
    if recent_save:
        state, text = "success", "保存完成"
    details.insert(0, f"远端状态：{_status_detail_text(state, text, alg_status)}")
    details.append(f"历史地图：{values.get('MAP_COUNT', '0')} 张")
    details.append(f"最新地图：{_compact_latest_map(latest_map)}")
    details.append(f"剩余空间：{_disk_available_text(values)}")
    if recent_save:
        details.append(f"最新地图刚更新：{latest_age_seconds}s 前")
    if operation_title and "保存" in operation_title and state != "success":
        details.append("保存流程进行中，正在确认地图文件")
    return MappingStatusSummary(
        values=values,
        state=state,
        text=text,
        detail="\n".join(details),
        alg_status=alg_status,
    )
