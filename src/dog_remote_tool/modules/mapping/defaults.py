from __future__ import annotations

from pathlib import Path

from dog_remote_tool.core.profiles import ProductProfile


DEFAULT_SENSOR_TYPE = "nx_xg_rs"
DEFAULT_SAVE_MAP_PATH = "/ota/alg_data/map"
OTA_SAVE_MAP_PATH = DEFAULT_SAVE_MAP_PATH
DEFAULT_HISTORY_MAP_PATH = f"{DEFAULT_SAVE_MAP_PATH}/history_map"
DEFAULT_CALIBRATION_FILE_PATH = "/ota/l2_new.yaml"
DEFAULT_ARC_CALIBRATION_FILE_PATH = (
    "/opt/robot/robot_arc/install/apriltag_localization/config/apriltag_localization_pc_config.yaml"
)
DEFAULT_LOCAL_DATA_ROOT = Path.home() / "data"
DEFAULT_LOCAL_MAP_DIR = str(DEFAULT_LOCAL_DATA_ROOT / "maps")
ZG_MAPPING_TARGETS = {"zg_lidar_nx", "zg_surround_s100", "zg_surround_3588"}
OTA_MAPPING_TARGETS = {"xg3588", "zg3588", *ZG_MAPPING_TARGETS, "xg1_nx", "xg2_s100"}
CALIBRATION_RESULTS_TARGETS = {"xg1_nx", "xg2_s100", *ZG_MAPPING_TARGETS}


def default_sensor_type(profile: ProductProfile | None = None) -> str:
    if profile and profile.key in ZG_MAPPING_TARGETS:
        return "nx_zg"
    if profile and profile.key == "xg1_nx":
        return "nx_xg"
    return DEFAULT_SENSOR_TYPE


def default_save_map_path(profile: ProductProfile | None = None) -> str:
    if profile and profile.key in OTA_MAPPING_TARGETS:
        return OTA_SAVE_MAP_PATH
    return DEFAULT_SAVE_MAP_PATH


def default_calibration_file_path(profile: ProductProfile | None = None) -> str:
    if profile and profile.key in CALIBRATION_RESULTS_TARGETS:
        return "/ota/calibration_results.yaml"
    return DEFAULT_CALIBRATION_FILE_PATH


def default_arc_calibration_file_path(_profile: ProductProfile | None = None) -> str:
    return DEFAULT_ARC_CALIBRATION_FILE_PATH


def default_map_pcd_path(profile: ProductProfile | None = None) -> str:
    return f"{default_save_map_path(profile).rstrip('/')}/map.pcd"


def history_map_path(save_map_path: str) -> str:
    root = (save_map_path or DEFAULT_SAVE_MAP_PATH).rstrip("/")
    if root.endswith("/history_map"):
        return root
    return f"{root}/history_map"
