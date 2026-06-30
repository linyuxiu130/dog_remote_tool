from __future__ import annotations

import os

from dog_remote_tool.modules.bag import remote_helper


def remote_bag_scan_command(scan_dirs: list[str]) -> str:
    return remote_helper.scan_command(scan_dirs)


def parse_remote_bag_scan_output(output: str) -> tuple[list[dict], dict | None]:
    items = []
    disk = None
    for line in output.splitlines():
        if line.startswith("__DISK__\t"):
            parts = line.split("\t", 3)
            if len(parts) == 4:
                try:
                    disk = {"available": int(parts[1]), "total": int(parts[2]), "mount": parts[3]}
                except ValueError:
                    disk = None
            continue
        if line.startswith("__DISK_ERROR__\t"):
            continue
        parts = line.split("\t", 4)
        if len(parts) != 5:
            continue
        try:
            epoch = float(parts[0])
            size = int(parts[2])
            active = int(parts[3])
        except ValueError:
            continue
        path = parts[4]
        items.append(
            {
                "epoch": epoch,
                "mtime": parts[1],
                "size": size,
                "active": active,
                "path": path,
                "name": os.path.basename(path.rstrip("/")),
            }
        )
    return items, disk
