from __future__ import annotations

from typing import Protocol

from dog_remote_tool.core.shell import quote
from dog_remote_tool.modules.ota.flash_s100_entry import s100_entry_help_lines
from dog_remote_tool.modules.ota.flash_s100_fastboot import s100_fastboot_recovery_lines
from dog_remote_tool.modules.ota.flash_s100_remote import s100_remote_probe_lines, s100_remote_setup_lines
from dog_remote_tool.modules.ota.flash_tooling import dfu_setup_lines, fastboot_setup_lines


class S100MonitorTarget(Protocol):
    key: str
    label: str
    host: str
    user: str
    password: str


def s100_entry_monitor_script(target: S100MonitorTarget) -> str:
    lines = [
        "set -euo pipefail",
        f"TARGET_LABEL={quote(target.label)}",
        *s100_remote_setup_lines(target),
        *s100_remote_probe_lines(),
        *fastboot_setup_lines(),
        *dfu_setup_lines(required=False),
        *s100_fastboot_recovery_lines(),
        *s100_entry_help_lines(),
        'echo "[flash] 目标: $TARGET_LABEL"',
        'echo "[flash] fastboot: $FASTBOOT_BIN"',
        'echo "[flash] dfu-util: ${DFU_BIN:-不可用}"',
        's100_print_entry_help',
        'WATCH_SECONDS="${DOG_REMOTE_TOOL_S100_ENTRY_WATCH_SECONDS:-45}"',
        'INTERVAL="${DOG_REMOTE_TOOL_S100_ENTRY_WATCH_INTERVAL:-1}"',
        'DEADLINE=$(( $(date +%s) + WATCH_SECONDS ))',
        'LAST_SUMMARY=""',
        'while [ "$(date +%s)" -le "$DEADLINE" ]; do',
        '  FASTBOOT_DEVICES="$("$FASTBOOT_BIN" devices || true)"',
        '  FASTBOOT_COUNT="$(printf "%s\\n" "$FASTBOOT_DEVICES" | sed \'/^[[:space:]]*$/d\' | wc -l | tr -d " ")"',
        '  DFU_DEVICES=""',
        '  if [ -n "${DFU_BIN:-}" ]; then DFU_DEVICES="$("$DFU_BIN" -l 2>&1 || true)"; fi',
        '  USB_LINES=""',
        '  if command -v lsusb >/dev/null 2>&1; then USB_LINES="$(lsusb 2>/dev/null | grep -Ei "3652:|1a86:(8091|7523)" || true)"; fi',
        '  SSHPASS_STATE="不可用"',
        '  if command -v sshpass >/dev/null 2>&1; then SSHPASS_STATE="可用"; fi',
        '  SSH_STATE="不可达"',
        '  SSH_LOGIN_STATE="未检查"',
        '  if [ "$SSHPASS_STATE" = "可用" ] && s100_select_reachable_remote_host >/dev/null 2>&1; then SSH_STATE="可达"; SSH_LOGIN_STATE="可登录"; fi',
        '  if [ "$SSH_STATE" = "不可达" ]; then',
        '    for candidate in $S100_REMOTE_HOST_CANDIDATES; do',
        '      if [ -n "$candidate" ] && timeout 1 bash -lc "</dev/tcp/$candidate/22" >/dev/null 2>&1; then S100_REMOTE_HOST="$candidate"; SSH_STATE="可达"; break; fi',
        "    done",
        "  fi",
        '  if [ "${FASTBOOT_COUNT:-0}" -gt 1 ]; then',
        '    SUMMARY="异常: 多台 fastboot 设备"',
        '  elif [ -n "$FASTBOOT_DEVICES" ]; then',
        '    BOOTINTF="$(s100_fastboot_getvar bootintf || true)"',
        '    SUMMARY="就绪: fastboot${BOOTINTF:+ bootintf=$BOOTINTF}"',
        '  elif printf "%s\\n" "$DFU_DEVICES" | grep -Eiq "\\[3652:6610\\]"; then',
        '    SUMMARY="就绪: S100 BootROM DFU 3652:6610"',
        '  elif printf "%s\\n" "$DFU_DEVICES" | grep -Eiq "\\[3652:(6615|6620|6625|6630|7610|7620|7630)\\]"; then',
        '    SUMMARY="中间态: D-Robotics DFU 非 6610，建议重新上电进 BootROM"',
        '  elif [ "$SSH_STATE" = "可达" ] && [ "$SSHPASS_STATE" = "可用" ] && [ "$SSH_LOGIN_STATE" = "可登录" ]; then',
        '    SUMMARY="可自动进入: SSH $S100_REMOTE_USER@$S100_REMOTE_HOST 登录可用，执行线刷时可尝试 reboot usb2 -f"',
        '  elif [ "$SSH_STATE" = "可达" ] && [ "$SSHPASS_STATE" = "可用" ]; then',
        '    SUMMARY="未就绪: SSH 端口可达但登录失败，不能确认可自动发送 reboot usb2 -f"',
        '  elif [ "$SSH_STATE" = "可达" ]; then',
        '    SUMMARY="未就绪: SSH 端口可达但本机 sshpass 不可用，无法自动发送 reboot usb2 -f"',
        '  elif printf "%s\\n" "$USB_LINES" | grep -Eiq "3652:"; then',
        '    SUMMARY="未就绪: 看到 3652 USB 设备但不是 BootROM DFU/fastboot，可能仍是运行态 USB"',
        '  elif printf "%s\\n" "$USB_LINES" | grep -Eiq "1a86:(8091|7523)"; then',
        '    SUMMARY="未就绪: 只看到 CH340/ttyUSB，尚未进入 3652:6610 或 fastboot"',
        "  else",
        '    SUMMARY="未就绪: 未看到 3652/CH340/fastboot，检查供电、Type-C 数据线和 S100 USB 口"',
        "  fi",
        '  if [ "$SUMMARY" != "$LAST_SUMMARY" ]; then',
        '    echo "[flash] $(date +%H:%M:%S) $SUMMARY"',
        '    [ -n "$FASTBOOT_DEVICES" ] && printf "%s\\n" "$FASTBOOT_DEVICES"',
        '    [ -n "$USB_LINES" ] && printf "%s\\n" "$USB_LINES"',
        '    echo "[flash] SSH: $S100_REMOTE_USER@$S100_REMOTE_HOST 入口=$SSH_STATE 登录=$SSH_LOGIN_STATE sshpass=$SSHPASS_STATE 候选=$S100_REMOTE_HOST_CANDIDATES"',
        '    LAST_SUMMARY="$SUMMARY"',
        "  fi",
        '  case "$SUMMARY" in 就绪:*|可自动进入:*) exit 0 ;; esac',
        '  sleep "$INTERVAL"',
        "done",
        'echo "[WARN] 观察超时，仍未进入 S100 刷写入口。"',
        's100_print_entry_help',
        "exit 1",
    ]
    return "\n".join(lines)
