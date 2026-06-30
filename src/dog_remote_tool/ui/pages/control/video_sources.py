from __future__ import annotations


VIDEO_SOURCE_OPTIONS = {
    "l1": (
        ("本体相机", "front"),
    ),
    "surround": (
        ("前双目", "front"),
        ("前鱼眼", "front"),
        ("左鱼眼", "left"),
        ("右鱼眼", "right"),
        ("后鱼眼", "back"),
    ),
    "zg": (
        ("前视相机", "front"),
        ("后视相机", "back"),
    ),
    "fallback": (
        ("前视相机", "front"),
    ),
}


def video_source_options(profile_key: str) -> list[tuple[str, str]]:
    if profile_key in {"xg3588", "xg1_nx"}:
        return list(VIDEO_SOURCE_OPTIONS["l1"])
    if profile_key in {"xg2_3588", "xg2_s100", "zg_surround_s100"}:
        return list(VIDEO_SOURCE_OPTIONS["surround"])
    if profile_key in {"zg3588", "zg_surround_3588", "zg_lidar_nx"}:
        return list(VIDEO_SOURCE_OPTIONS["zg"])
    return list(VIDEO_SOURCE_OPTIONS["fallback"])
