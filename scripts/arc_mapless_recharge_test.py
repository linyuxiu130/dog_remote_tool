#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import re
import select
import signal
import subprocess
import sys
import time
import unicodedata
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from dog_remote_tool.core.parsers import parse_key_values
from dog_remote_tool.core.profiles import ProductProfile, get_product
from dog_remote_tool.modules import mapping
from dog_remote_tool.modules import navigation
from dog_remote_tool.modules.device_status import power


DEFAULT_COUNT = 50
DEFAULT_DEVICE = "zg_lidar_nx"
TEST_TITLE = "无图回充测试"
DOCK_PHASE = "无图回充"
DEFAULT_STATUS_INTERVAL = 1.0
DEFAULT_UNDOCK_TIMEOUT = 120
DEFAULT_UNDOCK_RETRIES = 1
DEFAULT_RESET_EVIDENCE_TIMEOUT = 12
DEFAULT_SETTLE_SECONDS = 2.0
ARC_ACTION_MONITOR_SECONDS_MAX = 120
STOP_COMMANDS = {"stop", "q", "quit", "exit", "停止"}
STOP_REQUESTED = False
STOP_REASON = ""
ACTIVE_PROGRESS: Progress | None = None
ARC_STATUS_RE = re.compile(r"\[INFO\]\s+(?:当前状态|状态|停止清理前状态|停止清理状态):\s+alg=(\S+)\s+dock=(\S+)")
ARC_ERROR_RE = re.compile(r'\[ERROR\]\s+(?:停止清理\s+)?ARC 错误通知:.*"code":\s*(\d+).*"description":\s*"([^"]+)"')
ARC_ERROR_TEXT = {
    "13136": "定位/传感数据不完整",
    "13699": "粗对准失败",
    "13708": "出桩/接触失败",
}

DEVICE_OPTIONS = (
    ("zg_lidar_nx", "中狗激光版 NX", "中狗默认"),
    ("zg_surround_s100", "中狗环视版 S100", "中狗环视"),
    ("xg2_s100", "小狗二代 S100", "小狗二代"),
)


@dataclass
class Progress:
    total: int
    started_at: float
    status_interval: float = DEFAULT_STATUS_INTERVAL
    completed: int = 0
    success: int = 0
    failed: int = 0
    current_round: int = 0
    phase: str = "准备"
    arc_alg: str = "未知"
    arc_dock: str = "未知"
    phase_started_at: float = 0.0
    last_status_printed_at: float = 0.0
    status_line_visible: bool = False
    status_line_count: int = 0
    last_warning: str = "无"


@dataclass
class CommandResult:
    returncode: int
    output: str
    elapsed: float


def request_stop(reason: str) -> None:
    global STOP_REASON, STOP_REQUESTED
    if not STOP_REQUESTED:
        STOP_REASON = reason
        STOP_REQUESTED = True
        clear_status_line(ACTIVE_PROGRESS)
        print(f"[停止] 已收到停止请求：{reason}。当前动作结束后会执行出桩清理。")


def stop_requested() -> bool:
    return STOP_REQUESTED


def stop_reason() -> str:
    return STOP_REASON or "手动停止"


