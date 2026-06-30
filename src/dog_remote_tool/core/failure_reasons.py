from __future__ import annotations

from collections.abc import Callable


def failure_reason(code: int, lines: list[str], is_important: Callable[[str], bool]) -> str:
    reason = _known_failure_reason(lines)
    if not reason:
        reason = _known_exit_code_reason(code, lines)
    if not reason:
        reason = _last_error_lines(lines, is_important)
    if not reason:
        reason = f"退出码 {code}；无匹配错误特征。"
    return reason


def _known_exit_code_reason(code: int, lines: list[str]) -> str:
    if code == 143:
        text = "\n".join(lines)
        if "MappingSaveBegin" in text or "保存中" in text or "结束保存请求已确认" in text:
            return "远端已接收结束保存请求，本地等待进程被停止；请刷新建图状态或历史地图确认保存结果。"
        return "本地任务被停止或连接被中断（SIGTERM）。"
    return ""


def _known_failure_reason(lines: list[str]) -> str:
    text = "\n".join(lines)
    lowered = text.lower()
    if "permission denied" in lowered and "/home/robot/.robot/param" in text:
        return "/home/robot/.robot/param 权限不足；执行 sudo mkdir -p /home/robot/.robot/param && sudo chown -R robot:robot /home/robot/.robot。"
    if "升级包不存在:" in text:
        line = _first_matching(lines, "升级包不存在:")
        return f"远端升级包不存在；{line}"
    if "/ota 文件大小校验失败" in text:
        return "NX OTA /ota 文件大小校验失败；本地包已上传完成但远端 /ota 目标文件大小不一致，请核对复制过程和目标文件。"
    if "calibration file missing:" in lowered:
        line = _first_matching(lines, "calibration file missing:")
        return f"标定文件不存在：{line.split(':', 1)[-1].strip()}"
    if "robot_slam 外部参数 yaml 不存在" in lowered:
        line = _first_matching(lines, "robot_slam 外部参数 YAML 不存在")
        return f"{line}；远端实际报错：[SystemConfig]: External parameters yaml file isn't exist."
    if "external parameters yaml file isn't exist" in lowered:
        line = _first_matching(lines, "External parameters yaml file isn't exist")
        return f"robot_slam 外部参数 YAML 缺失；远端实际报错：{line}"
    if "已停止 robot-alg-manager 但仍无法清理旧 robot_slam" in text:
        return "建图专用恢复失败；旧 robot_slam 未退出，未启动新的建图进程。"
    if "已有 robot_slam 进程" in text and "slam_state_service 未就绪" in text:
        return "远端已有 robot_slam 进程但状态服务不可见；工具已尝试建图专用恢复，请查看后续恢复日志。"
    if "slam_state_service 未就绪" in text:
        return "SLAM 状态服务未就绪；查看 robot_slam 启动日志。"
    if "invalidtopicnameerror" in lowered or "invalid topic name" in lowered:
        if "save_map_path: [] not exist" in lowered:
            return "robot_slam InvalidTopicNameError；GnssProcess save_map_path 为空或不存在。"
        return "robot_slam InvalidTopicNameError；ROS topic 为空或格式非法。"
    if "save_map_path: [] not exist" in lowered:
        return "GnssProcess save_map_path 为空或不存在；核对建图保存路径/GNSS 配置。"
    if "mapping sensors data is lost" in lowered:
        return "SLAM 建图传感器数据丢失；核对 lidar/imu 发布、频率、ROS_DOMAIN_ID/RMW。"
    if "relocalization failed" in lowered:
        return "定位重定位失败；当前地图已下发但定位未收敛。请确认地图是否匹配现场、初始位置是否接近地图真实位置，必要时重新加载地图或 reset 定位。"
    if "dock_not_ready" in lowered:
        detail = "；同时出现 FINE_FAILURE，精对准阶段已失败" if "fine_failure" in lowered else ""
        return f"ARC 回充失败：充电桩未就绪或未被稳定识别（DOCK_NOT_READY）{detail}。请确认机器狗正对充电桩二维码/桩体、距离和角度合适，充电桩已上电并完成蓝牙/UWB/桩匹配。"
    if "fine_failure" in lowered:
        return "ARC 回充失败：精对准阶段失败（FINE_FAILURE）。请确认桩体识别稳定、地图充电桩标记未偏移、初始姿态和距离合适，并检查底盘是否进入 ARC 对准控制。"
    if "sensors data" in lowered and "lost" in lowered:
        return "SLAM 输入传感器数据中断；lidar 或 imu 至少 2 秒无数据。"
    if "calibration file don't have" in lowered or "calibration file does not have" in lowered:
        return "标定文件缺少 SLAM 外参字段；核对雷达/相机标定 YAML。"
    if "未确认 state=2 ready" in lowered or "未确认可开始状态" in text:
        return "SLAM 未进入当前版本的可开始状态；未发送开始建图请求。"
    if "不是可开始/建图中状态" in text and "未发送开始请求" in text:
        return "SLAM 当前状态不是可开始或建图中状态；未发送开始建图请求。"
    if "state=6" in lowered and "未发送开始请求" in lowered:
        return "SLAM 当前状态不是可开始状态；旧版 state=6 通常表示保存完成。"
    if "current state is success" in lowered and "set active state failed" in lowered:
        return "SLAM 处于 SUCCESS，不能直接切 ACTIVE；需按 robot-slam 版本复位或重启后再开始。"
    if "检测到已有 robot_slam" in text and "不是本工具启动" in text:
        return "远端已有非本工具启动的 robot_slam；服务不可见时会尝试建图专用恢复。"
    if "no journal files were opened due to insufficient permissions" in lowered:
        return "当前用户无 systemd journal 读取权限；使用 sudo journalctl 或加入 systemd-journal 组。"
    common_reason = _common_failure_reason(lines)
    if common_reason:
        return common_reason
    if "permission denied" in lowered:
        return _first_matching(lines, "permission denied") or "权限不足。"
    return ""


