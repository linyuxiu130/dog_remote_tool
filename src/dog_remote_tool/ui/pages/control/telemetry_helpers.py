from __future__ import annotations

import math


ZERO_SPEED_THRESHOLD = 0.04


def display_motion_value(value: float) -> float:
    return 0.0 if abs(value) < ZERO_SPEED_THRESHOLD else value


def l1_telemetry_text(payload: dict) -> tuple[str, str, str, str]:
    body_velocity = payload.get("body_velocity") or []
    world_velocity = payload.get("world_velocity") or []
    body_gyro = payload.get("body_gyro") or []
    ctrl_mode = payload.get("ctrl_mode")

    def value_at(values, index: int) -> float:
        try:
            return float(values[index])
        except Exception:
            return 0.0

    body_vx = value_at(body_velocity, 0)
    body_vy = value_at(body_velocity, 1)
    world_vx = value_at(world_velocity, 0)
    world_vy = value_at(world_velocity, 1)
    gyro_z = display_motion_value(value_at(body_gyro, 2))
    linear_speed = display_motion_value(math.sqrt(world_vx * world_vx + world_vy * world_vy))
    translate_speed = display_motion_value(math.sqrt(body_vx * body_vx + body_vy * body_vy))
    mode_text = {0: "阻尼", 1: "站立", 3: "移动"}.get(ctrl_mode, str(ctrl_mode) if ctrl_mode is not None else "--")
    return (
        f"前后 {linear_speed:.2f} m/s",
        f"横移 {translate_speed:.2f} m/s",
        f"角速度 {gyro_z:.2f} rad/s",
        f"控制模式 {mode_text}",
    )


def l2_telemetry_text(payload: dict) -> tuple[str, str, str, str]:
    def fmt(value, unit: str) -> str:
        try:
            return f"{display_motion_value(float(value)):.2f} {unit}"
        except (TypeError, ValueError):
            return "--"

    topic = str(payload.get("topic") or "").strip()
    return (
        fmt(payload.get('linear_x'), 'm/s'),
        f"横移 {fmt(payload.get('linear_y'), 'm/s')}",
        f"角速度 {fmt(payload.get('angular_z'), 'rad/s')}",
        f"来源 {topic or '--'}",
    )
