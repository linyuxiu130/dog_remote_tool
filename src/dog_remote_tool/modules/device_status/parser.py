from __future__ import annotations

from dog_remote_tool.core.markers import extract_marked_payload
from dog_remote_tool.core.parsers import parse_key_values
from dog_remote_tool.modules.device_status.models import DeviceStatus, LaunchItem, PackageInfo


def parse_probe_output(text: str) -> DeviceStatus:
    values = parse_key_values(text)
    hostname = values.get("HOSTNAME", "")
    release_version = values.get("RELEASE", "")
    packages_by_name: dict[str, PackageInfo] = {}
    packages_text = extract_marked_payload(text, "PACKAGES_BEGIN", "PACKAGES_END")
    for raw in packages_text.splitlines():
        if "\t" in raw:
            name, version = raw.split("\t", 1)
            package = PackageInfo(name.strip(), version.strip())
            packages_by_name[package.name] = package
    raw_launch = extract_marked_payload(text, "LAUNCH_BEGIN", "LAUNCH_END").strip()
    return DeviceStatus(
        hostname=hostname,
        release_version=release_version,
        packages=tuple(packages_by_name[name] for name in sorted(packages_by_name)),
        launch_items=tuple(parse_launch_items(raw_launch)),
        raw_launch=raw_launch,
    )


def parse_launch_items(text: str) -> list[LaunchItem]:
    items: list[LaunchItem] = []
    for raw in text.splitlines():
        if "│" not in raw:
            continue
        columns = [part.strip() for part in raw.split("│")]
        columns = [part for part in columns if part]
        if len(columns) < 4 or not columns[0].isdigit():
            continue
        items.append(
            LaunchItem(
                index=columns[0],
                name=columns[2],
                status=columns[3],
                pid=columns[1],
                uptime=columns[5] if len(columns) > 5 else "",
            )
        )
    return items
