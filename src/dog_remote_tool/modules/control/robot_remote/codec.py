from __future__ import annotations

import json
import struct

from dog_remote_tool.modules.control.robot_remote.messages import MAGIC


def build_packet(payload: dict, frame_id: int) -> bytes:
    body = json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    if len(body) > 65535:
        raise ValueError("robot_remote payload is too large")
    return MAGIC + struct.pack("<HH", len(body), frame_id) + (b"\0" * 8) + body


def decode_packet(payload: bytes) -> dict:
    if len(payload) < 16 or payload[:4] != MAGIC:
        raise ValueError("非 ZSKJ 数据帧")
    length = struct.unpack("<H", payload[4:6])[0]
    body = payload[16 : 16 + length]
    if len(body) != length:
        raise ValueError("ZSKJ JSON 长度不完整")
    return json.loads(body.decode("utf-8"))
