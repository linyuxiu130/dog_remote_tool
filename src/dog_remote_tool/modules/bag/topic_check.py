from __future__ import annotations

import re
import shlex


TOPIC_CHECK_ALTERNATIVE_GROUPS = (("/rs_rgb_img/compressed", "/rs_ir_left/compressed"),)

TOPIC_CHECK_PROFILES = {
    "/front_camera/image": {"expected_hz": 10.0, "min_hz": 8.0, "max_hz": 12.0},
    "/front_lidar": {"expected_hz": 10.0, "min_hz": 8.0, "max_hz": 12.0},
    "/front_lidar/imu": {"expected_hz": 200.0, "min_hz": 150.0, "max_hz": 250.0},
    "/rs_pointcloud": {"expected_hz": 10.0, "min_hz": 8.0, "max_hz": 12.0},
    "/rs_rgb_img/compressed": {"expected_hz": 10.0, "min_hz": 8.0, "max_hz": 12.0},
}


def topic_check_units(topics: list[str]) -> list[dict]:
    topic_set = set(topics)
    topic_to_group = {}
    for group in TOPIC_CHECK_ALTERNATIVE_GROUPS:
        selected = [topic for topic in group if topic in topic_set]
        if len(selected) >= 2:
            for topic in selected:
                topic_to_group[topic] = tuple(selected)
    units = []
    visited = set()
    for topic in topics:
        if topic in visited:
            continue
        group = topic_to_group.get(topic)
        if group:
            units.append({"label": " / ".join(group), "topics": list(group), "is_group": True})
            visited.update(group)
        else:
            units.append({"label": topic, "topics": [topic], "is_group": False})
            visited.add(topic)
    return units


def build_topic_check_command(env_lines: list[str], topic: str, hz_profile: dict | None = None) -> str:
    env_prefix = " && ".join(env_lines)
    topic_arg = shlex.quote(topic)
    steps = [
        env_prefix,
        f"ros2 topic info {topic_arg} --no-daemon -v",
        "info_rc=$?",
        '[ "$info_rc" -eq 0 ] || exit "$info_rc"',
        f"timeout 3s ros2 topic echo {topic_arg} --once --no-daemon",
        "echo_rc=$?",
        '[ "$echo_rc" -eq 0 ] || [ "$echo_rc" -eq 124 ] || exit "$echo_rc"',
    ]
    if hz_profile:
        steps.extend(
            [
                f"timeout 6s python3 -u /opt/ros/humble/bin/ros2 topic hz {topic_arg} --window 20",
                "hz_rc=$?",
                '[ "$hz_rc" -eq 0 ] || [ "$hz_rc" -eq 124 ] || exit "$hz_rc"',
            ]
        )
    return "; ".join(steps)


def topic_echo_has_message(output: str) -> bool:
    normalized = output.strip()
    if not normalized:
        return False
    if "---" in normalized or "header:" in normalized:
        return True
    lines = [line.strip() for line in normalized.splitlines() if line.strip() and not line.lstrip().startswith("WARNING:")]
    return any(line.startswith(("-", "{", "[")) or ":" in line for line in lines)


def parse_topic_check_result(topic: str, result, hz_profile: dict | None) -> tuple[bool, str, str]:
    stdout = result.stdout or ""
    stderr = result.stderr or ""
    combined = f"{stdout}\n{stderr}"
    if result.returncode not in (0, 124):
        detail = stderr.strip() or stdout.strip() or f"return code {result.returncode}"
        lowered = detail.lower()
        if any(text in lowered for text in ("unknown topic", "topic not found", "invalid topic name", "could not determine the type")):
            return False, f"{topic}: 不存在", f"{topic} -> {detail[:200]}"
        return False, f"{topic}: 异常", f"{topic} -> {detail[:200]}"
    publisher_match = re.search(r"Publisher count:\s*(\d+)", combined)
    publisher_count = int(publisher_match.group(1)) if publisher_match else None
    if publisher_count is None or publisher_count < 1:
        return False, f"{topic}: 无发布者", f"{topic} -> Publisher count异常"
    if not topic_echo_has_message(stdout):
        return False, f"{topic}: 无消息", f"{topic} -> echo未收到消息"
    if hz_profile:
        rates = [float(item) for item in re.findall(r"average rate:\s*([0-9.]+)", combined)]
        if not rates:
            return True, f"{topic}: 正常(频率未取到)", f"{topic} -> publisher与消息检查正常，但未解析到hz输出"
        hz_value = rates[-1]
        if not (hz_profile["min_hz"] <= hz_value <= hz_profile["max_hz"]):
            return False, f"{topic}: 频率异常", f"{topic} -> hz={hz_value:.2f}, 期望范围 {hz_profile['min_hz']:.1f}-{hz_profile['max_hz']:.1f}"
        return True, f"{topic}: 正常({hz_value:.1f}Hz)", f"{topic} -> 正常, hz={hz_value:.2f}"
    return True, f"{topic}: 正常", f"{topic} -> 正常"
