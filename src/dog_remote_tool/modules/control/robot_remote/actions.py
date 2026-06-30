from __future__ import annotations

from collections.abc import Callable

import dog_remote_tool.modules.control.robot_remote.messages as _messages
from dog_remote_tool.modules.control.robot_remote.client import RobotRemoteClient


ClientFactory = Callable[[str, int, float], RobotRemoteClient]
_check_ack = _messages.check_ack


def run_probe(
    host: str,
    port: int,
    timeout: float,
    read_only: bool = False,
    client_factory: ClientFactory = RobotRemoteClient,
) -> int:
    client = client_factory(host, port, timeout)
    controlled = False
    try:
        client.connect()
        print(f"[INFO] 已连接 robot_remote websocket: {host}:{port}", flush=True)
        handshake = client.handshake()
        _check_ack(handshake, "握手")
        device = handshake.get("data") or {}
        model = device.get("model", "unknown")
        device_type = device.get("device_type", "unknown")
        print(f"[INFO] 握手成功: model={model} device_type={device_type}", flush=True)
        if read_only:
            try:
                client.send_heartbeat()
                print("[INFO] 心跳已发送", flush=True)
            except Exception as exc:
                print(f"[WARN] 心跳发送失败: {exc}", flush=True)
            print("[INFO] 只读检查完成，未获取控制权", flush=True)
            return 0
        client.send_heartbeat()
        print("[INFO] 心跳已发送", flush=True)
        take = client.take_control()
        _check_ack(take, "获取控制权")
        controlled = True
        print("[INFO] 控制权获取成功", flush=True)
        return 0
    finally:
        if controlled:
            try:
                client.release_control()
                print("[INFO] 已释放控制权", flush=True)
            except Exception as exc:
                print(f"[WARN] 释放控制权失败: {exc}", flush=True)
        client.close()


def run_posture(
    host: str,
    port: int,
    command_name: str,
    timeout: float,
    client_factory: ClientFactory = RobotRemoteClient,
) -> int:
    client = client_factory(host, port, timeout)
    controlled = False
    try:
        client.connect()
        print(f"[INFO] 已连接 robot_remote websocket: {host}:{port}", flush=True)
        _check_ack(client.handshake(), "握手")
        print("[INFO] 握手成功", flush=True)
        client.send_heartbeat()
        take = client.take_control()
        _check_ack(take, "获取控制权")
        controlled = True
        print("[INFO] 控制权获取成功", flush=True)
        ack = client.command(command_name)
        _check_ack(ack, "姿态指令")
        echoed = (ack.get("data") or {}).get("cmd")
        if echoed and echoed != command_name:
            raise RuntimeError(f"robot_remote 返回了非预期指令: {echoed}")
        print(f"[INFO] robot_remote 已确认姿态指令: {command_name}", flush=True)
        return 0
    finally:
        if controlled:
            try:
                client.release_control()
                print("[INFO] 已释放控制权", flush=True)
            except Exception as exc:
                print(f"[WARN] 释放控制权失败: {exc}", flush=True)
        client.close()
