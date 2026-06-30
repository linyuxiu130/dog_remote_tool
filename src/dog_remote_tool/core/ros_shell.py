from __future__ import annotations

from dog_remote_tool.core.shell import quote


def topic_publisher_count(topic: str, timeout: int | float = 1) -> str:
    return (
        f"timeout {timeout}s ros2 topic info {quote(topic)} --no-daemon 2>/dev/null | "
        "awk -F': ' '/Publisher count:/ {print $2; found=1} END{if(!found) print 0}'"
    )


def topic_subscription_count(topic: str, timeout: int | float = 1) -> str:
    return (
        f"timeout {timeout}s ros2 topic info {quote(topic)} --no-daemon 2>/dev/null | "
        "awk -F': ' '/Subscription count:/ {print $2; found=1} END{if(!found) print 0}'"
    )


def service_exists(service_name: str, timeout: int | float = 3) -> str:
    return (
        f"timeout {timeout}s ros2 service list --no-daemon 2>/dev/null | "
        f"awk -v target={quote(service_name)} '$0==target {{found=1}} END {{exit !found}}'"
    )
