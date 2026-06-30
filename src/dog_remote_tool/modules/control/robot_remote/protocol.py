from __future__ import annotations

import argparse
import sys

import dog_remote_tool.modules.control.robot_remote.messages as _messages
from dog_remote_tool.modules.control.robot_remote import actions as _actions
from dog_remote_tool.modules.control.robot_remote import stream as _stream
from dog_remote_tool.modules.control.robot_remote.client import (
    MAGIC,
    PROTOCOL_VERSION,
    SRC_ROBOT,
    SRC_SDK,
    TYPE_COMMAND,
    TYPE_HANDSHAKE,
    TYPE_HEARTBEAT,
    TYPE_RELEASE_CONTROL,
    TYPE_REMOTE,
    TYPE_TAKE_CONTROL,
    RobotRemoteClient,
)


_check_ack = _messages.check_ack
_emit = _stream._emit
_read_stream_input = _stream._read_stream_input
_stream_values = _stream._stream_values


def run_probe(host: str, port: int, timeout: float, read_only: bool = False) -> int:
    return _actions.run_probe(host, port, timeout, read_only, client_factory=RobotRemoteClient)


def run_posture(host: str, port: int, command_name: str, timeout: float) -> int:
    return _actions.run_posture(host, port, command_name, timeout, client_factory=RobotRemoteClient)


def run_stream(host: str, port: int, timeout: float, axis_limit: int, interval: float, auto_general: bool = True) -> int:
    return _stream.run_stream(host, port, timeout, axis_limit, interval, auto_general, client_factory=RobotRemoteClient)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="dog_remote_tool robot_remote")
    subparsers = parser.add_subparsers(dest="action", required=True)
    for name in ("probe", "posture", "stream"):
        sub = subparsers.add_parser(name)
        sub.add_argument("--host", required=True)
        sub.add_argument("--port", type=int, default=8081)
        sub.add_argument("--timeout", type=float, default=3.0)
        if name == "probe":
            sub.add_argument("--read-only", action="store_true")
        if name == "posture":
            sub.add_argument("--cmd", required=True)
        if name == "stream":
            sub.add_argument("--axis-limit", type=int, default=100)
            sub.add_argument("--interval", type=float, default=0.02)
            sub.add_argument("--no-general", action="store_true")
    args = parser.parse_args(argv)
    try:
        if args.action == "probe":
            return run_probe(args.host, args.port, args.timeout, args.read_only)
        if args.action == "posture":
            return run_posture(args.host, args.port, args.cmd, args.timeout)
        if args.action == "stream":
            return run_stream(args.host, args.port, args.timeout, args.axis_limit, args.interval, not args.no_general)
    except Exception as exc:
        print(f"[ERROR] {exc}", file=sys.stderr, flush=True)
        return 1
    return 2


__all__ = [
    "MAGIC",
    "PROTOCOL_VERSION",
    "RobotRemoteClient",
    "SRC_ROBOT",
    "SRC_SDK",
    "TYPE_COMMAND",
    "TYPE_HANDSHAKE",
    "TYPE_HEARTBEAT",
    "TYPE_RELEASE_CONTROL",
    "TYPE_REMOTE",
    "TYPE_TAKE_CONTROL",
    "_check_ack",
    "_emit",
    "_read_stream_input",
    "_stream_values",
    "main",
    "run_posture",
    "run_probe",
    "run_stream",
]


if __name__ == "__main__":
    raise SystemExit(main())
