from __future__ import annotations

import os
import shlex

from dog_remote_tool.modules.bag.remote_status import record_process_match_awk_functions


def remote_bag_scan_command(scan_dirs: list[str]) -> str:
    base_dir = scan_dirs[0]
    dir_list = " ".join(shlex.quote(path) for path in scan_dirs)
    return f"""
base_dir={shlex.quote(base_dir)}
if [ -d "$base_dir" ]; then
  df -PB1 "$base_dir" 2>/dev/null | awk 'NR==2 {{printf "__DISK__\\t%s\\t%s\\t%s\\n", $4, $2, $6}}'
else
  printf "__DISK_ERROR__\\t%s\\n" "$base_dir"
fi
for dir in {dir_list}; do
  [ -d "$dir" ] || continue
  find "$dir" -maxdepth 1 -regextype posix-extended -type d -regex '.*/(rosbag2_)?(xg|zg|air|l2)_[0-9]{{8}}_[0-9]{{6}}' -printf '%T@\\t%TY-%Tm-%Td %TH:%TM\\t%p\\n'
done |
sort -nr |
head -100 |
while IFS="$(printf '\\t')" read -r epoch mtime path; do
  size=$(du -sb "$path" 2>/dev/null | awk '{{print $1}}')
  active=$(ps -eww -o pid=,cmd= | awk -v path="$path" '{record_process_match_awk_functions()}
index($0, "ros2 bag record") > 0 && has_output_path($0, path) {{count++}} END {{print count+0}}')
  printf '%s\\t%s\\t%s\\t%s\\t%s\\n' "$epoch" "$mtime" "${{size:-0}}" "$active" "$path"
done
"""


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
