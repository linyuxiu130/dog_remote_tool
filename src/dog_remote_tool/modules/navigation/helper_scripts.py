from __future__ import annotations


MODE_SWITCH_TOPIC = "/robot_roamerx/is_in_nav_control"
MODE_SWITCH_STATE_PID = "/tmp/dog_remote_nav_control_state_pub.pid"
START_NAV_HELPER_SCRIPT = "/tmp/dog_remote_start_navigation_helper.py"
START_NAV_HELPER_PID = "/tmp/dog_remote_start_navigation_helper.pid"
START_NAV_HELPER_FIFO = "/tmp/dog_remote_start_navigation.fifo"
START_NAV_HELPER_LOG = "/tmp/dog_remote_start_navigation_helper.log"


def _start_navigation_helper_python() -> str:
    return r"""
import base64
import os
import select
import stat

import rclpy
import yaml
from robots_dog_msgs.msg import StartNavigation
from rosidl_runtime_py.set_message import set_message_fields

FIFO = "/tmp/dog_remote_start_navigation.fifo"
PID = "/tmp/dog_remote_start_navigation_helper.pid"
TOPIC = "/start_navigation"


def ensure_fifo():
    try:
        mode = os.stat(FIFO).st_mode
        if not stat.S_ISFIFO(mode):
            os.unlink(FIFO)
    except FileNotFoundError:
        pass
    if not os.path.exists(FIFO):
        os.mkfifo(FIFO, 0o666)


def publish_payload(node, publisher, encoded):
    text = base64.b64decode(encoded.encode("ascii")).decode("utf-8")
    data = yaml.safe_load(text) or {}
    msg = StartNavigation()
    set_message_fields(msg, data)
    publisher.publish(msg)
    rclpy.spin_once(node, timeout_sec=0.0)


def main():
    ensure_fifo()
    with open(PID, "w", encoding="utf-8") as pid_file:
        pid_file.write(str(os.getpid()))
    rclpy.init()
    node = rclpy.create_node("dog_remote_tool_start_navigation")
    publisher = node.create_publisher(StartNavigation, TOPIC, 10)
    fd = os.open(FIFO, os.O_RDWR | os.O_NONBLOCK)
    buffer = ""
    try:
        while rclpy.ok():
            rclpy.spin_once(node, timeout_sec=0.0)
            readable, _, _ = select.select([fd], [], [], 0.02)
            if not readable:
                continue
            try:
                chunk = os.read(fd, 65536).decode("utf-8", errors="ignore")
            except BlockingIOError:
                continue
            if not chunk:
                continue
            buffer += chunk
            while "\n" in buffer:
                line, buffer = buffer.split("\n", 1)
                encoded = line.strip()
                if not encoded:
                    continue
                try:
                    publish_payload(node, publisher, encoded)
                    node.get_logger().info("published StartNavigation payload")
                except Exception as exc:
                    node.get_logger().error(f"failed to publish StartNavigation payload: {exc}")
    finally:
        os.close(fd)
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
""".strip()
