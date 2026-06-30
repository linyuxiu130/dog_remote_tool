from __future__ import annotations

import json
import sys
import time
from collections.abc import Callable

import dog_remote_tool.modules.control.robot_remote.messages as _messages
from dog_remote_tool.modules.control.robot_remote.client import RobotRemoteClient


ClientFactory = Callable[[str, int, float], RobotRemoteClient]
_check_ack = _messages.check_ack

def _emit(payload: dict) -> None:
    print(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), flush=True)


def _stream_values(command: dict, axis_limit: int) -> tuple[float, float, float, float]:
    limit = max(5, min(abs(int(axis_limit)), 100))

    def axis(name: str) -> float:
        raw_value = command.get(name, 0)
        if isinstance(raw_value, float):
            raw = float(command.get(name, 0.0))
            return round(max(-1.0, min(1.0, raw)), 4)
        value = int(raw_value)
        value = max(-limit, min(limit, value))
        return round(value / 100.0, 4)

    # RobotSDK Move(left_right, forward_back, yaw) maps to lx/ly/rx.
    # UI vectors keep the historical keyboard signs, so invert before sending SDK semantics.
    lx = -axis("strafe")
    ly = -axis("forward")
    rx = -axis("turn")
    ry = -axis("pitch")
    return lx, ly, rx, ry


def _read_stream_input(timeout: float) -> list[str]:
    try:
        import select

        readable, _, _ = select.select([sys.stdin], [], [], max(0.0, timeout))
        if not readable:
            return []
        lines = []
        while readable:
            line = sys.stdin.readline()
            lines.append(line)
            if not line:
                break
            readable, _, _ = select.select([sys.stdin], [], [], 0.0)
        return lines
    except Exception:
        line = sys.stdin.readline()
        return [line] if line else [""]


def run_stream(
    host: str,
    port: int,
    timeout: float,
    axis_limit: int,
    interval: float,
    auto_general: bool = True,
    client_factory: ClientFactory = RobotRemoteClient,
) -> int:
    client = client_factory(host, port, timeout)
    controlled = False
    target = (0.0, 0.0, 0.0, 0.0)
    target_active = False
    running = True
    motion_mode = "unknown"
    next_heartbeat = time.monotonic() + 1.0
    next_send = time.monotonic()
    drain_pending = getattr(client, "drain_pending", None)
    try:
        client.connect()
        _check_ack(client.handshake(), "握手")
        client.send_heartbeat()
        _check_ack(client.take_control(), "获取控制权")
        controlled = True
        if auto_general:
            try:
                _check_ack(client.command("mode/general"), "通用模式")
                motion_mode = "general"
            except Exception as exc:
                _emit({"type": "log", "message": f"切通用模式未确认: {exc}"})
        _emit({"type": "ready", "protocol": "robot_remote", "host": host, "port": port, "axis_limit": axis_limit})

        while running:
            send_now = False
            for line in _read_stream_input(next_send - time.monotonic()):
                if not line:
                    running = False
                    break
                try:
                    command = json.loads(line)
                except json.JSONDecodeError as exc:
                    _emit({"type": "error", "message": str(exc)})
                    continue
                cmd = command.get("cmd")
                if cmd == "set":
                    target = _stream_values(command, axis_limit)
                    target_active = any(value != 0.0 for value in target)
                    send_now = True
                    if target_active and (target[0] != 0.0 or target[1] != 0.0) and motion_mode != "general":
                        _check_ack(client.command("mode/general"), "通用模式")
                        motion_mode = "general"
                        _emit({"type": "result", "cmd": "general"})
                elif cmd == "neutral":
                    target = (0.0, 0.0, 0.0, 0.0)
                    target_active = False
                    send_now = True
                elif cmd == "stand":
                    _check_ack(client.command("action/stand_up"), "站立")
                    _check_ack(client.command("mode/general"), "通用模式")
                    motion_mode = "general"
                    _emit({"type": "result", "cmd": "stand"})
                elif cmd == "crawl":
                    _check_ack(client.command("action/crawl"), "匍匐")
                    _emit({"type": "result", "cmd": "crawl"})
                elif cmd == "head":
                    _check_ack(client.command("mode/in_place"), "原地")
                    motion_mode = "in_place"
                    _emit({"type": "result", "cmd": "head"})
                elif cmd == "lie":
                    _check_ack(client.command("action/lie_down"), "趴下")
                    _emit({"type": "result", "cmd": "lie"})
                elif cmd == "quit":
                    running = False
                else:
                    _emit({"type": "error", "message": f"未知指令: {cmd}"})

            now = time.monotonic()
            if callable(drain_pending):
                drain_pending()
            if now >= next_heartbeat:
                client.send_heartbeat()
                next_heartbeat = now + 1.0
            if send_now or now >= next_send:
                client.remote(*target)
                send_interval = interval if target_active else max(interval, 0.2)
                next_send = now + send_interval
                if target_active:
                    _emit({"type": "stream", "lx": target[0], "ly": target[1], "rx": target[2], "ry": target[3]})
    finally:
        if controlled:
            try:
                client.remote(0.0, 0.0, 0.0, 0.0)
            except Exception:
                pass
            try:
                client.release_control()
                _emit({"type": "closed"})
            except Exception as exc:
                _emit({"type": "error", "message": f"释放控制权失败: {exc}"})
        client.close()
    return 0
