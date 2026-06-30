from __future__ import annotations

from dog_remote_tool.core.shell import quote


def navigation_graph_status_probe_shell() -> str:
    script = r"""
import shlex
import time

import rclpy


def emit(name, value):
    print(f"{name}={shlex.quote(str(value))}")


def main():
    rclpy.init()
    node = rclpy.create_node("dog_remote_nav_graph_probe")
    try:
        time.sleep(0.5)
        start_subs = node.get_subscriptions_info_by_topic("/start_navigation")
        emit("START_NAV_SUBSCRIBERS", len(start_subs))
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        emit("GRAPH_PROBE_ERROR", exc)
        sys.exit(0)
""".strip()
    command = f"timeout 6s python3 -c {quote(script)} 2>/dev/null || true"
    return (
        f"eval \"$({command})\"; "
        "echo START_NAV_SUBSCRIBERS=$START_NAV_SUBSCRIBERS; "
        "echo GRAPH_PROBE_ERROR=${GRAPH_PROBE_ERROR:-}"
    )
