from __future__ import annotations

import os
from pathlib import Path


L1_LOCAL_SDK_PATH = Path(os.environ.get("DOG_REMOTE_TOOL_L1_SDK_PATH", Path.home() / "code" / "genisom_l1_sdk")).expanduser()
L1_DEFAULT_REMOTE_SDK_PATH = "/home/firefly/genisom_l1_sdk"
L1_SDK_MODES = {
    "zsl-1": {
        "label": "zsl-1 点足",
        "lib_subdir": "zsl-1",
        "module_name": "mc_sdk_zsl_1_py",
        "vx_max": 3.0,
        "vy_max": 1.0,
        "yaw_max": 3.0,
        "crawl": False,
    },
    "zsl-1w": {
        "label": "zsl-1w 轮足",
        "lib_subdir": "zsl-1w",
        "module_name": "mc_sdk_zsl_1w_py",
        "vx_max": 3.7,
        "vy_max": 1.0,
        "yaw_max": 3.0,
        "crawl": True,
    },
}
L1_SDK_ACTIONS = {
    "status": ("状态检查", False),
    "standUp": ("站立", False),
    "lieDown": ("低姿态", False),
    "passive": ("阻尼趴下", True),
    "estop": ("急停", True),
    "crawl_mode": ("低姿态 crawl", True),
}


def l1_sdk_mode(mode_key: str) -> dict:
    return L1_SDK_MODES.get(mode_key, L1_SDK_MODES["zsl-1"])


def l1_clamp(value: float, limit: float) -> float:
    return max(-limit, min(limit, float(value)))
