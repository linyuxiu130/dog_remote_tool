#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import selectors
import signal
import statistics
import subprocess
import sys
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from dog_remote_tool.core.profiles import get_product, product_keys  # noqa: E402
from dog_remote_tool.core.shell import ssh_command  # noqa: E402
from dog_remote_tool.modules import bag, device_status, localization, navigation  # noqa: E402
from dog_remote_tool.modules.bag import topic_check as bag_topic_check  # noqa: E402


STREAM_OPERATIONS = ("pose-stream", "plan-stream", "state-stream")
OPERATIONS = ("connection", "device-status", "bag", "bag-topic", "navigation-status", *STREAM_OPERATIONS)
DEFAULT_TOPIC = "/odom/current_pose"


def build_shell_command(profile, operation: str, map_pcd: str) -> str:
    if operation == "connection":
        return ssh_command(profile, "echo ONLINE")
    if operation == "device-status":
        return device_status.probe_command(profile).command
    if operation == "navigation-status":
        return navigation.fast_probe_status_command(profile, map_pcd)
    if operation == "pose-stream":
        return localization.pose_stream_command(profile)
    if operation == "plan-stream":
        return localization.navigation_plan_stream_command(profile)
    if operation == "state-stream":
        return localization.navigation_state_stream_command(profile)
    raise ValueError(f"unsupported shell operation: {operation}")


def stop_process_group(process: subprocess.Popen) -> None:
    if process.poll() is not None:
        return
    try:
        os.killpg(process.pid, signal.SIGTERM)
        process.wait(timeout=1)
    except Exception:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except Exception:
            pass


def run_stream_until_output(command: str, timeout: int) -> int:
    process = subprocess.Popen(
        ["bash", "-lc", command],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        start_new_session=True,
    )
    selector = selectors.DefaultSelector()
    assert process.stdout is not None
    selector.register(process.stdout, selectors.EVENT_READ)
    deadline = time.monotonic() + timeout
    try:
        while time.monotonic() < deadline:
            remaining = max(0.0, deadline - time.monotonic())
            events = selector.select(min(0.2, remaining))
            if events:
                line = process.stdout.readline()
                if line:
                    return 0
            returncode = process.poll()
            if returncode is not None:
                return int(returncode) if returncode != 0 else 1
        return 124
    finally:
        try:
            selector.unregister(process.stdout)
        except Exception:
            pass
        selector.close()
        stop_process_group(process)


def run_bag_topic_probe(profile, topics: list[str], timeout: int) -> int:
    backend = bag.BagBackend(profile)
    ok = True
    for topic in topics:
        command = bag_topic_check.build_topic_check_command(
            backend._topic_probe_env_lines(),
            topic,
            bag_topic_check.TOPIC_CHECK_PROFILES.get(topic),
        )
        result = backend.ssh_bash_command(command, timeout=timeout)
        topic_ok, _short, _detail = bag_topic_check.parse_topic_check_result(
            topic,
            result,
            bag_topic_check.TOPIC_CHECK_PROFILES.get(topic),
        )
        ok = ok and topic_ok
    return 0 if ok else 1


