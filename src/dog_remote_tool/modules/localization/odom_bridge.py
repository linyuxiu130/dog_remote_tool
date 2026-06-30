from __future__ import annotations

import base64

from dog_remote_tool.core.ros_shell import topic_publisher_count
from dog_remote_tool.core.shell import quote


BRIDGE_PID = "/tmp/dog_remote_tool_odom_current_pose_bridge.pid"
BRIDGE_LOG = "/tmp/dog_remote_tool_odom_current_pose_bridge.log"
BRIDGE_SCRIPT = "/tmp/dog_remote_tool_odom_current_pose_bridge.py"


def ensure_current_pose_bridge_inner() -> str:
    bridge_code = r"""import rclpy
from nav_msgs.msg import Odometry


def main():
    rclpy.init()
    node = rclpy.create_node("dog_remote_tool_odom_current_pose_bridge")
    pub = node.create_publisher(Odometry, "/odom/current_pose", 10)

    def callback(msg):
        pub.publish(msg)

    node.create_subscription(Odometry, "/odom/localization_odom", callback, 10)
    rclpy.spin(node)
    node.destroy_node()
    rclpy.shutdown()


if __name__ == "__main__":
    main()
"""
    bridge_code_b64 = base64.b64encode(bridge_code.encode("utf-8")).decode("ascii")
    return (
        "if [ -n \"${TOPIC_LIST+x}\" ] && ! printf '%s\\n' \"$TOPIC_LIST\" | grep -Fx -- /odom/current_pose >/dev/null; then "
        "CURRENT_POSE_PUB=0; "
        f"else CURRENT_POSE_PUB=$({topic_publisher_count('/odom/current_pose')}); fi; "
        "if [ -n \"${TOPIC_LIST+x}\" ] && ! printf '%s\\n' \"$TOPIC_LIST\" | grep -Fx -- /odom/localization_odom >/dev/null; then "
        "LOCALIZATION_ODOM_PUB=0; "
        f"else LOCALIZATION_ODOM_PUB=$({topic_publisher_count('/odom/localization_odom')}); fi; "
        "if [ \"$CURRENT_POSE_PUB\" -gt 0 ]; then "
        "echo '[INFO] /odom/current_pose 已有发布者'; "
        "elif [ \"$LOCALIZATION_ODOM_PUB\" -lt 1 ]; then "
        "echo '[WARN] /odom/localization_odom 未发布，暂不能建立导航位姿桥'; "
        "else "
        f"BRIDGE_PID=; [ -f {quote(BRIDGE_PID)} ] && BRIDGE_PID=$(cat {quote(BRIDGE_PID)} 2>/dev/null || true); "
        "if [ -n \"$BRIDGE_PID\" ] && kill -0 \"$BRIDGE_PID\" 2>/dev/null; then "
        "echo '[INFO] 导航位姿桥已在运行 PID='\"$BRIDGE_PID\"; "
        "else "
        f"printf '%s' {quote(bridge_code_b64)} | base64 -d > {quote(BRIDGE_SCRIPT)}; "
        f"nohup setsid python3 {quote(BRIDGE_SCRIPT)} > {quote(BRIDGE_LOG)} 2>&1 & "
        f"echo $! > {quote(BRIDGE_PID)}; "
        "echo '[INFO] 已启动导航位姿桥 /odom/localization_odom -> /odom/current_pose PID='$(cat "
        f"{quote(BRIDGE_PID)}); "
        "fi; "
        "for i in $(seq 1 8); do "
        f"CURRENT_POSE_PUB=$({topic_publisher_count('/odom/current_pose')}); "
        "[ \"$CURRENT_POSE_PUB\" -gt 0 ] && break; "
        "sleep 0.5; "
        "done; "
        "if [ \"$CURRENT_POSE_PUB\" -gt 0 ]; then "
        "echo '[INFO] 导航位姿桥已就绪 /odom/current_pose 发布者='\"$CURRENT_POSE_PUB\"; "
        "else "
        f"echo '[WARN] 导航位姿桥未就绪'; tail -40 {quote(BRIDGE_LOG)} 2>/dev/null || true; "
        "fi; "
        "fi; "
    )


def current_pose_ready_check_inner(exit_code: int = 6) -> str:
    return (
        "if [ -n \"${TOPIC_LIST+x}\" ] && ! printf '%s\\n' \"$TOPIC_LIST\" | grep -Fx -- /odom/current_pose >/dev/null; then "
        "CURRENT_POSE_PUB=0; "
        f"else CURRENT_POSE_PUB=$({topic_publisher_count('/odom/current_pose')}); fi; "
        "if [ \"$CURRENT_POSE_PUB\" -lt 1 ]; then "
        "echo '[ERROR] /odom/current_pose 没有发布者，导航无法接收定位位姿'; "
        f"exit {exit_code}; "
        "fi; "
    )


def stop_current_pose_bridge_inner() -> str:
    return (
        f"BRIDGE_PID=; [ -f {quote(BRIDGE_PID)} ] && BRIDGE_PID=$(cat {quote(BRIDGE_PID)} 2>/dev/null || true); "
        "if [ -n \"$BRIDGE_PID\" ] && kill -0 \"$BRIDGE_PID\" 2>/dev/null; then "
        "PGID=$(ps -o pgid= -p \"$BRIDGE_PID\" 2>/dev/null | awk '{print $1}'); "
        "[ -n \"$PGID\" ] && kill -INT -- -\"$PGID\" 2>/dev/null || kill -INT \"$BRIDGE_PID\" 2>/dev/null || true; "
        "sleep 1; "
        "if kill -0 \"$BRIDGE_PID\" 2>/dev/null; then "
        "[ -n \"$PGID\" ] && kill -TERM -- -\"$PGID\" 2>/dev/null || kill -TERM \"$BRIDGE_PID\" 2>/dev/null || true; "
        "fi; "
        "fi; "
        f"rm -f {quote(BRIDGE_PID)}"
    )