def format_duration(seconds: float) -> str:
    seconds = max(0, int(seconds))
    hours, remainder = divmod(seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"


def success_rate(success: int, completed: int) -> float:
    if completed <= 0:
        return 0.0
    return success * 100.0 / completed


def display_width(text: object) -> int:
    width = 0
    for char in str(text):
        width += 2 if unicodedata.east_asian_width(char) in ("F", "W") else 1
    return width


def pad(text: object, width: int, align: str = "left") -> str:
    text = str(text)
    spaces = max(0, width - display_width(text))
    if align == "right":
        return " " * spaces + text
    return text + " " * spaces


def row(cols: list[object], widths: list[int], aligns: list[str]) -> str:
    return "  ".join(pad(col, width, align) for col, width, align in zip(cols, widths, aligns))


def arc_state_text(progress: Progress) -> str:
    if progress.arc_alg == "Charging" or progress.arc_dock == "Charging":
        return "充电中"
    if progress.arc_alg != "未知" or progress.arc_dock != "未知":
        return f"alg={progress.arc_alg} dock={progress.arc_dock}"
    return "未知"


def status_text(progress: Progress) -> str:
    now = time.time()
    rate = success_rate(progress.success, progress.completed)
    return " | ".join(
        (
            f"进度 {progress.completed}/{progress.total}",
            f"当前第 {progress.current_round}/{progress.total}",
            f"动作 {progress.phase}",
            f"ARC {arc_state_text(progress)}",
            f"总用时 {format_duration(now - progress.started_at)}",
            f"阶段用时 {format_duration(now - progress.phase_started_at)}",
            f"成功 {progress.success} 失败 {progress.failed} 成功率 {rate:.1f}%",
            f"最近告警 {progress.last_warning}",
        )
    )


def render_status(progress: Progress) -> str:
    now = time.time()
    rate = success_rate(progress.success, progress.completed)
    widths = [10, 16, 20, 12]
    aligns = ["left", "left", "left", "right"]
    return "\n".join(
        [
            f"{TEST_TITLE}  {time.strftime('%H:%M:%S')}",
            "",
            row(["项目", "进度", "状态", "用时"], widths, aligns),
            row(
                [
                    "轮次",
                    f"{progress.completed}/{progress.total}",
                    f"当前第 {progress.current_round}/{progress.total}",
                    format_duration(now - progress.started_at),
                ],
                widths,
                aligns,
            ),
            row(
                [
                    "动作",
                    progress.phase,
                    f"ARC {arc_state_text(progress)}",
                    format_duration(now - progress.phase_started_at),
                ],
                widths,
                aligns,
            ),
            row(
                [
                    "结果",
                    f"成功 {progress.success}",
                    f"失败 {progress.failed}",
                    f"{rate:.1f}%",
                ],
                widths,
                aligns,
            ),
            row(
                [
                    "告警",
                    progress.last_warning,
                    "",
                    "",
                ],
                widths,
                aligns,
            ),
            "",
            "停止：输入 stop 回车，或按 Ctrl+C",
        ]
    )


def print_status_line(progress: Progress, *, force: bool = False) -> None:
    now = time.time()
    interactive = sys.stdout.isatty()
    if not force:
        if not interactive:
            return
        if progress.status_interval <= 0:
            return
        if now - progress.last_status_printed_at < progress.status_interval:
            return
    progress.last_status_printed_at = now
    text = render_status(progress)
    if interactive:
        if progress.status_line_count:
            print(f"\033[{progress.status_line_count}F", end="")
        for line in text.splitlines():
            print(f"\r\033[K{line}")
        progress.status_line_visible = True
        progress.status_line_count = len(text.splitlines())
        sys.stdout.flush()
    else:
        print(f"[状态] {status_text(progress)}")


def clear_status_line(progress: Progress | None = None) -> None:
    if progress is not None and not progress.status_line_visible:
        return
    if not sys.stdout.isatty():
        return
    if progress is not None and progress.status_line_count:
        print(f"\033[{progress.status_line_count}F", end="")
        for _ in range(progress.status_line_count):
            print("\r\033[K")
        progress.status_line_count = 0
        progress.status_line_visible = False
        sys.stdout.flush()
        return
    sys.stdout.write("\r" + " " * 220 + "\r")
    sys.stdout.flush()
    if progress is not None:
        progress.status_line_visible = False


def set_phase(progress: Progress, phase: str) -> None:
    progress.phase = phase
    progress.phase_started_at = time.time()
    print_status_line(progress, force=True)


def update_arc_status(progress: Progress, alg: str, dock: str) -> None:
    progress.arc_alg = alg
    progress.arc_dock = dock
    print_status_line(progress, force=True)


def update_arc_status_from_values(progress: Progress, values: dict[str, str]) -> None:
    alg = values.get("ARC_APP_ALG_STATUS") or values.get("ARC_TEXT") or progress.arc_alg
    dock = values.get("ARC_APP_DOCK_STATUS") or values.get("ARC_DOCK_TEXT") or progress.arc_dock
    update_arc_status(progress, alg, dock)


def update_warning(progress: Progress, warning: str) -> None:
    progress.last_warning = warning
    print_status_line(progress, force=True)


def arc_error_text(code: str, description: str) -> str:
    return f"{code} {ARC_ERROR_TEXT.get(code, description)}"


def undock_reset_verified(values: dict[str, str]) -> bool:
    if not values:
        return False
    app_alg = values.get("ARC_APP_ALG_STATUS", "")
    app_dock = values.get("ARC_APP_DOCK_STATUS", "")
    if app_alg or app_dock:
        return app_alg != "Charging" and app_dock != "Charging"
    arc_state = values.get("ARC_STATE", "")
    arc_text = values.get("ARC_TEXT", "")
    dock_state = values.get("ARC_DOCK_STATE", "")
    dock_text = values.get("ARC_DOCK_TEXT", "")
    if arc_state or arc_text or dock_state or dock_text:
        return arc_state != "7" and arc_text != "充电中" and dock_state != "2" and dock_text != "充电中"
    return values.get("DOG_REMOTE_CHARGING") not in {"1", "true", "True", "yes", "charging"}


def poll_stop_command() -> bool:
    if not sys.stdin.isatty():
        return False
    try:
        ready, _, _ = select.select([sys.stdin], [], [], 0)
    except (OSError, ValueError):
        return False
    if not ready:
        return False
    line = sys.stdin.readline()
    if line.strip().lower() in STOP_COMMANDS:
        request_stop("运行中输入 stop")
        return True
    return False


def is_charging(values: dict[str, str]) -> bool:
    return (
        values.get("ARC_DOCK_STATE") == "2"
        or values.get("ARC_STATE") == "7"
        or values.get("ARC_DOCK_TEXT") == "充电中"
        or values.get("ARC_TEXT") == "充电中"
        or values.get("ARC_APP_ALG_STATUS") == "Charging"
        or values.get("ARC_APP_DOCK_STATUS") == "Charging"
        or values.get("DOG_REMOTE_CHARGING") in {"1", "true", "True", "yes", "charging"}
    )


def has_arc_charge_state(values: dict[str, str]) -> bool:
    for key in (
        "ARC_DOCK_STATE",
        "ARC_STATE",
        "ARC_DOCK_TEXT",
        "ARC_TEXT",
        "ARC_APP_ALG_STATUS",
        "ARC_APP_DOCK_STATUS",
    ):
        value = values.get(key, "")
        if value and value not in {"无数据", "未知"}:
            return True
    return False


def charging_evidence(values: dict[str, str]) -> list[str]:
    evidence: list[str] = []
    if values.get("ARC_DOCK_STATE") == "2" or values.get("ARC_DOCK_TEXT") == "充电中":
        evidence.append(f"/arc/dock_state={values.get('ARC_DOCK_STATE', '')}({values.get('ARC_DOCK_TEXT', '')})")
    if values.get("ARC_STATE") == "7" or values.get("ARC_TEXT") == "充电中":
        evidence.append(f"/arc/arc_state={values.get('ARC_STATE', '')}({values.get('ARC_TEXT', '')})")
    if values.get("ARC_APP_ALG_STATUS") == "Charging":
        evidence.append("get_arc_alg_status=Charging")
    if values.get("ARC_APP_DOCK_STATUS") == "Charging":
        evidence.append("get_arc_dock_status=Charging")
    if values.get("DOG_REMOTE_CHARGING") in {"1", "true", "True", "yes", "charging"}:
        battery = values.get("DOG_REMOTE_BATTERY", "")
        suffix = f", battery={battery}%" if battery and battery != "UNKNOWN" else ""
        evidence.append(f"DOG_REMOTE_CHARGING=1{suffix}")
    return evidence


def evidence_text(values: dict[str, str]) -> str:
    evidence = charging_evidence(values)
    if evidence:
        return "；".join(evidence)
    return "未看到充电证据；" + compact_status(values)


def compact_status(values: dict[str, str]) -> str:
    if not values:
        return "无状态"
    parts = []
    for key in (
        "ARC_DOCK_TEXT",
        "ARC_TEXT",
        "ARC_APP_ALG_STATUS",
        "ARC_APP_DOCK_STATUS",
        "DOG_REMOTE_BATTERY",
        "DOG_REMOTE_CHARGING",
        "ARC_DOCK_ERROR",
        "ARC_DOCK_ERROR_MSG",
    ):
        value = values.get(key, "")
        if value:
            parts.append(f"{key}={value}")
    return " ".join(parts) if parts else "无关键状态"


def run_command_streaming(command: str, progress: Progress, log_prefix: str = "[远端]") -> CommandResult:
    started_at = time.time()
    proc = subprocess.Popen(
        ["bash", "-lc", command],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
        start_new_session=True,
    )
    assert proc.stdout is not None
    output_parts: list[str] = []
    last_remote_line = ""
    repeat_count = 0

    def print_remote_line(raw_line: str) -> None:
        nonlocal last_remote_line, repeat_count
        line = raw_line.rstrip()
        status_match = ARC_STATUS_RE.search(line)
        if status_match:
            update_arc_status(progress, status_match.group(1), status_match.group(2))
            return
        error_match = ARC_ERROR_RE.search(line)
        if error_match:
            update_warning(progress, arc_error_text(error_match.group(1), error_match.group(2)))
            return
        if line.startswith("[ERROR] ARC 动作进入失败状态。"):
            update_warning(progress, "ARC 动作进入失败状态")
            return
        if (
            line.startswith("[INFO] 系统应用通道响应:")
            or line.startswith("[INFO] 已发送系统 ARC 动作:")
            or line.startswith("[INFO] 响应:")
            or line.startswith("[INFO] 回充成功")
            or line.startswith("[INFO] 出桩成功")
            or line.startswith("[INFO] 停止清理出桩完成")
            or line.startswith("[INFO] 已发送 stop_arc")
        ):
            return
        if line == last_remote_line:
            repeat_count += 1
            return
        if repeat_count:
            clear_status_line(progress)
            print(f"{log_prefix} 上一条重复 {repeat_count} 次")
            repeat_count = 0
        clear_status_line(progress)
        print(f"{log_prefix} {line}")
        last_remote_line = line

    while True:
        try:
            ready, _, _ = select.select([proc.stdout], [], [], 0.5)
        except KeyboardInterrupt:
            request_stop("Ctrl+C")
            try:
                os.killpg(proc.pid, signal.SIGINT)
            except ProcessLookupError:
                pass
            except OSError:
                proc.terminate()
            ready = []
        if ready:
            line = proc.stdout.readline()
            if line:
                output_parts.append(line)
                print_remote_line(line)
        poll_stop_command()
        print_status_line(progress)
        if proc.poll() is not None:
            break
    tail = proc.stdout.read()
    if tail:
        output_parts.append(tail)
        for line in tail.splitlines():
            print_remote_line(line)
    if repeat_count:
        clear_status_line(progress)
        print(f"{log_prefix} 上一条重复 {repeat_count} 次")
    return CommandResult(proc.returncode or 0, "".join(output_parts), time.time() - started_at)


def run_command_capture(command: str, timeout: int = 30) -> CommandResult:
    started_at = time.time()
    result = subprocess.run(
        ["bash", "-lc", command],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=timeout,
        check=False,
        start_new_session=True,
    )
    return CommandResult(result.returncode, result.stdout, time.time() - started_at)


def sleep_with_progress(seconds: float, progress: Progress) -> None:
    deadline = time.time() + max(0.0, seconds)
    while time.time() < deadline:
        if poll_stop_command() or stop_requested():
            return
        print_status_line(progress)
        try:
            time.sleep(min(1.0, max(0.0, deadline - time.time())))
        except KeyboardInterrupt:
            request_stop("Ctrl+C")
            return


def choose_device(raw_device: str | None, prompt: bool, *, test_title: str = TEST_TITLE) -> ProductProfile:
    options_by_key = {key: (label, hint) for key, label, hint in DEVICE_OPTIONS}
    if raw_device:
        if raw_device not in options_by_key:
            raise SystemExit(f"未知设备: {raw_device}")
        return get_product(raw_device)
    if not prompt or not sys.stdin.isatty():
        return get_product(DEFAULT_DEVICE)

    default_index = next(index for index, item in enumerate(DEVICE_OPTIONS, 1) if item[0] == DEFAULT_DEVICE)
    print(f"请选择{test_title}设备：")
    for index, (key, label, hint) in enumerate(DEVICE_OPTIONS, 1):
        default_mark = "（默认）" if key == DEFAULT_DEVICE else ""
        print(f"  {index}. {label} [{key}] {hint}{default_mark}")
    answer = input(f"设备编号/Key，直接回车选择中狗默认 [{default_index}]: ").strip()
    if not answer:
        return get_product(DEFAULT_DEVICE)
    if answer in {"中狗", "狗"}:
        return get_product(DEFAULT_DEVICE)
    if answer.isdigit():
        index = int(answer)
        if 1 <= index <= len(DEVICE_OPTIONS):
            return get_product(DEVICE_OPTIONS[index - 1][0])
    if answer in options_by_key:
        return get_product(answer)
    raise SystemExit(f"无效设备选择: {answer}")


def confirm_start(profile: ProductProfile, args: argparse.Namespace, *, test_title: str = TEST_TITLE) -> None:
    print()
    print(f"{test_title}次数：{args.count}")
    print("测试配置：")
    print(f"  设备：{profile.label} [{profile.key}] {profile.user}@{profile.host}")
    print(f"  次数：{args.count}")
    if getattr(args, "map_pcd", ""):
        print(f"  地图：{args.map_pcd}")
    print(f"  回充超时：{args.dock_timeout}s")
    print(f"  出桩超时：{args.undock_timeout}s")
    print(f"  出桩失败重试：{args.undock_retries} 次")
    print(f"  充电证据确认超时：{args.evidence_timeout}s")
    print(f"  出桩复查超时：{args.reset_evidence_timeout}s")
    print(f"  轮次静置：{args.settle_seconds}s")
    print(f"  流程：必要时出桩复位 -> {DOCK_PHASE} -> 复查 ARC/App/电池充电证据后统计成功率")
    print("  停止：运行中输入 stop 回车，或按 Ctrl+C；脚本会先执行出桩清理再退出")
    if args.undock_after_final:
        print("  结束状态：最后一轮成功后也会出桩")
    else:
        print("  结束状态：最后一轮成功后保持充电状态")
    if args.yes or not sys.stdin.isatty():
        return
    print()
    print(f"注意：该测试会让机器人反复出桩和{test_title}，请确认现场安全、充电桩前方无遮挡。")
    answer = input("输入 start 开始测试，其他输入取消: ").strip().lower()
    if answer != "start":
        raise SystemExit("已取消")


def prompt_count_if_needed(args: argparse.Namespace, *, test_title: str = TEST_TITLE) -> None:
    if getattr(args, "count_was_provided", False) or args.yes or not sys.stdin.isatty():
        return
    answer = input(f"{test_title}次数，直接回车默认 {DEFAULT_COUNT}: ").strip()
    if not answer:
        return
    try:
        args.count = int(answer)
    except ValueError as exc:
        raise SystemExit(f"无效测试次数: {answer}") from exc


def read_arc_status(profile: ProductProfile) -> dict[str, str]:
    result = run_command_capture(mapping.arc_status_snapshot_command(profile), timeout=35)
    if result.returncode != 0:
        return {}
    return parse_key_values(result.output)


def read_battery_status(profile: ProductProfile) -> dict[str, str]:
    result = run_command_capture(power.battery_command(profile).command, timeout=20)
    if result.returncode != 0:
        return {}
    return parse_key_values(result.output)


def read_charging_evidence(profile: ProductProfile, *, include_battery: bool | None = None) -> dict[str, str]:
    values = read_arc_status(profile)
    should_read_battery = include_battery if include_battery is not None else not has_arc_charge_state(values)
    if should_read_battery:
        values.update(read_battery_status(profile))
    return values


def wait_for_charging_evidence(profile: ProductProfile, timeout_seconds: int, progress: Progress) -> dict[str, str]:
    deadline = time.time() + max(1, timeout_seconds)
    last_values: dict[str, str] = {}
    while time.time() < deadline:
        last_values = read_charging_evidence(profile)
        update_arc_status_from_values(progress, last_values)
        if is_charging(last_values):
            return last_values
        if poll_stop_command() or stop_requested():
            return last_values
        print_status_line(progress)
        try:
            time.sleep(min(2.0, max(0.0, deadline - time.time())))
        except KeyboardInterrupt:
            request_stop("Ctrl+C")
            return last_values
    fallback_values = read_charging_evidence(profile, include_battery=True)
    if fallback_values:
        update_arc_status_from_values(progress, fallback_values)
        return fallback_values
    return last_values


def wait_for_undock_reset(profile: ProductProfile, timeout_seconds: int, progress: Progress) -> dict[str, str]:
    deadline = time.time() + max(1, timeout_seconds)
    last_values: dict[str, str] = {}
    while time.time() < deadline:
        last_values = read_charging_evidence(profile)
        update_arc_status_from_values(progress, last_values)
        if undock_reset_verified(last_values):
            return last_values
        if poll_stop_command() or stop_requested():
            return last_values
        print_status_line(progress)
        try:
            time.sleep(min(2.0, max(0.0, deadline - time.time())))
        except KeyboardInterrupt:
            request_stop("Ctrl+C")
            return last_values
    fallback_values = read_charging_evidence(profile, include_battery=True)
    if fallback_values:
        update_arc_status_from_values(progress, fallback_values)
        return fallback_values
    return last_values


def run_arc_action(profile: ProductProfile, action: str, timeout_seconds: int, progress: Progress) -> CommandResult:
    spec = mapping.arc_start_action_command(profile, action, monitor_seconds=timeout_seconds)
    return run_command_streaming(spec.command, progress)


def run_dock_action(profile: ProductProfile, args: argparse.Namespace, progress: Progress) -> CommandResult:
    return run_arc_action(profile, "dock", args.dock_timeout, progress)


def run_mapped_dock_action(profile: ProductProfile, args: argparse.Namespace, progress: Progress) -> CommandResult:
    spec = navigation.start_arc_with_map_command(profile, args.map_pcd, monitor_seconds=args.dock_timeout)
    return run_command_streaming(spec.command, progress)


def release_arc_control(profile: ProductProfile, progress: Progress) -> CommandResult:
    set_phase(progress, "释放控制权")
    spec = mapping.arc_release_control_command(profile)
    return run_command_streaming(spec.command, progress, log_prefix="[清理]")


def run_undock_action(profile: ProductProfile, timeout_seconds: int, progress: Progress) -> tuple[CommandResult, CommandResult]:
    result = run_arc_action(profile, "undock", timeout_seconds, progress)
    release = release_arc_control(profile, progress)
    return result, release


def undock_attempt_count(args: argparse.Namespace) -> int:
    return max(1, int(getattr(args, "undock_retries", 0)) + 1)


def run_undock_reset_with_retries(
    profile: ProductProfile,
    args: argparse.Namespace,
    progress: Progress,
    round_no: int,
) -> tuple[bool, CommandResult, dict[str, str]]:
    attempts = undock_attempt_count(args)
    last_result = CommandResult(returncode=1, output="", elapsed=0.0)
    last_values: dict[str, str] = {}
    total_elapsed = 0.0
    for attempt in range(1, attempts + 1):
        set_phase(progress, "出桩复位" if attempt == 1 else f"出桩重试 {attempt - 1}/{attempts - 1}")
        last_result, release_result = run_undock_action(profile, args.undock_timeout, progress)
        total_elapsed += last_result.elapsed
        last_result = CommandResult(last_result.returncode, last_result.output, total_elapsed)
        clear_status_line(progress)
        if release_result.returncode != 0:
            print(f"[轮次 {round_no}/{args.count}] 出桩后控制权释放提示失败：{last_error_line(release_result.output)}")
        if last_result.returncode == 0:
            return True, last_result, last_values

        set_phase(progress, "出桩复查")
        last_values = wait_for_undock_reset(profile, args.reset_evidence_timeout, progress)
        update_arc_status_from_values(progress, last_values)
        clear_status_line(progress)
        if undock_reset_verified(last_values):
            print(
                f"[轮次 {round_no}/{args.count}] 出桩命令返回异常但复查已离桩，继续当前轮；"
                f"远端：{last_error_line(last_result.output)}；状态：{compact_status(last_values)}"
            )
            return True, last_result, last_values

        if attempt < attempts and not stop_requested():
            print(
                f"[轮次 {round_no}/{args.count}] 出桩第 {attempt}/{attempts} 次失败且复查仍在充电，准备重试；"
                f"远端：{last_error_line(last_result.output)}；状态：{compact_status(last_values)}"
            )
            continue
        break
    return False, last_result, last_values


def last_error_line(text: str) -> str:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    for line in reversed(lines):
        if "[ERROR]" in line or "[WARN]" in line:
            return line
    return lines[-1] if lines else "无输出"


def parse_args(argv: list[str], configure_parser=None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="连续无图回充测试，默认 50 次。",
        epilog="运行中可输入 stop 回车请求停止；按 Ctrl+C 也会转为停止请求，并在退出前发送 exit_charging 出桩清理。",
    )
    parser.add_argument("--count", type=int, default=None, help="测试次数，默认 50")
    parser.add_argument("--device", choices=[key for key, _label, _hint in DEVICE_OPTIONS], help="跳过设备选择提示，直接指定设备")
    parser.add_argument("--dock-timeout", type=int, default=120, help="每次无图回充等待 Charging 的超时秒数")
    parser.add_argument(
        "--undock-timeout",
        type=int,
        default=DEFAULT_UNDOCK_TIMEOUT,
        help=f"出桩复位等待完成的超时秒数，最大 {ARC_ACTION_MONITOR_SECONDS_MAX}",
    )
    parser.add_argument(
        "--undock-retries",
        type=int,
        default=DEFAULT_UNDOCK_RETRIES,
        help="出桩命令失败且复查仍在充电时的重试次数，默认 1",
    )
    parser.add_argument("--evidence-timeout", type=int, default=15, help="回充动作结束后确认充电证据的超时秒数")
    parser.add_argument("--reset-evidence-timeout", type=int, default=DEFAULT_RESET_EVIDENCE_TIMEOUT, help="出桩命令异常后复查已离桩状态的超时秒数")
    parser.add_argument("--settle-seconds", type=float, default=DEFAULT_SETTLE_SECONDS, help="出桩后到下一次回充前的静置秒数")
    parser.add_argument("--status-interval", type=float, default=DEFAULT_STATUS_INTERVAL, help="控制台状态栏刷新间隔秒数，默认 1")
    parser.add_argument("--undock-after-final", action="store_true", help="最后一轮成功后也执行出桩")
    parser.add_argument("--continue-on-reset-failure", action="store_true", help="出桩复位失败时仍继续后续轮次")
    parser.add_argument("--yes", action="store_true", help="跳过 START 确认；仍会在未指定 --device 时默认选择中狗")
    if configure_parser is not None:
        configure_parser(parser)
    args = parser.parse_args(argv)
    args.count_was_provided = args.count is not None
    if args.count is None:
        args.count = DEFAULT_COUNT
    return args


def stop_cleanup(profile: ProductProfile, args: argparse.Namespace, progress: Progress, reason: str) -> bool:
    clear_status_line(progress)
    print(f"[停止] 开始停止清理：{reason}")
    set_phase(progress, "停止状态确认")
    release_ok = True
    try:
        values = read_charging_evidence(profile)
    except KeyboardInterrupt:
        request_stop("Ctrl+C")
        values = {}
    update_arc_status_from_values(progress, values)
    clear_status_line(progress)
    print(f"[停止] 清理前状态：{compact_status(values)}")
    if not is_charging(values):
        release = release_arc_control(profile, progress)
        release_ok = release.returncode == 0
        clear_status_line(progress)
        if not release_ok:
            print(f"[停止] 控制权释放提示失败：{last_error_line(release.output)}")
        print(f"[停止] 当前未看到充电证据，跳过出桩清理：{compact_status(values)}")
        return release_ok
    set_phase(progress, "停止出桩")
    try:
        result, release = run_undock_action(profile, args.undock_timeout, progress)
    except KeyboardInterrupt:
        request_stop("Ctrl+C")
        result, release = run_undock_action(profile, args.undock_timeout, progress)
    release_ok = release.returncode == 0
    clear_status_line(progress)
    if not release_ok:
        print(f"[停止] 控制权释放提示失败：{last_error_line(release.output)}")
    if result.returncode != 0:
        print(f"[停止] 出桩清理失败：{last_error_line(result.output)}")
        return False

    verify_values = read_charging_evidence(profile)
    update_arc_status_from_values(progress, verify_values)
    if is_charging(verify_values):
        print(f"[停止] 出桩命令完成，但仍看到充电证据：{evidence_text(verify_values)}")
        return False
    print(f"[停止] 出桩清理完成：{compact_status(verify_values)}")
    return release_ok


def main(
    argv: list[str] | None = None,
    *,
    test_title: str = TEST_TITLE,
    dock_phase: str = DOCK_PHASE,
    configure_parser=None,
    validate_args=None,
    prepare_args=None,
    dock_runner=run_dock_action,
) -> int:
    global ACTIVE_PROGRESS, TEST_TITLE, DOCK_PHASE
    TEST_TITLE = test_title
    DOCK_PHASE = dock_phase
    args = parse_args(argv or sys.argv[1:], configure_parser=configure_parser)
    prompt_count_if_needed(args, test_title=test_title)
    if args.count <= 0:
        raise SystemExit("--count 必须大于 0")
    if args.undock_timeout <= 0:
        raise SystemExit("--undock-timeout 必须大于 0")
    if args.undock_retries < 0:
        raise SystemExit("--undock-retries 不能小于 0")
    if validate_args is not None:
        validate_args(args)
    profile = choose_device(args.device, prompt=not args.yes, test_title=test_title)
    if prepare_args is not None:
        prepare_args(profile, args)
    confirm_start(profile, args, test_title=test_title)

    progress = Progress(
        total=args.count,
        started_at=time.time(),
        status_interval=args.status_interval,
        phase_started_at=time.time(),
    )
    ACTIVE_PROGRESS = progress
    if sys.stdout.isatty():
        print("\033[?25l", end="")
    results: list[tuple[int, str, float, str]] = []
    print()
    print(f"开始连续{test_title}。")

    cleanup_required = False
    cleanup_ok = True
    try:
        for round_no in range(1, args.count + 1):
            if stop_requested():
                cleanup_required = True
                break
            progress.current_round = round_no
            set_phase(progress, "状态检查")
            try:
                values = read_arc_status(profile)
            except KeyboardInterrupt:
                request_stop("Ctrl+C")
                cleanup_required = True
                break
            update_arc_status_from_values(progress, values)
            clear_status_line(progress)
            print(f"[轮次 {round_no}/{args.count}] 初始 ARC 状态: {compact_status(values)}")

            if stop_requested():
                cleanup_required = True
                break

            if is_charging(values):
                undock_ok, undock, reset_values = run_undock_reset_with_retries(profile, args, progress, round_no)
                if not undock_ok:
                    progress.completed += 1
                    progress.failed += 1
                    reason = "出桩失败: " + last_error_line(undock.output)
                    reason = f"{reason}；复查状态：{compact_status(reset_values)}"
                    results.append((round_no, "失败", undock.elapsed, reason))
                    print(f"[轮次 {round_no}/{args.count}] {reason}")
                    if not args.continue_on_reset_failure:
                        print("出桩复位失败且复查仍未离桩，已停止后续轮次。可排查后用 --continue-on-reset-failure 强制继续。")
                        break
                    continue

            if stop_requested():
                cleanup_required = True
                break

            if args.settle_seconds > 0:
                set_phase(progress, "静置")
                sleep_with_progress(args.settle_seconds, progress)
                if stop_requested():
                    cleanup_required = True
                    break

            set_phase(progress, dock_phase)
            dock = dock_runner(profile, args, progress)
            clear_status_line(progress)
            progress.completed += 1
            set_phase(progress, "充电证据确认")
            evidence_values = wait_for_charging_evidence(profile, args.evidence_timeout, progress)
            update_arc_status_from_values(progress, evidence_values)
            clear_status_line(progress)
            evidence = evidence_text(evidence_values)
            if is_charging(evidence_values):
                progress.success += 1
                if dock.returncode == 0:
                    reason = "充电证据确认: " + evidence
                else:
                    reason = "命令返回失败但充电证据确认: " + evidence
                results.append((round_no, "成功", dock.elapsed, reason))
                print(
                    f"[轮次 {round_no}/{args.count}] 成功，用时 {format_duration(dock.elapsed)}；"
                    f"证据：{evidence}；当前成功率 {success_rate(progress.success, progress.completed):.1f}%"
                )
            else:
                progress.failed += 1
                reason = last_error_line(dock.output) if dock.returncode != 0 else "命令成功但充电证据不足"
                reason = f"{reason}；{evidence}"
                results.append((round_no, "失败", dock.elapsed, reason))
                print(
                    f"[轮次 {round_no}/{args.count}] 失败，用时 {format_duration(dock.elapsed)}；"
                    f"原因：{reason}；当前成功率 {success_rate(progress.success, progress.completed):.1f}%"
                )
            if stop_requested():
                cleanup_required = True
                break
    except KeyboardInterrupt:
        request_stop("Ctrl+C")
        cleanup_required = True

    if cleanup_required or stop_requested():
        cleanup_ok = stop_cleanup(profile, args, progress, stop_reason())
    elif args.undock_after_final and progress.completed == args.count:
        values = read_arc_status(profile)
        update_arc_status_from_values(progress, values)
        if is_charging(values):
            progress.current_round = args.count
            set_phase(progress, "结束出桩")
            run_undock_action(profile, args.undock_timeout, progress)
            clear_status_line(progress)

    if sys.stdout.isatty():
        print("\033[?25h", end="")
    ACTIVE_PROGRESS = None
    elapsed = time.time() - progress.started_at
    print()
    print("测试结束。")
    if cleanup_required or stop_requested():
        print(f"停止原因：{stop_reason()}；出桩清理：{'正常' if cleanup_ok else '异常'}")
    print(
        f"总轮次 {progress.completed}/{args.count}，成功 {progress.success}，失败 {progress.failed}，"
        f"成功率 {success_rate(progress.success, progress.completed):.1f}%，总用时 {format_duration(elapsed)}"
    )
    print("轮次结果：")
    for round_no, status, elapsed_seconds, reason in results:
        print(f"  {round_no:02d}. {status} | 用时 {format_duration(elapsed_seconds)} | {reason}")
    if cleanup_required or stop_requested():
        return 0 if cleanup_ok else 130
    return 0 if progress.failed == 0 and progress.completed == args.count else 1


if __name__ == "__main__":
    raise SystemExit(main())
