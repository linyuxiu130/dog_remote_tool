from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class ProductProfile:
    key: str
    label: str
    platform: str
    host: str
    user: str
    password: str
    home: str
    bag_storage: str = "mcap"
    ros_domain_id: str = "24"
    rmw: str = "rmw_zenoh_cpp"
    jump_host: str = ""
    jump_user: str = ""
    jump_password: str = ""
    capabilities: tuple[str, ...] = field(default_factory=tuple)

    @property
    def target(self) -> str:
        return f"{self.user}@{self.host}"


PRODUCTS: dict[str, ProductProfile] = {
    "xg3588": ProductProfile(
        key="xg3588",
        label="小狗一代 3588",
        platform="RK3588",
        host="192.168.234.1",
        user="firefly",
        password="firefly",
        home="/home/firefly",
        capabilities=("bag", "control", "remote_access", "ota", "5g"),
    ),
    "xg2_3588": ProductProfile(
        key="xg2_3588",
        label="小狗二代 3588",
        platform="RK3588",
        host="192.168.234.1",
        user="robot",
        password="bot",
        home="/home/robot",
        capabilities=("bag", "control", "remote_access", "flash", "5g"),
    ),
    "zg3588": ProductProfile(
        key="zg3588",
        label="中狗 3588",
        platform="RK3588",
        host="192.168.234.1",
        user="robot",
        password="bot",
        home="/home/robot",
        capabilities=("bag", "control", "remote_access", "ota", "5g"),
    ),
    "zg_surround_3588": ProductProfile(
        key="zg_surround_3588",
        label="中狗环视版 3588",
        platform="RK3588",
        host="192.168.234.1",
        user="robot",
        password="bot",
        home="/home/robot",
        capabilities=("bag", "control", "remote_access", "ota", "5g"),
    ),
    "xg1_nx": ProductProfile(
        key="xg1_nx",
        label="小狗一代 NX",
        platform="Orin NX",
        host="192.168.234.234",
        user="robot",
        password="1",
        home="/home/robot",
        capabilities=("bag", "ota", "frp", "visualizer", "sensor", "mapping", "localization", "navigation", "speed_override"),
    ),
    "xg2_s100": ProductProfile(
        key="xg2_s100",
        label="小狗二代 S100",
        platform="S100",
        host="192.168.168.100",
        user="robot",
        password="1",
        home="/home/robot",
        bag_storage="sqlite3",
        jump_host="192.168.234.1",
        jump_user="robot",
        jump_password="bot",
        capabilities=("bag", "sensor", "visualizer", "mapping", "localization", "navigation", "flash"),
    ),
    "zg_surround_s100": ProductProfile(
        key="zg_surround_s100",
        label="中狗环视版 S100",
        platform="S100",
        host="192.168.168.100",
        user="robot",
        password="1",
        home="/home/robot",
        jump_host="192.168.234.1",
        jump_user="robot",
        jump_password="bot",
        capabilities=("bag", "sensor", "visualizer", "frp", "mapping", "localization", "navigation", "flash"),
    ),
    "zg_lidar_nx": ProductProfile(
        key="zg_lidar_nx",
        label="中狗激光版 NX",
        platform="Orin NX",
        host="192.168.168.100",
        user="robot",
        password="1",
        home="/home/robot",
        jump_host="192.168.234.1",
        jump_user="robot",
        jump_password="bot",
        capabilities=("bag", "flash", "frp", "visualizer", "sensor", "mapping", "localization", "navigation", "speed_override"),
    ),
}


def product_keys() -> list[str]:
    return list(PRODUCTS.keys())


def get_product(key: str) -> ProductProfile:
    return PRODUCTS[key]
