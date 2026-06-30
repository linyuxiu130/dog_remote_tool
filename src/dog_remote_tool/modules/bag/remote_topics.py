from __future__ import annotations

import json


LIST_REMOTE_TOPICS_PROBE = r'''
import json
import rclpy

node = None
try:
    rclpy.init()
    node = rclpy.create_node("dog_remote_topic_list_probe")
    rows = []
    for topic, types in sorted(node.get_topic_names_and_types(), key=lambda item: item[0]):
        if topic.startswith("/"):
            rows.append({"topic": topic, "type": types[0] if types else "", "hz": None, "status": "待采样"})
    print(json.dumps({"ok": True, "topics": rows}, ensure_ascii=False))
except Exception as exc:
    print(json.dumps({"ok": False, "error": str(exc)[:500], "topics": []}, ensure_ascii=False))
finally:
    if node is not None:
        node.destroy_node()
    if rclpy.ok():
        rclpy.shutdown()
'''


INSPECT_REMOTE_TOPICS_PROBE = r'''
import json
import time

import rclpy
from rosidl_runtime_py.utilities import get_message

try:
    from rclpy.qos import QoSProfile, QoSHistoryPolicy, QoSReliabilityPolicy, QoSDurabilityPolicy
except ImportError:
    from rclpy.qos import QoSProfile, HistoryPolicy as QoSHistoryPolicy
    from rclpy.qos import ReliabilityPolicy as QoSReliabilityPolicy
    from rclpy.qos import DurabilityPolicy as QoSDurabilityPolicy

SAMPLE_SECONDS = __SAMPLE_SECONDS__
BATCH_SIZE = __BATCH_SIZE__


def make_qos():
    qos = QoSProfile(depth=10)
    qos.history = QoSHistoryPolicy.KEEP_LAST
    qos.reliability = QoSReliabilityPolicy.BEST_EFFORT
    qos.durability = QoSDurabilityPolicy.VOLATILE
    return qos


rows = []
node = None

try:
    started_at = time.time()
    rclpy.init()
    node = rclpy.create_node("dog_remote_topic_hz_probe")
    topic_types = sorted(node.get_topic_names_and_types(), key=lambda item: item[0])

    for topic, types in topic_types:
        if not topic.startswith("/"):
            continue
        topic_type = types[0] if types else ""
        row = {"topic": topic, "type": topic_type, "hz": None, "status": "未取到"}
        rows.append(row)

    def make_callback(topic, stats):
        def callback(_msg):
            now = time.monotonic()
            stat = stats[topic]
            stat["count"] += 1
            if stat["first"] is None:
                stat["first"] = now
            stat["last"] = now
        return callback

    for offset in range(0, len(rows), BATCH_SIZE):
        batch = rows[offset:offset + BATCH_SIZE]
        stats = {}
        subscriptions = []

        for row in batch:
            topic_type = row["type"]
            if not topic_type:
                row["status"] = "类型未知"
                continue
            try:
                msg_type = get_message(topic_type)
                stats[row["topic"]] = {"count": 0, "first": None, "last": None}
                subscriptions.append(
                    node.create_subscription(msg_type, row["topic"], make_callback(row["topic"], stats), make_qos())
                )
            except Exception as exc:
                row["status"] = f"订阅失败: {str(exc)[:60]}"

        deadline = time.monotonic() + SAMPLE_SECONDS
        while time.monotonic() < deadline:
            rclpy.spin_once(node, timeout_sec=0.05)

        for subscription in subscriptions:
            node.destroy_subscription(subscription)

        time.sleep(0.05)

        for row in batch:
            stat = stats.get(row["topic"])
            if not stat:
                continue
            count = stat["count"]
            row["samples"] = count
            if count >= 2 and stat["first"] is not None and stat["last"] is not None and stat["last"] > stat["first"]:
                row["hz"] = round((count - 1) / (stat["last"] - stat["first"]), 2)
                row["status"] = "正常"
            elif count == 1:
                row["status"] = "采样不足"
            else:
                row["status"] = "未取到"

    print(json.dumps({
        "ok": True,
        "elapsed": round(time.time() - started_at, 1),
        "sample_seconds": SAMPLE_SECONDS,
        "batch_size": BATCH_SIZE,
        "topics": rows,
    }, ensure_ascii=False))
except Exception as exc:
    print(json.dumps({"ok": False, "error": str(exc)[:500], "topics": []}, ensure_ascii=False))
finally:
    if node is not None:
        node.destroy_node()
    if rclpy.ok():
        rclpy.shutdown()
'''


def clamp_inspect_options(sample_seconds: float, workers: int) -> tuple[float, int]:
    return max(0.5, min(10.0, float(sample_seconds))), max(4, min(32, int(workers)))


def wrap_python_probe(env_lines: list[str], probe_script: str) -> str:
    return "\n".join(env_lines) + "\npython3 - <<'PY'\n" + probe_script + "\nPY\n"


def list_remote_topics_script(env_lines: list[str]) -> str:
    return wrap_python_probe(env_lines, LIST_REMOTE_TOPICS_PROBE)


def inspect_remote_topics_script(env_lines: list[str], sample_seconds: float = 1.5, workers: int = 16) -> tuple[str, float, int]:
    sample_seconds, batch_size = clamp_inspect_options(sample_seconds, workers)
    probe_script = INSPECT_REMOTE_TOPICS_PROBE.replace("__SAMPLE_SECONDS__", str(sample_seconds))
    probe_script = probe_script.replace("__BATCH_SIZE__", str(batch_size))
    return wrap_python_probe(env_lines, probe_script), sample_seconds, batch_size


def parse_remote_topics_output(stdout: str, stderr: str = "", *, empty_message: str, failure_message: str) -> list[dict]:
    json_lines = [line for line in stdout.splitlines() if line.strip().startswith("{")]
    if not json_lines:
        raise RuntimeError((stdout or stderr or empty_message)[:500])
    payload = json.loads(json_lines[-1])
    if not payload.get("ok"):
        raise RuntimeError(payload.get("error") or failure_message)
    return payload.get("topics", [])
