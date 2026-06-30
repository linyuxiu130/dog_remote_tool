from __future__ import annotations

from dataclasses import dataclass

from dog_remote_tool.core.parsers import parse_key_values
from dog_remote_tool.core.profiles import ProductProfile
from dog_remote_tool.core.shell import CommandSpec, ssh_command


@dataclass(frozen=True)
class BatteryStatus:
    percent: int
    charging: bool = False


XG_BATTERY_PROFILES = {"xg3588", "xg1_nx"}
L2_BATTERY_PROFILES = {"xg2_3588", "xg2_s100"}
ZG_BATTERY_PROFILES = {"zg3588", "zg_surround_3588", "zg_surround_s100", "zg_lidar_nx"}


def battery_source_profile(profile: ProductProfile) -> ProductProfile:
    """Return the 3588 host that owns the shared robot battery."""
    if profile.key in XG_BATTERY_PROFILES:
        return ProductProfile(
            key="xg3588_battery",
            label="小狗一代 3588 电池",
            platform="RK3588",
            host="192.168.234.1",
            user="firefly",
            password="firefly",
            home="/home/firefly",
        )
    if profile.key in L2_BATTERY_PROFILES:
        return ProductProfile(
            key="xg2_3588_battery",
            label="小狗二代 3588 电池",
            platform="RK3588",
            host="192.168.234.1",
            user="robot",
            password="bot",
            home="/home/robot",
        )
    if profile.key in ZG_BATTERY_PROFILES:
        return ProductProfile(
            key="zg3588_battery",
            label="中狗 3588 电池",
            platform="RK3588",
            host="192.168.234.1",
            user="robot",
            password="bot",
            home="/home/robot",
        )
    return profile


def _zg_robot_remote_battery_script() -> str:
    return r"""
set +e
python3 - <<'PY'
import json
import re

path = "/home/robot/robot_launch_log/robot_remote.stdout"
last = ""
try:
    with open(path, "rb") as handle:
        handle.seek(0, 2)
        end = handle.tell()
        handle.seek(max(0, end - 262144))
        for raw in handle:
            line = raw.decode("utf-8", "ignore")
            if '"battery"' in line and "Sent Data to clients" in line:
                last = line
    match = re.search(r'(\{"data":.*\})', last)
    battery = json.loads(match.group(1))["data"]["battery"] if match else {}
    powers = []
    for key in ("power1", "power2"):
        value = float(battery.get(key) or 0)
        if 0 < value <= 100:
            powers.append(value)
    currents = [float(battery.get(k) or 0) for k in ("current1", "current2")]
    statuses = [int(battery.get(k) or 0) for k in ("power_supply_status1", "power_supply_status2")]
    power = int(sum(powers) / len(powers) + 0.5)
except Exception:
    print("DOG_REMOTE_BATTERY=UNKNOWN")
else:
    if 0 < power <= 100:
        print(f"DOG_REMOTE_BATTERY={power}")
        print(f"DOG_REMOTE_CHARGING={1 if any(v > 0 for v in currents) or 1 in statuses else 0}")
    else:
        print("DOG_REMOTE_BATTERY=UNKNOWN")
PY
"""


def _shared_memory_battery_script() -> str:
    return r"""
set +e
python3 - <<'PY'
import struct

try:
    with open("/dev/shm/bms_shm", "rb") as handle:
        data = handle.read(28)
    current = struct.unpack_from("<f", data, 12)[0]
    power = int(struct.unpack_from("<f", data, 16)[0] + 0.5)
except Exception:
    print("DOG_REMOTE_BATTERY=UNKNOWN")
else:
    if 0 < power <= 100:
        print(f"DOG_REMOTE_BATTERY={power}")
        print(f"DOG_REMOTE_CHARGING={1 if current > 0 else 0}")
    else:
        print("DOG_REMOTE_BATTERY=UNKNOWN")
PY
"""


def battery_command(profile: ProductProfile) -> CommandSpec:
    profile = battery_source_profile(profile)
    if profile.key == "zg3588_battery":
        script = _zg_robot_remote_battery_script()
    else:
        script = _shared_memory_battery_script()
    return CommandSpec("读取电量", ssh_command(profile, script), concurrency="parallel", locks=("device-battery",))


def parse_battery_output(text: str) -> int | None:
    status = parse_battery_status_output(text)
    return status.percent if status is not None else None


def parse_battery_status_output(text: str) -> BatteryStatus | None:
    values = parse_key_values(text)
    value = values.get("DOG_REMOTE_BATTERY")
    charging = values.get("DOG_REMOTE_CHARGING", "").lower() in {"1", "true", "yes", "charging"}
    if not value or value == "UNKNOWN":
        return None
    try:
        raw_percent = float(value)
    except ValueError:
        return None
    percent = int(raw_percent + 0.5)
    if percent <= 0:
        return None
    return BatteryStatus(min(100, percent), charging)
