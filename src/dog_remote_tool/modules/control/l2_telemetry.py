from __future__ import annotations

from dog_remote_tool.core.network_routes import with_route_repair
from dog_remote_tool.core.profiles import ProductProfile
from dog_remote_tool.core.shell import quote, remote_env, ssh_prefix_command


def build_l2_body_telemetry_stream_command(target: ProductProfile, interval: float) -> str:
    remote_py = r"""
import json
import math
import re
import os
import subprocess
import time

TOPICS = (
    "/robot_control_server/mc_state",
    "/odom",
    "/odom/localization_odom",
)

def emit(payload):
    print(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), flush=True)

def number(text):
    if text is None:
        return None
    text = str(text).strip().strip("'\"")
    match = re.search(r"[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?", text)
    if not match:
        return None
    try:
        value = float(match.group(0))
    except ValueError:
        return None
    return value if math.isfinite(value) else None

def topic_list():
    try:
        proc = subprocess.run(["ros2", "topic", "list"], text=True, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=5)
    except Exception:
        return set()
    return {line.strip() for line in proc.stdout.splitlines() if line.strip()}

def choose_topic():
    available = topic_list()
    for topic in TOPICS:
        if topic in available:
            return topic
    return TOPICS[0]

def parse_doc(doc):
    scalars = {}
    vectors = {}
    stack = []
    for raw in doc.splitlines():
        if not raw.strip() or raw.strip() == "---":
            continue
        indent = len(raw) - len(raw.lstrip(" "))
        stripped = raw.strip()
        if stripped.startswith("- "):
            while stack and indent < stack[-1][0]:
                stack.pop()
            value = number(stripped[2:])
            if value is not None and stack:
                vectors.setdefault(".".join(item[1] for item in stack), []).append(value)
            continue
        while stack and indent <= stack[-1][0]:
            stack.pop()
        if stripped.endswith(":") and ":" not in stripped[:-1]:
            stack.append((indent, stripped[:-1]))
            continue
        if ":" not in stripped:
            continue
        key, raw_value = stripped.split(":", 1)
        key = key.strip()
        value = number(raw_value)
        path = ".".join([item[1] for item in stack] + [key])
        if value is not None:
            scalars[path] = value
    return scalars, vectors

def first_scalar(scalars, names):
    for name in names:
        if name in scalars:
            return scalars[name]
    for suffix in names:
        for key, value in scalars.items():
            if key.endswith("." + suffix) or key == suffix:
                return value
    return None

def first_vector(vectors, names, index):
    for name in names:
        for key, values in vectors.items():
            if (key.endswith("." + name) or key == name) and len(values) > index:
                return values[index]
    return None

def extract_telemetry(doc, topic):
    scalars, vectors = parse_doc(doc)
    linear_x = first_scalar(scalars, (
        "twist.twist.linear.x", "twist.linear.x", "linear.x",
        "v_body.x", "v_world.x", "v.x", "velocity.x", "linear_velocity.x",
    ))
    linear_y = first_scalar(scalars, (
        "twist.twist.linear.y", "twist.linear.y", "linear.y",
        "v_body.y", "v_world.y", "v.y", "velocity.y", "linear_velocity.y",
    ))
    angular_z = first_scalar(scalars, (
        "twist.twist.angular.z", "twist.angular.z", "angular.z",
        "w.z", "omega.z", "omega_body.z", "gyro.z", "body_gyro.z",
        "angular_velocity.z", "yaw_rate", "yaw_vel",
    ))
    if linear_x is None:
        linear_x = first_vector(vectors, ("v_body", "v_world", "v", "velocity", "linear_velocity"), 0)
    if linear_y is None:
        linear_y = first_vector(vectors, ("v_body", "v_world", "v", "velocity", "linear_velocity"), 1)
    if angular_z is None:
        angular_z = first_vector(vectors, ("w", "omega", "omega_body", "gyro", "body_gyro", "angular_velocity"), 2)
    if linear_x is None and linear_y is None and angular_z is None:
        return None
    return {
        "type": "telemetry",
        "topic": topic,
        "linear_x": linear_x,
        "linear_y": linear_y,
        "angular_z": angular_z,
    }

def stream_topic(topic, interval, max_doc_lines):
    proc = subprocess.Popen(
        ["ros2", "topic", "echo", topic],
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
        bufsize=1,
    )
    doc = []
    last_emit = 0.0
    try:
        for line in proc.stdout:
            if line.strip() == "---":
                if doc:
                    now = time.monotonic()
                    if now - last_emit >= interval:
                        payload = extract_telemetry("".join(doc), topic)
                        if payload:
                            emit(payload)
                            last_emit = now
                    doc = []
                continue
            doc.append(line)
            if len(doc) > max_doc_lines:
                emit({"type": "log", "message": f"drop oversized telemetry document topic={topic}"})
                doc = []
    finally:
        try:
            proc.terminate()
        except Exception:
            pass
        try:
            return proc.wait(timeout=2)
        except subprocess.TimeoutExpired:
            proc.kill()
            return proc.wait(timeout=2)

interval = float(os.environ.get("DOG_REMOTE_L2_TELEMETRY_INTERVAL", "0.25"))
max_doc_lines = max(50, min(int(os.environ.get("DOG_REMOTE_L2_TELEMETRY_MAX_DOC_LINES", "400")), 2000))
topic = choose_topic()
emit({"type": "ready", "topic": topic})
failures = 0
while True:
    started = time.monotonic()
    code = stream_topic(topic, interval, max_doc_lines)
    if time.monotonic() - started < 2.0:
        failures += 1
    else:
        failures = 0
    if failures >= 5:
        emit({"type": "error", "message": f"telemetry stream exited too often code={code}"})
        raise SystemExit(2)
    retry_delay = min(5.0, 1.0 + failures)
    emit({"type": "log", "message": f"telemetry stream exited code={code}; retrying in {retry_delay:.1f}s"})
    time.sleep(retry_delay)
    topic = choose_topic()
"""
    remote_script = f"""
set -e
{remote_env(target)}
source /opt/robot/install/setup.bash >/dev/null 2>&1 || true
telemetry_py="${{TMPDIR:-/tmp}}/dog_remote_l2_body_telemetry_$$.py"
cat > "$telemetry_py" <<'PY'
{remote_py.rstrip()}
PY
trap 'rm -f "$telemetry_py"' EXIT
export DOG_REMOTE_L2_TELEMETRY_INTERVAL={interval}
export DOG_REMOTE_L2_TELEMETRY_MAX_DOC_LINES=400
exec python3 -u "$telemetry_py"
"""
    command = (
        f"{ssh_prefix_command(target)} {quote('bash -lc ' + quote(remote_script))}"
    )
    return with_route_repair(target, command)