def run_operation(profile, operation: str, map_pcd: str, timeout: int, topics: list[str]) -> int:
    if operation == "bag":
        result = bag.BagBackend(profile).ssh_bash_command("echo BAG_ONLINE", timeout=timeout)
    elif operation == "bag-topic":
        return run_bag_topic_probe(profile, topics, timeout)
    elif operation in STREAM_OPERATIONS:
        return run_stream_until_output(build_shell_command(profile, operation, map_pcd), timeout)
    else:
        result = subprocess.run(
            ["bash", "-lc", build_shell_command(profile, operation, map_pcd)],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    return int(result.returncode)


def measure_once(profile, operation: str, map_pcd: str, timeout: int, topics: list[str]) -> tuple[int, int]:
    started_at = time.monotonic()
    try:
        returncode = run_operation(profile, operation, map_pcd, timeout, topics)
    except subprocess.TimeoutExpired:
        return int((time.monotonic() - started_at) * 1000), 124
    return int((time.monotonic() - started_at) * 1000), returncode


def summarize(values: list[int]) -> tuple[float, float, int]:
    if not values:
        return 0.0, 0.0, 0
    return statistics.mean(values), statistics.median(values), min(values)


def comparison_summary(
    off: tuple[float, float, int],
    on: tuple[float, float, int],
    off_ok: tuple[int, int] | None = None,
    on_ok: tuple[int, int] | None = None,
) -> str:
    avg_delta = off[0] - on[0]
    p50_delta = off[1] - on[1]
    best_delta = off[2] - on[2]
    avg_saved_pct = (avg_delta / off[0] * 100.0) if off[0] > 0 else 0.0
    detail = f"avg_delta={avg_delta:.1f};p50_delta={p50_delta:.1f};best_delta={best_delta};avg_saved_pct={avg_saved_pct:.1f}"
    if off_ok is not None and on_ok is not None:
        detail += f";off_ok={off_ok[0]}/{off_ok[1]};on_ok={on_ok[0]}/{on_ok[1]}"
    return detail


def set_ssh_control(enabled: bool) -> str | None:
    previous = os.environ.get("DOG_REMOTE_TOOL_SSH_CONTROL")
    os.environ["DOG_REMOTE_TOOL_SSH_CONTROL"] = "1" if enabled else "0"
    return previous


def restore_ssh_control(previous: str | None) -> None:
    if previous is None:
        os.environ.pop("DOG_REMOTE_TOOL_SSH_CONTROL", None)
    else:
        os.environ["DOG_REMOTE_TOOL_SSH_CONTROL"] = previous


def run_benchmark(profile, operations: list[str], map_pcd: str, repeats: int, timeout: int, topics: list[str]) -> int:
    print("operation,ssh_control,run,elapsed_ms,returncode")
    exit_code = 0
    summaries: dict[tuple[str, str], tuple[float, float, int]] = {}
    successes: dict[tuple[str, str], tuple[int, int]] = {}
    for enabled in (False, True):
        previous = set_ssh_control(enabled)
        try:
            label = "on" if enabled else "off"
            for operation in operations:
                elapsed_values: list[int] = []
                ok_count = 0
                for index in range(1, repeats + 1):
                    elapsed_ms, returncode = measure_once(profile, operation, map_pcd, timeout, topics)
                    elapsed_values.append(elapsed_ms)
                    if returncode == 0:
                        ok_count += 1
                    exit_code = max(exit_code, 0 if returncode == 0 else 1)
                    print(f"{operation},{label},{index},{elapsed_ms},{returncode}", flush=True)
                avg_ms, p50_ms, best_ms = summarize(elapsed_values)
                summaries[(operation, label)] = (avg_ms, p50_ms, best_ms)
                successes[(operation, label)] = (ok_count, len(elapsed_values))
                print(f"{operation},{label},summary,avg={avg_ms:.1f};p50={p50_ms:.1f};best={best_ms};ok={ok_count}/{len(elapsed_values)},-", flush=True)
        finally:
            restore_ssh_control(previous)
    for operation in operations:
        off = summaries.get((operation, "off"))
        on = summaries.get((operation, "on"))
        if off is not None and on is not None:
            off_ok = successes.get((operation, "off"))
            on_ok = successes.get((operation, "on"))
            print(f"{operation},compare,summary,{comparison_summary(off, on, off_ok, on_ok)},-", flush=True)
    return exit_code


def main() -> int:
    parser = argparse.ArgumentParser(description="Benchmark Dog Remote Tool SSH ControlMaster reuse.")
    parser.add_argument("profile", choices=product_keys(), help="Product profile key")
    parser.add_argument("--operation", action="append", choices=OPERATIONS, help="Operation to measure; repeatable")
    parser.add_argument("--repeats", type=int, default=3, help="Runs per operation and SSH-control mode")
    parser.add_argument("--timeout", type=int, default=30, help="Per-run timeout seconds")
    parser.add_argument("--map-pcd", default="", help="Map PCD path for navigation-status")
    parser.add_argument("--topic", action="append", default=[], help=f"Topic for bag-topic; repeatable. Default: {DEFAULT_TOPIC}")
    args = parser.parse_args()

    profile = get_product(args.profile)
    operations = args.operation or list(OPERATIONS)
    map_pcd = args.map_pcd or navigation.default_goal_map_path(profile)
    topics = args.topic or [DEFAULT_TOPIC]
    return run_benchmark(profile, operations, map_pcd, max(1, args.repeats), max(1, args.timeout), topics)


if __name__ == "__main__":
    raise SystemExit(main())
