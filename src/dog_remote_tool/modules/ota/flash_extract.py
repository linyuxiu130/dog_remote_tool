from __future__ import annotations

from typing import Protocol

from dog_remote_tool.core.shell import quote
from dog_remote_tool.modules.ota.flash_tooling import (
    dfu_setup_lines,
    fastboot_device_count_lines,
    fastboot_setup_lines,
)


class FlashExtractTarget(Protocol):
    key: str
    label: str


def base_extract_script(target: FlashExtractTarget, package: str, package_type: str, *, require_fastboot: bool = True) -> list[str]:
    lines = [
        "set -euo pipefail",
        f"PACKAGE={quote(package)}",
        f"TARGET_LABEL={quote(target.label)}",
        f"TARGET_KEY={quote(target.key)}",
        f"PACKAGE_TYPE={quote(package_type)}",
        *fastboot_setup_lines(),
        'test -f "$PACKAGE" || { echo "[ERROR] 线刷包不存在: $PACKAGE"; exit 2; }',
        'FASTBOOT_DEVICES="$("$FASTBOOT_BIN" devices || true)"',
        *fastboot_device_count_lines(fatal=True),
    ]
    if require_fastboot:
        lines.extend(
            [
                'if [ -z "$FASTBOOT_DEVICES" ]; then',
                '  echo "[ERROR] 未检测到 fastboot 设备，请先让设备进入线刷/fastboot 模式并通过 USB 连接本机。"',
                "  exit 2",
                "fi",
            ]
        )
    else:
        lines.extend(
            [
                'if [ -z "$FASTBOOT_DEVICES" ]; then',
                '  echo "[flash] 当前未检测到 fastboot 设备，S100 将尝试 DFU 自动引导。"',
                "fi",
            ]
        )
    lines.extend(
        [
            'echo "[flash] 目标: $TARGET_LABEL"',
            'echo "[flash] fastboot: $FASTBOOT_BIN"',
            'if [ -n "$FASTBOOT_DEVICES" ]; then',
            '  echo "[flash] fastboot 设备:"',
            '  printf "%s\\n" "$FASTBOOT_DEVICES"',
            "fi",
            'ROOT="${XDG_CACHE_HOME:-$HOME/.cache}/dog_remote_tool/line_flash"',
            'mkdir -p "$ROOT"',
            'PKG_KEY="$(stat -c "%s_%Y" "$PACKAGE" | sha256sum | cut -c1-16)"',
            'PKG_BASE="$(basename "$PACKAGE")"',
            'PKG_BASE="${PKG_BASE%.tar.gz}"',
            'PKG_BASE="${PKG_BASE%.tgz}"',
            'WORKDIR="$ROOT/${PKG_BASE}_${PKG_KEY}"',
            'SIBLING_WORKDIR="${PACKAGE%.tar.gz}_extracted"',
            'if [ "$SIBLING_WORKDIR" = "$PACKAGE" ]; then SIBLING_WORKDIR="${PACKAGE%.tgz}_extracted"; fi',
            'if [ -d "$WORKDIR/.complete" ]; then',
            '  echo "[flash] 复用已解压缓存目录: $WORKDIR"',
            'elif [ -d "$SIBLING_WORKDIR" ] && find -L "$SIBLING_WORKDIR" -path "*/product/img_packages/flash_all.sh" -print -quit | grep -q .; then',
            '  WORKDIR="$SIBLING_WORKDIR"',
            '  echo "[flash] 复用包旁已解压目录: $WORKDIR"',
            "else",
            '  rm -rf "$WORKDIR"',
            '  mkdir -p "$WORKDIR"',
            '  echo "[flash] 解压线刷包到: $WORKDIR"',
            '  (',
            '    while true; do',
            '      sleep 5',
            '      [ -d "$WORKDIR" ] || continue',
            '      echo "[flash] 解压进度: $(du -sh "$WORKDIR" 2>/dev/null | awk \'{print $1}\')"',
            '    done',
            '  ) &',
            '  PROGRESS_PID=$!',
            '  trap \'kill "$PROGRESS_PID" 2>/dev/null || true\' EXIT',
            '  tar -xzf "$PACKAGE" -C "$WORKDIR"',
            '  kill "$PROGRESS_PID" 2>/dev/null || true',
            '  trap - EXIT',
            '  mkdir -p "$WORKDIR/.complete"',
            '  echo "[flash] 解压完成: $(du -sh "$WORKDIR" | awk \'{print $1}\')"',
            "fi",
        ]
    )
    if not require_fastboot:
        lines[lines.index('echo "[flash] 目标: $TARGET_LABEL"') : lines.index('echo "[flash] 目标: $TARGET_LABEL"')] = [
            *dfu_setup_lines(required=True),
            'echo "[flash] dfu-util: $DFU_BIN"',
        ]
    return lines
