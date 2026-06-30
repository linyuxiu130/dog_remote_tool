from __future__ import annotations

from dog_remote_tool.core.profiles import ProductProfile
from dog_remote_tool.core.shell import echo_message, quote
from dog_remote_tool.modules.localization import alg as localization_alg


def load_navigation_map_inner(profile: ProductProfile, map_pcd_path: str) -> str:
    return (
        f"if [ ! -s {quote(map_pcd_path)} ]; then {echo_message(f'[ERROR] 地图 PCD 不存在或为空: {map_pcd_path}')}; exit 2; fi; "
        f"{load_localization_map_once_inner(profile, map_pcd_path)}"
    )


def load_localization_map_once_inner(profile: ProductProfile, map_pcd_path: str, timeout_seconds: int = 45) -> str:
    alg_load_call = localization_alg.alg_localization_load_inner(profile, map_pcd_path, timeout_seconds)
    return (
        f"{alg_load_call}; "
        "ALG_NAV_LOC_RC=$?; "
        "if [ \"$ALG_NAV_LOC_RC\" -ne 0 ]; then exit \"$ALG_NAV_LOC_RC\"; fi; "
        "echo MAP_PREP_LOCALIZATION_READY=1; "
        "echo MAP_PREP_MAP_PCD=" + quote(map_pcd_path) + "; "
    )
