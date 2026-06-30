from __future__ import annotations

import shlex
import subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Callable

from dog_remote_tool.core.profiles import ProductProfile
from dog_remote_tool.modules.bag import remote_topics as bag_remote_topics
from dog_remote_tool.modules.bag import topic_check as bag_topic_check


SshCommand = Callable[..., subprocess.CompletedProcess]
ProgressCallback = Callable[[int, int, str], None]


def topic_probe_env_lines(profile: ProductProfile, ros_env_lines: list[str]) -> list[str]:
    env_lines = list(ros_env_lines)
    env_lines.extend(
        [
            "[ -f /opt/robot/robot_nav/install/setup.bash ] && source /opt/robot/robot_nav/install/setup.bash || true",
            "[ -f /opt/robot/robot_slam/install/setup.bash ] && source /opt/robot/robot_slam/install/setup.bash || true",
            f"export ROS_DOMAIN_ID={shlex.quote(profile.ros_domain_id)}",
            f"export RMW_IMPLEMENTATION={shlex.quote(profile.rmw)}",
            "export ROS_LOCALHOST_ONLY=0",
        ]
    )
    return env_lines


def list_remote_topics(
    profile: ProductProfile,
    ros_env_lines: list[str],
    ssh_bash_command: SshCommand,
) -> list[dict]:
    script = bag_remote_topics.list_remote_topics_script(topic_probe_env_lines(profile, ros_env_lines))
    result = ssh_bash_command(script, timeout=30)
    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip() or f"return code {result.returncode}"
        raise RuntimeError(detail[:500])
    return bag_remote_topics.parse_remote_topics_output(
        result.stdout,
        result.stderr,
        empty_message="远端未返回话题列表",
        failure_message="远端话题读取失败",
    )


def inspect_remote_topics(
    profile: ProductProfile,
    ros_env_lines: list[str],
    ssh_bash_command: SshCommand,
    sample_seconds: float = 1.5,
    workers: int = 16,
) -> list[dict]:
    script, _sample_seconds, _batch_size = bag_remote_topics.inspect_remote_topics_script(
        topic_probe_env_lines(profile, ros_env_lines),
        sample_seconds,
        workers,
    )
    result = ssh_bash_command(script, timeout=300)
    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip() or f"return code {result.returncode}"
        raise RuntimeError(detail[:500])
    return bag_remote_topics.parse_remote_topics_output(
        result.stdout,
        result.stderr,
        empty_message="远端未返回话题数据",
        failure_message="远端话题读取失败",
    )


def check_topics(
    topics: list[str],
    ros_env_lines: list[str],
    ssh_bash_command: SshCommand,
    log: Callable[[str], None],
    progress: ProgressCallback | None = None,
) -> tuple[list[str], list[str]]:
    units = bag_topic_check.topic_check_units(topics)
    if not units:
        return [], []
    passed: list[str] = []
    failed: list[str] = []
    with ThreadPoolExecutor(max_workers=min(4, len(units))) as executor:
        futures = [executor.submit(_check_topic_unit, unit, ros_env_lines, ssh_bash_command) for unit in units]
        for done, future in enumerate(as_completed(futures), start=1):
            result = future.result()
            if progress:
                progress(done, len(units), result["topic"])
            if result["ok"]:
                passed.append(result["short"])
            else:
                failed.append(result["short"])
                log(f"[话题检查] ✗ {result['detail']}")
    return passed, failed


def _check_single_topic(topic: str, ros_env_lines: list[str], ssh_bash_command: SshCommand) -> dict:
    hz_profile = bag_topic_check.TOPIC_CHECK_PROFILES.get(topic)
    try:
        command = bag_topic_check.build_topic_check_command(ros_env_lines, topic, hz_profile)
        result = ssh_bash_command(command, timeout=25)
        ok, short, detail = bag_topic_check.parse_topic_check_result(topic, result, hz_profile)
        return {"topic": topic, "ok": ok, "short": short, "detail": detail}
    except subprocess.TimeoutExpired:
        return {"topic": topic, "ok": False, "short": f"{topic}: 检查超时", "detail": f"{topic} -> 检查超时"}
    except Exception as exc:
        return {"topic": topic, "ok": False, "short": f"{topic}: 检查异常", "detail": f"{topic} -> {str(exc)[:200]}"}


def _check_topic_unit(unit: dict, ros_env_lines: list[str], ssh_bash_command: SshCommand) -> dict:
    if not unit["is_group"]:
        return _check_single_topic(unit["topics"][0], ros_env_lines, ssh_bash_command)
    results = [_check_single_topic(topic, ros_env_lines, ssh_bash_command) for topic in unit["topics"]]
    passed = [item for item in results if item["ok"]]
    if passed:
        return {
            "topic": unit["label"],
            "ok": True,
            "short": f"{unit['label']}: 正常",
            "detail": f"{unit['label']} -> 候选Topic通过: {', '.join(item['topic'] for item in passed)}",
        }
    return {
        "topic": unit["label"],
        "ok": False,
        "short": f"{unit['label']}: 异常",
        "detail": f"{unit['label']} -> " + "；".join(item["detail"] for item in results),
    }
