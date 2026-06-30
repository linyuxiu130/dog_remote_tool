from __future__ import annotations

from dog_remote_tool.core.profiles import ProductProfile, get_product


ARC_DOCK_STATE_TEXT = {
    "0": "空闲",
    "1": "已接触",
    "2": "充电中",
    "3": "失败",
    "4": "已完成",
    "5": "被动",
}

ARC_STATE_TEXT = {
    "0": "待机",
    "1": "标定中",
    "2": "回充初始化",
    "3": "回充导航",
    "4": "粗对准",
    "5": "精对准",
    "6": "接触检测",
    "7": "充电中",
    "8": "出桩中",
    "9": "出桩复位",
    "10": "成功",
    "11": "安全失败",
    "12": "接触失败",
    "13": "被动",
}


def arc_runtime_profile(profile: ProductProfile) -> ProductProfile:
    """Return the compute-side target that owns robot_arc for split 3588/NX systems."""
    if profile.key == "xg2_3588":
        return get_product("xg2_s100")
    if profile.key == "zg3588":
        return get_product("zg_lidar_nx")
    if profile.key == "zg_surround_3588":
        return get_product("zg_surround_s100")
    return profile
