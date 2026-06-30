from __future__ import annotations


NAVIGATION_STATE_TEXT = {
    "0": "待机/空闲",
    "1": "初始化/旧版待机",
    "2": "执行中",
    "3": "暂停",
    "4": "已取消",
    "5": "已到达",
    "6": "失败",
    "7": "空闲",
    "100": "执行中",
    "140": "初始化",
    "141": "暂停",
    "200": "已到达",
    "201": "已取消",
    "202": "失败",
}
NAVIGATION_STATE_ENUM_TEXT = {
    "0": "STANDBY/IDLE",
    "1": "INITIALIZING/STANDBY",
    "2": "ACTIVE",
    "3": "PAUSED",
    "4": "CANCELLED",
    "5": "SUCCEEDED",
    "6": "FAILED",
    "7": "IDLE",
    "100": "ACTIVE",
    "140": "INITIALIZING",
    "141": "PAUSED",
    "200": "SUCCEEDED",
    "201": "CANCELLED",
    "202": "FAILED",
}
ACTIVE_SUBSTATE_TEXT = {
    "0": "正常",
    "1": "避障",
    "2": "阻塞",
}
ACTIVE_SUBSTATE_ENUM_TEXT = {
    "0": "NORMAL",
    "1": "AVOIDING",
    "2": "BLOCKED",
}
TASK_STATUS_TEXT = {
    "0": "等待",
    "1": "初始化",
    "2": "执行中",
    "3": "暂停",
    "4": "已取消",
    "5": "成功",
    "6": "失败",
}
TASK_STATUS_ENUM_TEXT = {
    "0": "PENDING",
    "1": "INITIALIZING",
    "2": "EXECUTING",
    "3": "PAUSED",
    "4": "CANCELLED",
    "5": "SUCCEEDED",
    "6": "FAILED",
}
LOCALIZATION_STATE_TEXT = {
    "0": "初始化",
    "1": "地图加载中",
    "2": "初始定位/重定位中",
    "3": "连续定位正常",
    "4": "定位错误",
    "5": "主动重定位",
    "6": "定位丢失",
    "8": "重定位失败",
    "100": "连续定位正常",
}
PERCEPTION_STATE_TEXT = {
    "0": "初始化",
    "1": "模型加载中",
    "2": "传感器异常",
    "3": "运行正常",
    "4": "运行中",
}
