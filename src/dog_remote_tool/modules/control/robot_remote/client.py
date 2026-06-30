from __future__ import annotations

import base64
import os
import select
import socket
import struct
import time
from dataclasses import dataclass

import dog_remote_tool.modules.control.robot_remote.codec as _codec
import dog_remote_tool.modules.control.robot_remote.messages as _messages


MAGIC = _messages.MAGIC
PROTOCOL_VERSION = _messages.PROTOCOL_VERSION
SRC_ROBOT = _messages.SRC_ROBOT
SRC_SDK = _messages.SRC_SDK
TYPE_HANDSHAKE = _messages.TYPE_HANDSHAKE
TYPE_HEARTBEAT = _messages.TYPE_HEARTBEAT
TYPE_COMMAND = _messages.TYPE_COMMAND
TYPE_REMOTE = _messages.TYPE_REMOTE
TYPE_TAKE_CONTROL = _messages.TYPE_TAKE_CONTROL
TYPE_RELEASE_CONTROL = _messages.TYPE_RELEASE_CONTROL


@dataclass(frozen=True)
class RobotRemoteClient:
    host: str
    port: int = 8081
    timeout: float = 3.0

    def __post_init__(self) -> None:
        object.__setattr__(self, "_sock", None)
        object.__setattr__(self, "_frame_id", 1)

    @property
    def sock(self) -> socket.socket:
        sock = getattr(self, "_sock")
        if sock is None:
            raise RuntimeError("robot_remote websocket is not connected")
        return sock

    def connect(self) -> None:
        sock = socket.create_connection((self.host, self.port), timeout=self.timeout)
        sock.settimeout(self.timeout)
        key = base64.b64encode(os.urandom(16)).decode("ascii")
        request = (
            "GET / HTTP/1.1\r\n"
            f"Host: {self.host}:{self.port}\r\n"
            "Upgrade: websocket\r\n"
            "Connection: Upgrade\r\n"
            f"Sec-WebSocket-Key: {key}\r\n"
            "Sec-WebSocket-Version: 13\r\n"
            "\r\n"
        ).encode("ascii")
        sock.sendall(request)
        response = self._recv_http_header(sock)
        if b" 101 " not in response.split(b"\r\n", 1)[0]:
            raise RuntimeError(response.decode("utf-8", errors="replace").splitlines()[0])
        object.__setattr__(self, "_sock", sock)

    def close(self) -> None:
        sock = getattr(self, "_sock")
        if sock is not None:
            try:
                sock.close()
            finally:
                object.__setattr__(self, "_sock", None)

    def handshake(self) -> dict:
        return self.request(TYPE_HANDSHAKE, _messages.handshake_payload())

    def heartbeat(self) -> dict:
        return self.request(TYPE_HEARTBEAT, _messages.empty_payload(TYPE_HEARTBEAT))

    def send_heartbeat(self) -> None:
        self._send_json(_messages.empty_payload(TYPE_HEARTBEAT))

    def take_control(self) -> dict:
        return self.request(TYPE_TAKE_CONTROL, _messages.empty_payload(TYPE_TAKE_CONTROL))

    def release_control(self) -> dict:
        return self.request(TYPE_RELEASE_CONTROL, _messages.empty_payload(TYPE_RELEASE_CONTROL))

    def command(self, command_name: str) -> dict:
        return self.request(TYPE_COMMAND, _messages.command_payload(command_name))

    def remote(self, lx: float, ly: float, rx: float, ry: float, turn: str = "none", high_low: str = "none") -> None:
        self._send_json(_messages.remote_payload(lx, ly, rx, ry, turn, high_low))

    def drain_pending(self, max_frames: int = 20) -> int:
        sock = getattr(self, "_sock")
        if sock is None:
            return 0
        drained = 0
        for _ in range(max(1, int(max_frames))):
            readable, _, _ = select.select([sock], [], [], 0)
            if not readable:
                break
            try:
                payload = self._recv_ws_payload(0.01)
            except (TimeoutError, socket.timeout):
                break
            if payload:
                drained += 1
        return drained

    def request(self, expected_type: int, payload: dict) -> dict:
        self._send_json(payload)
        return self._read_until_type(expected_type)

    def _next_frame_id(self) -> int:
        frame_id = getattr(self, "_frame_id")
        object.__setattr__(self, "_frame_id", (frame_id % 65535) + 1)
        return frame_id

    def _send_json(self, payload: dict) -> None:
        self._send_ws_frame(_codec.build_packet(payload, self._next_frame_id()))

    def _read_until_type(self, expected_type: int) -> dict:
        deadline = time.monotonic() + self.timeout
        last_error = ""
        while time.monotonic() < deadline:
            payload = self._recv_ws_payload(deadline - time.monotonic())
            if not payload:
                continue
            try:
                message = self._decode_packet(payload)
            except ValueError as exc:
                last_error = str(exc)
                continue
            head = message.get("head") or {}
            if head.get("src") == SRC_ROBOT and head.get("type") == expected_type:
                return message
        if last_error:
            raise TimeoutError(f"等待 robot_remote 响应超时: {last_error}")
        raise TimeoutError(f"等待 robot_remote type={expected_type} 响应超时")

    def _send_ws_frame(self, payload: bytes, opcode: int = 0x2) -> None:
        length = len(payload)
        header = bytearray([0x80 | opcode])
        if length < 126:
            header.append(0x80 | length)
        elif length <= 0xFFFF:
            header.extend([0x80 | 126])
            header.extend(struct.pack("!H", length))
        else:
            header.extend([0x80 | 127])
            header.extend(struct.pack("!Q", length))
        mask = os.urandom(4)
        masked = bytes(value ^ mask[index % 4] for index, value in enumerate(payload))
        self.sock.sendall(bytes(header) + mask + masked)

    def _recv_ws_payload(self, timeout: float) -> bytes:
        self.sock.settimeout(max(0.1, timeout))
        first, second = self._recv_exact(2)
        opcode = first & 0x0F
        masked = bool(second & 0x80)
        length = second & 0x7F
        if length == 126:
            length = struct.unpack("!H", self._recv_exact(2))[0]
        elif length == 127:
            length = struct.unpack("!Q", self._recv_exact(8))[0]
        mask = self._recv_exact(4) if masked else b""
        payload = self._recv_exact(length) if length else b""
        if masked:
            payload = bytes(value ^ mask[index % 4] for index, value in enumerate(payload))
        if opcode == 0x8:
            raise ConnectionError("robot_remote websocket closed")
        if opcode == 0x9:
            self._send_ws_frame(payload, opcode=0xA)
            return b""
        if opcode not in (0x1, 0x2):
            return b""
        return payload

    def _recv_exact(self, size: int) -> bytes:
        chunks = bytearray()
        while len(chunks) < size:
            chunk = self.sock.recv(size - len(chunks))
            if not chunk:
                raise ConnectionError("robot_remote websocket disconnected")
            chunks.extend(chunk)
        return bytes(chunks)

    @staticmethod
    def _recv_http_header(sock: socket.socket) -> bytes:
        data = bytearray()
        while b"\r\n\r\n" not in data:
            chunk = sock.recv(1024)
            if not chunk:
                break
            data.extend(chunk)
            if len(data) > 8192:
                raise RuntimeError("robot_remote websocket header is too large")
        return bytes(data)

    @staticmethod
    def _decode_packet(payload: bytes) -> dict:
        return _codec.decode_packet(payload)
