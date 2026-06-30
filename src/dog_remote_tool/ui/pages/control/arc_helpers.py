from __future__ import annotations


ARC_CHARGING_DOCK_STATES = {"2"}
ARC_APP_CHARGING_STATES = {"Charging"}
ARC_READY_STATES = {"0", "10", "13"}
ARC_APP_READY_STATES = {"StandBy", "Success", "Idle", ""}


def arc_remote_action_state(values: dict[str, str]) -> tuple[str, str, bool, str]:
    dock_state = values.get("ARC_DOCK_STATE", "")
    dock_text = values.get("ARC_DOCK_TEXT", "") or "无数据"
    arc_state = values.get("ARC_STATE", "")
    arc_text = values.get("ARC_TEXT", "") or "无数据"
    app_alg = values.get("ARC_APP_ALG_STATUS", "")
    app_dock = values.get("ARC_APP_DOCK_STATUS", "")
    detected = values.get("ARC_DOCK_DETECTED", "") in {"1", "true", "True"}
    charging = (
        dock_state in ARC_CHARGING_DOCK_STATES
        or dock_text == "充电中"
        or arc_text == "充电中"
        or app_alg in ARC_APP_CHARGING_STATES
        or app_dock in ARC_APP_CHARGING_STATES
    )
    if charging:
        return "undock", "出桩", True, "充电中"
    if detected:
        if not arc_state or arc_state in ARC_READY_STATES:
            return "dock", "回充", True, "已识别充电桩"
        return "", "回充", False, f"ARC {arc_text}，暂不可回充"
    app_ready = bool(app_alg or app_dock) and app_alg in ARC_APP_READY_STATES and app_dock in ARC_APP_READY_STATES
    arc_ready = bool(arc_state) and arc_state in ARC_READY_STATES
    if dock_state in {"", "0"} and (app_ready or arc_ready):
        return "dock", "回充", True, "ARC 正常，未确认识别充电桩"
    if dock_state:
        return "", "回充", False, f"{dock_text}，未识别充电桩"
    return "", "回充", False, "读取中"