def _common_failure_reason(lines: list[str]) -> str:
    text = "\n".join(lines)
    lowered = text.lower()
    if "sudo" in lowered and ("incorrect password" in lowered or "sorry, try again" in lowered or "authentication failure" in lowered):
        return "sudo 密码验证失败；核对设备密码和 sudo 权限。"
    if "host key verification failed" in lowered:
        return "SSH 主机指纹校验失败；known_hosts 与当前设备不一致。"
    if "permission denied" in lowered and ("publickey" in lowered or "password" in lowered or "keyboard-interactive" in lowered):
        return "SSH 认证失败；核对设备类型、IP、账号、密码。"
    if "connection timed out" in lowered or "no route to host" in lowered:
        return "SSH 网络不可达；核对链路、目标 IP、设备在线状态。"
    if "connection refused" in lowered:
        return "目标主机拒绝连接；SSH 服务、端口或设备启动状态异常。"
    if "could not resolve hostname" in lowered or "temporary failure in name resolution" in lowered:
        return "目标地址解析失败；核对 IP/主机名配置。"
    if "no space left on device" in lowered or "not enough space" in lowered or "磁盘空间不足" in text or "空间不足" in text:
        return "目标磁盘空间不足；清理远端空间或更换保存目录。"
    if "no such file or directory" in lowered:
        line = _first_matching(lines, "no such file or directory")
        return f"目标文件或目录不存在：{line}" if line else "目标文件或目录不存在。"
    if "command not found" in lowered:
        line = _first_matching(lines, "command not found")
        command = _missing_command_name(line)
        detail = f"：{command}" if command else ""
        return f"远端缺少命令{detail}；核对依赖安装或镜像版本。"
    if "service not found" in lowered or "service not available" in lowered or "failed to call service" in lowered:
        line = _first_matching(lines, "service")
        return f"ROS 服务不可用；核对节点状态、ROS_DOMAIN_ID/RMW。{line}".rstrip()
    if "未就绪" in text and ("service" in lowered or "服务" in text):
        line = _first_matching(lines, "未就绪")
        return f"目标服务未就绪；节点未启动或已异常退出。{line}".rstrip()
    if "syntax error near unexpected token" in lowered:
        line = _first_matching(lines, "syntax error near unexpected token")
        return f"远端执行脚本语法错误；命令参数或路径拼接异常。{line}".rstrip()
    if "modulenotfounderror" in lowered or "no module named" in lowered:
        line = _first_matching(lines, "No module named") or _first_matching(lines, "ModuleNotFoundError")
        return f"Python 依赖缺失：{line}"
    return ""


def _last_error_lines(lines: list[str], is_important: Callable[[str], bool]) -> str:
    selected = [
        line
        for line in lines
        if is_important(line)
        and not line.startswith("$ ")
    ]
    if not selected:
        return ""
    return "；".join(selected[-3:])


def _first_matching(lines: list[str], needle: str) -> str:
    lowered = needle.lower()
    for line in lines:
        if lowered in line.lower():
            return line.strip()
    return ""


def _missing_command_name(line: str) -> str:
    if not line:
        return ""
    before, _sep, _after = line.partition("command not found")
    parts = [part.strip() for part in before.split(":") if part.strip()]
    if not parts:
        return ""
    command = parts[-1]
    return command if command not in {"bash", "sh", "line"} else ""
