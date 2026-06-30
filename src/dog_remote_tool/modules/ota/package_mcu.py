from __future__ import annotations

from pathlib import Path

from dog_remote_tool.modules.ota.package_versions import firmware_version_from_name


MCU_DISPLAY_SLOTS: dict[str, tuple[tuple[str, str], ...]] = {
    "xg_l1_point_3588": (
        ("spline", "spline"),
        ("motorcontrol", "motorcontrol"),
        ("imu", "imu"),
        ("power_board", "power_board/SOC"),
    ),
    "xg_l1_wheel_3588": (
        ("spline", "spline"),
        ("motorcontrol", "motorcontrol"),
        ("imu", "imu"),
        ("power_board", "power_board/SOC"),
    ),
    "xg3588": (
        ("spline", "spline"),
        ("motorcontrol", "motorcontrol"),
        ("imu", "imu"),
        ("power_board", "power_board/SOC"),
    ),
    "zg3588": (
        ("imu", "imu"),
        ("actuator_joint", "actuator_joint"),
        ("actuator_wheel", "actuator_wheel"),
        ("uart2can", "uart2can"),
        ("hot_swap", "hot_swap"),
        ("power_control", "power_control"),
        ("battery", "battery"),
    ),
}


def mcu_display_slots(target_key: str) -> list[tuple[str, str]]:
    return list(MCU_DISPLAY_SLOTS.get(target_key, ()))


def mcu_slot_for_name(name: str) -> str:
    text = name.lower()
    if "actuator_joint" in text:
        return "actuator_joint"
    if "actuator_wheel" in text:
        return "actuator_wheel"
    if "uart2can" in text or "canfd" in text:
        return "uart2can"
    if "hot_swap" in text:
        return "hot_swap"
    if "power_control" in text:
        return "power_control"
    if "battery" in text:
        return "battery"
    if "motorcontrol" in text:
        return "motorcontrol"
    if "spline" in text:
        return "spline"
    if "imu" in text:
        return "imu"
    if "power_board" in text or "soc" in text:
        return "power_board"
    return text.split("(", 1)[0].strip() or name


def mcu_target_versions_from_manifest(manifest) -> dict[str, str]:
    values: dict[str, list[str]] = {}
    for module in manifest.modules:
        label = module.name or Path(module.firmware).stem
        slot = mcu_slot_for_name(label or module.firmware)
        version = module.version or firmware_version_from_name(Path(module.firmware).name)
        value = version or Path(module.firmware).name
        if value:
            values.setdefault(slot, []).append(value)
    return {slot: "；".join(items) for slot, items in values.items()}
