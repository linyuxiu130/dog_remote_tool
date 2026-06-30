from __future__ import annotations

from dog_remote_tool.modules.ota.types import OtaTarget


TARGETS = {
    "xg_l1_point_3588": OtaTarget(
        "xg_l1_point_3588", "小狗 L1 点足 3588", "rk3588", "192.168.234.1", "firefly", "firefly"
    ),
    "xg_l1_wheel_3588": OtaTarget(
        "xg_l1_wheel_3588", "小狗 L1 轮足 3588", "rk3588", "192.168.234.1", "firefly", "firefly"
    ),
    "xg_l1_point_nx": OtaTarget("xg_l1_point_nx", "小狗 L1 点足 NX", "nx", "192.168.234.234", "robot", "1"),
    "xg_l1_wheel_nx": OtaTarget("xg_l1_wheel_nx", "小狗 L1 轮足 NX", "nx", "192.168.234.234", "robot", "1"),
    "xg3588": OtaTarget("xg3588", "小狗一代 3588（旧入口）", "rk3588", "192.168.234.1", "firefly", "firefly"),
    "nx": OtaTarget("nx", "小狗一代 NX（旧入口）", "nx", "192.168.234.234", "robot", "1"),
    "zg3588": OtaTarget("zg3588", "中狗 3588", "rk3588", "192.168.234.1", "robot", "bot"),
    "zgnx": OtaTarget("zgnx", "中狗 NX", "nx", "192.168.168.100", "robot", "1"),
}
