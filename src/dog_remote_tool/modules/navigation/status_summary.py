from __future__ import annotations

from dog_remote_tool.core.parsers import parse_key_values
from dog_remote_tool.modules.navigation import status as navigation_status


def summarize_status(output: str, exit_code: int = 0) -> tuple[str, str, str, dict[str, str]]:
    values = parse_key_values(output)
    app_nav_status = values.get("APP_NAV_STATUS", "").strip()
    if app_nav_status:
        if app_nav_status in {"Running", "Active", "Naving"}:
            values["STATUS"] = "active"
        elif app_nav_status in {"Succeeded"}:
            values["STATUS"] = "success"
        elif app_nav_status in {"Error", "NavError", "LocError", "Failed"}:
            values["STATUS"] = "error"
        elif app_nav_status in {"Stopped", "StandBy"}:
            values.setdefault("STATUS", "ready")
        values["TEXT"] = app_nav_status
    if exit_code != 0 and "STATUS" not in values:
        if values:
            if values.get("NAV_PROCESS") == "1" and values.get("START_NAV_SUBSCRIBERS") == "0":
                values["STATUS"] = "blocked"
                values["TEXT"] = "导航状态通道异常"
            elif values.get("NAV_PROCESS") == "1":
                values["STATUS"] = "unknown"
                values["TEXT"] = "状态读取中断"
            else:
                values["STATUS"] = "blocked"
                values["TEXT"] = "导航栈未就绪"
        else:
            compact = output.strip().replace("\n", "；")
            return "unknown", "读取失败", compact[:240], values
    details = []
    map_pcd = values.get("MAP_PCD", "")
    if map_pcd:
        map_text = "可用" if values.get("MAP_OK") == "1" else "缺失"
        details.append(f"地图：{map_text}")
    artifacts = []
    if "LICENSE_OK" in values:
        artifacts.append("授权正常" if values.get("LICENSE_OK") == "1" else "授权缺失")
    if "CALIBRATION_OK" in values:
        artifacts.append("标定正常" if values.get("CALIBRATION_OK") == "1" else "标定缺失")
    if artifacts:
        details.append("文件：" + "，".join(artifacts))
    nav_ready = values.get("NAV_PROCESS") == "1" and values.get("START_NAV_SUBSCRIBERS", "0") != "0"
    details.append("导航服务：" + ("可用" if nav_ready else "未启动"))
    subscribers = values.get("START_NAV_SUBSCRIBERS", "0")
    if values.get("NAV_PROCESS") == "1" and subscribers == "0":
        details.append("导航服务：等待指令通道")
    if "NAVIGATION_CMD_PUBLISHERS" in values:
        has_motion = any(values.get(f"{key}_VEL", "") for key in ("NAVIGATION_CMD", "HANDLE_VEL", "CMD_VEL"))
        details.append("运动输出：" + ("有速度输出" if has_motion else "等待输出"))
    if "ROBOT_ROAMERX_IS_IN_NAV_CONTROL_PUBLISHERS" in values:
        bridge_ready = values.get("ROBOT_CONTROL_SERVER_NAV_POSE_SUBSCRIBERS", "0") != "0"
        details.append("底盘控制：" + ("已连接" if bridge_ready else "等待连接"))
    loc_code = values.get("LOCALIZATION_CODE", "")
    loc_code_field = values.get("LOCALIZATION_CODE_FIELD", "status") or "status"
    loc_desc = values.get("LOCALIZATION_DESC", "")
    loc_text = navigation_status.localization_state_display_text(loc_code, loc_desc, loc_code_field)
    if loc_code:
        desc_part = f"；{loc_desc}" if loc_desc and loc_text in {"定位丢失", "重定位失败"} else ""
        details.append(f"定位：{loc_text}{desc_part}")
    elif values.get("LOCALIZATION_TOPIC"):
        details.append("定位：状态未更新")
    else:
        details.append("定位：未发布")
    stamp_details = []
    for label, key in (
        ("laser_scan", "LASER_SCAN_STAMP_AGE_MS"),
        ("current_pose", "CURRENT_POSE_STAMP_AGE_MS"),
        ("localization_state", "LOCALIZATION_STATE_STAMP_AGE_MS"),
    ):
        value = values.get(key, "")
        if value:
            stamp_details.append(f"{label}={value}ms")
    if stamp_details:
        details.append("数据延迟：" + "，".join(stamp_details))
    if "PERCEPTION_CODE" in values or "PERCEPTION_READY" in values:
        pers_code = values.get("PERCEPTION_CODE", "")
        if pers_code:
            details.append(f"感知：{navigation_status.perception_state_text(pers_code)}")
        else:
            details.append("感知：未发布")
    user_nav_summary = navigation_status.navigation_user_status_summary(values)
    if user_nav_summary:
        details.append(user_nav_summary)
    if values.get("NAV_ERROR"):
        details.append(f"错误：{values['NAV_ERROR']}")
    if "NAV_ERRORS_PUBLISHERS" in values:
        nav_errors = values.get("NAV_ERRORS_SUMMARY", "")
        if nav_errors:
            details.append(f"导航错误：{nav_errors}")
        else:
            details.append("导航错误：暂无")
    if "DETECTION2D_PUBLISHERS" in values:
        publishers = values.get("DETECTION2D_PUBLISHERS", "0")
        if values.get("DETECTION2D_READY") == "1":
            details.append("障碍物感知：正常")
        elif publishers != "0":
            details.append("障碍物感知：未取到有效数据")
        else:
            details.append("障碍物感知：未发布")
    if values.get("PERCEPTION_DESC") == "not_published":
        details.append("感知：未发布 /pers/state，按当前设备可选项处理")
    ready_services = values.get("READY_LIFECYCLE_SERVICES", "")
    if ready_services:
        details.append(f"Lifecycle 服务：{ready_services}/{len(navigation_status.LIFECYCLE_SERVICES)}")
    missing_services = values.get("MISSING_LIFECYCLE_SERVICES", "")
    if missing_services:
        details.append(f"未就绪：{missing_services}")
    warnings = values.get("NAV_LOG_LIFECYCLE_WARNINGS", "")
    if warnings:
        details.append(f"导航日志异常：最近 120 行 {warnings} 条")
    return values.get("STATUS", "unknown"), values.get("TEXT", "未知"), "\n".join(details), values
