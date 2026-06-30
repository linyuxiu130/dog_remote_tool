#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

export DOG_REMOTE_TOOL_ROOT="$ROOT"
export DOG_REMOTE_TOOL_CLI="${DOG_REMOTE_TOOL_CLI:-python3 -m dog_remote_tool}"
export PYTHONPATH="$ROOT/src${PYTHONPATH:+:$PYTHONPATH}"

case "${1:-}" in
  --check-l2-versions|--check-versions|检查小包|小包版本)
    shift
    python3 - "$@" <<'PY'
from __future__ import annotations

import subprocess
import sys

from dog_remote_tool.core.profiles import get_product
from dog_remote_tool.modules.device_status import package_detail, parse_probe_output, probe_command


DEFAULT_TARGETS = ("xg2_3588", "xg2_s100")


def print_versions(key: str) -> bool:
    try:
        profile = get_product(key)
    except KeyError:
        print(f"=== {key} ===")
        print("未知设备配置")
        return False

    print(f"=== {profile.label} ({profile.target}) ===")
    result = subprocess.run(
        probe_command(profile).command,
        shell=True,
        text=True,
        capture_output=True,
        timeout=30,
    )
    if result.returncode != 0:
        print(f"读取失败: exit={result.returncode}")
        if result.stderr.strip():
            print(result.stderr.strip())
        return False

    status = parse_probe_output(result.stdout)
    print(f"主机名: {status.hostname or '-'}")
    print(f"设备版本: {status.release_version or '未找到'}")
    print("小包版本:")
    print(package_detail(status.packages))
    return True


targets = tuple(sys.argv[1:]) or DEFAULT_TARGETS
ok = True
for index, target in enumerate(targets):
    if index:
        print()
    ok = print_versions(target) and ok

raise SystemExit(0 if ok else 1)
PY
    exit $?
    ;;
  -h|--help)
    echo "用法:"
    echo "  bash 启动.sh                         启动图形工具"
    echo "  bash 启动.sh --check-l2-versions     检查 L2 3588/S100 小包版本"
    echo "  bash 启动.sh --check-versions xg1_nx 检查指定设备配置的小包版本"
    exit 0
    ;;
esac

EXISTING="$(ps -eo pid=,args= | awk -v self="$$" '
  $1 == self {next}
  $0 ~ /^[[:space:]]*[0-9]+[[:space:]]+([^[:space:]]*\/)?python3 -m dog_remote_tool([[:space:]]|$)/ {print; exit}
')"
if [ -n "$EXISTING" ]; then
  echo "远程调试平台已在运行，请先关闭旧窗口后再启动。"
  echo "$EXISTING"
  exit 1
fi

export QT_AUTO_SCREEN_SCALE_FACTOR=0
export QT_ENABLE_HIGHDPI_SCALING=1

exec python3 -m dog_remote_tool "$@"
