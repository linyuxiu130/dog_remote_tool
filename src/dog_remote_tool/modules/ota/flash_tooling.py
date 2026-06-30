from __future__ import annotations

from dog_remote_tool.core.shell import quote
from dog_remote_tool.modules.ota.flash_resources import (
    bundled_dfu_util_path,
    bundled_fastboot_path,
    bundled_xburn_path,
)


def fastboot_setup_lines() -> list[str]:
    bundled = bundled_fastboot_path()
    return [
        f"BUNDLED_FASTBOOT={quote(str(bundled))}",
        'FASTBOOT_BIN="${DOG_REMOTE_TOOL_FASTBOOT:-}"',
        'if [ -n "$FASTBOOT_BIN" ] && [ ! -x "$FASTBOOT_BIN" ]; then',
        '  echo "[ERROR] DOG_REMOTE_TOOL_FASTBOOT 不可执行: $FASTBOOT_BIN"',
        "  exit 2",
        "fi",
        'if [ -z "$FASTBOOT_BIN" ] && [ -x "$BUNDLED_FASTBOOT" ]; then',
        '  FASTBOOT_BIN="$BUNDLED_FASTBOOT"',
        "fi",
        'if [ -z "$FASTBOOT_BIN" ] && command -v fastboot >/dev/null 2>&1; then',
        '  FASTBOOT_BIN="$(command -v fastboot)"',
        "fi",
        'if [ -z "$FASTBOOT_BIN" ]; then',
        '  echo "[ERROR] 未找到 fastboot；请保留工具内置 resources/platform-tools/linux-x86_64/bin/fastboot，或安装系统 fastboot。"',
        "  exit 2",
        "fi",
        'FASTBOOT_DIR="$(dirname "$FASTBOOT_BIN")"',
        'export PATH="$FASTBOOT_DIR:$PATH"',
    ]


def fastboot_device_count_lines(*, fatal: bool) -> list[str]:
    level = "ERROR" if fatal else "WARN"
    action = "exit 2" if fatal else "true"
    return [
        'FASTBOOT_DEVICE_COUNT="$(printf "%s\\n" "$FASTBOOT_DEVICES" | sed \'/^[[:space:]]*$/d\' | wc -l | tr -d " ")"',
        'if [ "${FASTBOOT_DEVICE_COUNT:-0}" -gt 1 ]; then',
        f'  echo "[{level}] 检测到多个 fastboot 设备，请只连接一台待刷设备。"',
        '  printf "%s\\n" "$FASTBOOT_DEVICES"',
        f"  {action}",
        "fi",
    ]


def dfu_setup_lines(*, required: bool = True) -> list[str]:
    bundled = bundled_dfu_util_path()
    missing_lines = [
        '  echo "[ERROR] 未找到 dfu-util；请保留工具内置 resources/platform-tools/linux-x86_64/bin/dfu-util，或安装系统 dfu-util。"',
        "  exit 2",
    ]
    if not required:
        missing_lines = [
            '  echo "[WARN] 未找到 dfu-util；S100 自动 DFU 引导不可用，但已在 fastboot 的设备仍可检查。"',
            '  DFU_BIN=""',
        ]
    return [
        f"BUNDLED_DFU={quote(str(bundled))}",
        'DFU_BIN="${DOG_REMOTE_TOOL_DFU_UTIL:-}"',
        'if [ -n "$DFU_BIN" ] && [ ! -x "$DFU_BIN" ]; then',
        '  echo "[ERROR] DOG_REMOTE_TOOL_DFU_UTIL 不可执行: $DFU_BIN"',
        "  exit 2",
        "fi",
        'if [ -z "$DFU_BIN" ] && [ -x "$BUNDLED_DFU" ]; then',
        '  DFU_BIN="$BUNDLED_DFU"',
        "fi",
        'if [ -z "$DFU_BIN" ] && command -v dfu-util >/dev/null 2>&1; then',
        '  DFU_BIN="$(command -v dfu-util)"',
        "fi",
        'if [ -z "$DFU_BIN" ]; then',
        *missing_lines,
        "fi",
        'if [ -n "$DFU_BIN" ]; then',
        'DFU_DIR="$(dirname "$DFU_BIN")"',
        'export PATH="$DFU_DIR:$PATH"',
        "fi",
    ]


def xburn_setup_lines() -> list[str]:
    bundled = bundled_xburn_path()
    return [
        f"BUNDLED_XBURN={quote(str(bundled))}",
        'XBURN_BIN="${DOG_REMOTE_TOOL_XBURN:-}"',
        'if [ -n "$XBURN_BIN" ] && [ ! -x "$XBURN_BIN" ]; then',
        '  echo "[ERROR] DOG_REMOTE_TOOL_XBURN 不可执行: $XBURN_BIN"',
        "  exit 2",
        "fi",
        'if [ -z "$XBURN_BIN" ] && [ -x "$BUNDLED_XBURN" ]; then',
        '  XBURN_BIN="$BUNDLED_XBURN"',
        "fi",
        'if [ -z "$XBURN_BIN" ] && command -v xburn >/dev/null 2>&1; then',
        '  XBURN_BIN="$(command -v xburn)"',
        "fi",
        'if [ -z "$XBURN_BIN" ]; then',
        '  echo "[ERROR] 未找到 xburn；S100 整盘烧写需要工具内置 resources/xburn/linux-x86_64/bin/xburn，或安装系统 xburn。"',
        "  exit 2",
        "fi",
    ]
