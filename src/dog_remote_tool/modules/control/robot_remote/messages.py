from __future__ import annotations

import time


MAGIC = b"ZSKJ"
PROTOCOL_VERSION = "1.2.0"
SRC_ROBOT = 1
SRC_SDK = 3
TYPE_HANDSHAKE = 1000
TYPE_HEARTBEAT = 1001
TYPE_COMMAND = 1002
TYPE_REMOTE = 1003
TYPE_TAKE_CONTROL = 1013
TYPE_RELEASE_CONTROL = 1015


def head(frame_type: int) -> dict:
    return {"type": frame_type, "time": int(time.time() * 1000), "src": SRC_SDK}


def handshake_payload() -> dict:
    return {
        "head": head(TYPE_HANDSHAKE),
        "data": {
            "version": "dog_remote_tool",
            "protocol_version": PROTOCOL_VERSION,
            "device": "dog_remote_tool",
            "platform": "linux",
            "package_name": "dog_remote_tool",
        },
    }


def empty_payload(frame_type: int) -> dict:
    return {"head": head(frame_type), "data": {}}


def command_payload(command_name: str) -> dict:
    return {"head": head(TYPE_COMMAND), "data": {"cmd": command_name}}


def remote_payload(lx: float, ly: float, rx: float, ry: float, turn: str = "none", high_low: str = "none") -> dict:
    return {
        "head": head(TYPE_REMOTE),
        "data": {
            "lx": lx,
            "ly": ly,
            "rx": rx,
            "ry": ry,
            "body": {"turn": turn, "high_low": high_low},
        },
    }


def check_ack(message: dict, action: str) -> None:
    data = message.get("data") or {}
    error_code = data.get("error_code", 0)
    if error_code not in (0, "0", None):
        reason = data.get("reason") or data.get("message") or "unknown"
        raise RuntimeError(f"{action} 被拒绝: error_code={error_code} reason={reason}")
