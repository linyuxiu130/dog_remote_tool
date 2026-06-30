from __future__ import annotations


DIRECTION_KEYS = {
    ord("W"): "w",
    ord("S"): "s",
    ord("A"): "a",
    ord("D"): "d",
    ord("Q"): "q",
    ord("E"): "e",
}
L2_ACTION_KEYS = {
    ord("1"): "stand",
    ord("2"): "lie",
    ord("3"): "crawl",
    ord("4"): "head",
    ord("5"): "neutral",
}
L1_ACTION_KEYS = {
    ord("1"): "stand",
    ord("2"): "lie",
    ord("3"): "passive",
}

LINEAR_SPEED_MIN_MPS = 0.1
LINEAR_SPEED_DEFAULT_MPS = 0.6
LINEAR_SPEED_MAX_MPS = 3.0
LINEAR_SPEED_STEP_MPS = 0.1
ANGULAR_SPEED_MIN_RADPS = 0.1
ANGULAR_SPEED_DEFAULT_RADPS = 0.8
ROBOT_REMOTE_ANGULAR_SPEED_DEFAULT_RADPS = ANGULAR_SPEED_DEFAULT_RADPS
ANGULAR_SPEED_MAX_RADPS = 3.0
ANGULAR_SPEED_STEP_RADPS = 0.1


def clamp_stream_speed(value: float, minimum: float, maximum: float) -> float:
    return round(max(minimum, min(maximum, float(value))), 2)


def stepped_stream_speed(value: float, delta: float, minimum: float, maximum: float) -> float:
    return clamp_stream_speed(value + delta, minimum, maximum)


def l1_velocity_vector(keys: set[str], linear_speed: float, angular_speed: float) -> tuple[float, float, float]:
    forward = linear_speed if "w" in keys and "s" not in keys else -linear_speed if "s" in keys and "w" not in keys else 0.0
    strafe = linear_speed if "q" in keys and "e" not in keys else -linear_speed if "e" in keys and "q" not in keys else 0.0
    turn = angular_speed if "a" in keys and "d" not in keys else -angular_speed if "d" in keys and "a" not in keys else 0.0
    return round(forward, 2), round(strafe, 2), round(turn, 2)


def l2_gamepad_vector(keys: set[str], axis: int, inplace_mode: bool) -> tuple[int, int, int, int]:
    if inplace_mode:
        forward = 0
        strafe = 0
        turn = -axis if "a" in keys and "d" not in keys else axis if "d" in keys and "a" not in keys else 0
        pitch = -axis if "w" in keys and "s" not in keys else axis if "s" in keys and "w" not in keys else 0
    else:
        forward = -axis if "w" in keys and "s" not in keys else axis if "s" in keys and "w" not in keys else 0
        strafe = -axis if "q" in keys and "e" not in keys else axis if "e" in keys and "q" not in keys else 0
        turn = -axis if "a" in keys and "d" not in keys else axis if "d" in keys and "a" not in keys else 0
        pitch = 0
    return forward, strafe, turn, pitch


def robot_sdk_velocity_vector(keys: set[str], linear_speed: float, angular_speed: float) -> tuple[float, float, float, float]:
    forward = -linear_speed if "w" in keys and "s" not in keys else linear_speed if "s" in keys and "w" not in keys else 0.0
    strafe = -linear_speed if "q" in keys and "e" not in keys else linear_speed if "e" in keys and "q" not in keys else 0.0
    turn = -angular_speed if "a" in keys and "d" not in keys else angular_speed if "d" in keys and "a" not in keys else 0.0
    return round(forward, 2), round(strafe, 2), round(turn, 2), 0.0


def stream_set_payload(
    vector: tuple[int | float, ...],
    *,
    linear_speed: float | None = None,
    angular_speed: float | None = None,
    linear_limit_mps: float | None = None,
    angular_limit_radps: float | None = None,
) -> dict:
    if len(vector) not in (3, 4):
        raise ValueError(f"实时遥控向量只支持 3 轴或 4 轴: {len(vector)}")
    payload = {"cmd": "set"}
    for name, value in zip(("forward", "strafe", "turn", "pitch"), vector):
        payload[name] = value
    if linear_speed is not None:
        payload["linear_speed"] = round(float(linear_speed), 2)
    if angular_speed is not None:
        payload["angular_speed"] = round(float(angular_speed), 2)
    if linear_limit_mps is not None:
        payload["linear_limit_mps"] = round(float(linear_limit_mps), 2)
    if angular_limit_radps is not None:
        payload["angular_limit_radps"] = round(float(angular_limit_radps), 2)
    return payload


def direction_key(key: int) -> str:
    return DIRECTION_KEYS.get(key, "")


def l2_action_key(key: int) -> str:
    return L2_ACTION_KEYS.get(key, "")


def l1_action_key(key: int) -> str:
    return L1_ACTION_KEYS.get(key, "")


def l2_action_payload(action: str) -> tuple[dict, bool | None]:
    payload = {"cmd": action}
    inplace_mode: bool | None = None
    if action in {"crawl", "head"}:
        payload["ensure_stand"] = True
    if action == "head":
        inplace_mode = True
    elif action in {"stand", "lie", "crawl"}:
        inplace_mode = False
    return payload, inplace_mode
