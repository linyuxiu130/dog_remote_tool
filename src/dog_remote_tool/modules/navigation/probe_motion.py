from __future__ import annotations

from dog_remote_tool.core.shell import quote


def topic_count_assignments(topic: str, key: str, timeout: int | float = 2) -> str:
    return (
        f"{key}_TOPIC_INFO=$(timeout {timeout}s ros2 topic info {quote(topic)} --no-daemon 2>/dev/null || true); "
        f"{key}_PUBLISHERS=$(printf '%s\\n' \"${key}_TOPIC_INFO\" | "
        "awk -F': ' '/Publisher count:/ {print $2; found=1} END{if(!found) print 0}'); "
        f"{key}_SUBSCRIBERS=$(printf '%s\\n' \"${key}_TOPIC_INFO\" | "
        "awk -F': ' '/Subscription count:/ {print $2; found=1} END{if(!found) print 0}')"
    )


def motion_velocity_sample_shell(topic: str, key: str) -> str:
    return (
        f"{key}_VEL=; {key}_SAMPLE=; "
        f"if [ \"${{{key}_PUBLISHERS:-0}}\" -gt 0 ]; then "
        f"{key}_MSG=$(timeout 1.5s ros2 topic echo --once {quote(topic)} --no-daemon 2>/dev/null || true); "
        f"{key}_VEL=$(printf '%s\\n' \"${key}_MSG\" | awk '"
        "/^[[:space:]]*linear:/ {section=\"linear\"; next} "
        "/^[[:space:]]*angular:/ {section=\"angular\"; next} "
        "section==\"linear\" && /^[[:space:]]*x:/ {lx=$2} "
        "section==\"linear\" && /^[[:space:]]*y:/ {ly=$2} "
        "section==\"angular\" && /^[[:space:]]*z:/ {az=$2} "
        "END {if (lx != \"\" || ly != \"\" || az != \"\") printf \"vx=%s vy=%s wz=%s\", lx, ly, az}'"
        "); "
        f"{key}_SAMPLE=$(printf '%s\\n' \"${key}_MSG\" | sed '/^[[:space:]]*$/d' | head -40 | tr '\\n' ' ' | "
        "sed 's/[[:space:]][[:space:]]*/ /g' | cut -c1-240); "
        "fi; "
        f"echo {key}_VEL=${{{key}_VEL:-}}; "
        f"echo {key}_SAMPLE=${{{key}_SAMPLE:-}}"
    )


def motion_control_chain_probe_shell() -> str:
    topics = (
        "/navigation_cmd",
        "/handle_vel",
        "/cmd_vel",
        "/robot_roamerx/is_in_nav_control",
        "/robot_control_server/nav_pose",
        "/robot_control_server/mc_state",
    )
    checks = []
    for topic in topics:
        key = topic.strip("/").replace("/", "_").upper()
        checks.append(
            f"if printf '%s\\n' \"$TOPIC_LIST\" | grep -Fx -- {quote(topic)} >/dev/null; then "
            f"{topic_count_assignments(topic, key, timeout=2)}; "
            f"else {key}_PUBLISHERS=0; {key}_SUBSCRIBERS=0; fi; "
            f"echo {key}_PUBLISHERS=${key}_PUBLISHERS; "
            f"echo {key}_SUBSCRIBERS=${key}_SUBSCRIBERS"
        )
        if topic in {"/navigation_cmd", "/handle_vel", "/cmd_vel"}:
            checks.append(motion_velocity_sample_shell(topic, key))
    return "; ".join(checks)
