from __future__ import annotations

from dog_remote_tool.core.profiles import ProductProfile
from dog_remote_tool.modules.mapping import alg as mapping_alg


def probe_status_command(profile: ProductProfile, save_map_path: str) -> str:
    return mapping_alg.alg_probe_status_command(profile, save_map_path)
