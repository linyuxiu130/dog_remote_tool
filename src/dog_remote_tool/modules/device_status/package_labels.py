from __future__ import annotations


PACKAGE_LABELS = {
    "app-launch": "应用入口",
    "community-node": "社区节点",
    "det-inference": "感知推理",
    "det-inference-nx": "感知推理",
    "elevation-mapping": "地形建图",
    "libnvjpeg-12-6": "NVJPEG 运行库",
    "libnvjpeg-dev-12-6": "NVJPEG 开发库",
    "motion-control": "运动控制",
    "navigation": "导航",
    "perception-zg": "中狗感知",
    "robot-alg-manager": "算法管理",
    "robot-arc": "回充",
    "robot-deb": "系统工具",
    "robot-forward": "数据转发",
    "robot-meb": "安全避障",
    "robot-monitor": "机器人监控",
    "robot-ota-cli": "OTA 工具",
    "robot-ws": "机器人工作区",
    "robot-runtime": "运行环境",
    "robot-runtime-nx": "NX 运行环境",
    "robot-runtime-s100": "S100 运行环境",
    "robot-driver": "传感器驱动",
    "robot-sensors": "传感器驱动",
    "robot-localization": "定位",
    "robot-slam": "建图/定位",
    "robot-nav": "导航",
    "robot-nav2": "导航",
    "robot-navigation": "导航",
    "robot_nav": "导航",
    "robot_nav2": "导航",
    "robot-launch": "启动管理",
    "robots_dog_msgs": "通信消息",
    "zsibot_common": "公共库",
    "zsibot-common": "公共库",
    "zsibot-sdk": "SDK",
}

S100_PACKAGE_GROUPS = (
    ("导航", ("navigation", "robot-nav", "robot-nav2", "robot-navigation", "robot_nav", "robot_nav2")),
    ("建图/定位", ("robot-slam",)),
    ("传感器驱动", ("robot-driver", "robot-sensors")),
    ("S100 运行环境", ("robot-runtime-s100",)),
    ("启动管理", ("robot-launch",)),
)

NX_PACKAGE_GROUPS = (
    ("导航", ("navigation", "robot-nav", "robot-nav2", "robot-navigation", "robot_nav", "robot_nav2")),
    ("建图/定位", ("robot-slam",)),
    ("中狗感知", ("perception-zg",)),
    ("传感器驱动", ("robot-driver", "robot-sensors")),
    ("算法管理", ("robot-alg-manager",)),
    ("数据转发", ("robot-forward",)),
    ("运行环境", ("robot-runtime-nx", "robot-runtime")),
    ("系统工具", ("robot-deb",)),
    ("通信消息", ("robots_dog_msgs",)),
    ("公共库", ("zsibot_common", "zsibot-common")),
    ("NVJPEG 运行库", ("libnvjpeg-12-6",)),
    ("NVJPEG 开发库", ("libnvjpeg-dev-12-6",)),
    ("回充", ("robot-arc",)),
    ("安全避障", ("robot-meb",)),
    ("启动管理", ("robot-launch",)),
)

XG1_NX_PACKAGE_GROUPS = (
    ("应用入口", ("app-launch",)),
    ("导航", ("navigation", "robot-nav", "robot-nav2", "robot-navigation", "robot_nav", "robot_nav2")),
    ("定位", ("robot-localization",)),
    ("建图", ("robot-slam",)),
    ("传感器驱动", ("robot-driver", "robot-sensors")),
    ("感知推理", ("det-inference-nx",)),
    ("地形建图", ("elevation-mapping",)),
    ("算法管理", ("robot-alg-manager",)),
    ("数据转发", ("robot-forward",)),
    ("回充", ("robot-arc",)),
    ("机器人监控", ("robot-monitor",)),
    ("社区节点", ("community-node",)),
    ("通信消息", ("robots_dog_msgs",)),
    ("公共库", ("zsibot_common", "zsibot-common")),
    ("SDK", ("zsibot-sdk",)),
    ("启动管理", ("robot-launch",)),
)

XG3588_PACKAGE_GROUPS = (
    ("应用入口", ("app-launch",)),
    ("运动控制", ("motion-control",)),
    ("导航", ("navigation", "robot-nav", "robot-nav2", "robot-navigation", "robot_nav", "robot_nav2")),
    ("感知推理", ("det-inference", "det-inference-nx")),
    ("数据转发", ("robot-forward",)),
    ("机器人监控", ("robot-monitor",)),
    ("通信消息", ("robots_dog_msgs",)),
    ("公共库", ("zsibot_common", "zsibot-common")),
    ("启动管理", ("robot-launch",)),
)

BASE_PACKAGE_GROUPS = (
    ("运动控制", ("motion-control",)),
    ("机器人工作区", ("robot-ws",)),
    ("运行环境", ("robot-runtime",)),
    ("启动管理", ("robot-launch",)),
)
