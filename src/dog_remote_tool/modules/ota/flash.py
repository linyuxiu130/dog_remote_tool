from __future__ import annotations

from dog_remote_tool.core.shell import CommandSpec, quote
from dog_remote_tool.modules.ota import flash_extract as _flash_extract
from dog_remote_tool.modules.ota import flash_package as _flash_package
from dog_remote_tool.modules.ota import flash_s100_dfu as _flash_s100_dfu
from dog_remote_tool.modules.ota import flash_s100_entry as _flash_s100_entry
from dog_remote_tool.modules.ota import flash_s100_fastboot as _flash_s100_fastboot
from dog_remote_tool.modules.ota import flash_s100_monitor as _flash_s100_monitor
from dog_remote_tool.modules.ota import flash_s100_package_check as _flash_s100_package_check
from dog_remote_tool.modules.ota import flash_s100_remote as _flash_s100_remote
from dog_remote_tool.modules.ota import flash_tooling as _flash_tooling
from dog_remote_tool.modules.ota import flash_upgrade_scripts as _flash_upgrade_scripts
from dog_remote_tool.modules.ota.flash_tooling import (
    dfu_setup_lines,
    fastboot_device_count_lines,
    fastboot_setup_lines,
)
from dog_remote_tool.modules.ota.flash_types import FlashTarget, S100_FLASH_TARGET_KEYS


S100_BOOT_SECURITY_FILES = _flash_package.S100_BOOT_SECURITY_FILES
flash_detail_rows = _flash_package.flash_detail_rows
flash_type_hint = _flash_package.flash_type_hint
flash_type_label = _flash_package.flash_type_label
inspect_flash_package = _flash_package.inspect_flash_package
_base_extract_script = _flash_extract.base_extract_script
_s100_dfu_boot_lines = _flash_s100_dfu.s100_dfu_boot_lines
_s100_entry_help_lines = _flash_s100_entry.s100_entry_help_lines
_s100_entry_readiness_lines = _flash_s100_entry.s100_entry_readiness_lines
_s100_usb_diagnosis_lines = _flash_s100_entry.s100_usb_diagnosis_lines
_s100_fastboot_recovery_lines = _flash_s100_fastboot.s100_fastboot_recovery_lines
_s100_entry_monitor_script = _flash_s100_monitor.s100_entry_monitor_script
_s100_package_precheck_lines = _flash_s100_package_check.s100_package_precheck_lines
_s100_password_ssh_options = _flash_s100_remote.s100_password_ssh_options
_s100_remote_probe_lines = _flash_s100_remote.s100_remote_probe_lines
_s100_remote_setup_lines = _flash_s100_remote.s100_remote_setup_lines
_s100_flash_script = _flash_upgrade_scripts.s100_flash_script
_orin_flash_script = _flash_upgrade_scripts.orin_flash_script
_unsupported_flash_script = _flash_upgrade_scripts.unsupported_flash_script
_unsupported_s100_target_script = _flash_upgrade_scripts.unsupported_s100_target_script
xburn_setup_lines = _flash_tooling.xburn_setup_lines


def flash_precheck_command(target: FlashTarget, package: str) -> CommandSpec:
    package_type = flash_type_hint(package) or "line_flash"
    if package_type == "s100_flash" and target.key not in S100_FLASH_TARGET_KEYS:
        script = _unsupported_s100_target_script(target, package)
    else:
        script = _common_precheck_script(target, package, package_type)
    return CommandSpec(
        "线刷预检",
        script,
        description="只检查本机 fastboot、包类型和线刷入口提示，不执行刷写",
        display_command=f"执行：线刷预检（{target.label}）",
        concurrency="parallel",
    )


def s100_entry_monitor_command(target: FlashTarget) -> CommandSpec:
    return CommandSpec(
        "S100 刷写入口观察",
        _s100_entry_monitor_script(target),
        description="只读观察 S100 USB/fastboot/SSH 入口状态，不执行刷写或重启",
        display_command=f"执行：S100 刷写入口观察（{target.label}）",
        concurrency="parallel",
    )


def flash_upgrade_command(target: FlashTarget, package: str) -> CommandSpec:
    package_type = flash_type_hint(package) or "line_flash"
    if package_type == "s100_flash":
        if target.key in S100_FLASH_TARGET_KEYS:
            script = _s100_flash_script(target, package)
        else:
            script = _unsupported_s100_target_script(target, package)
    elif package_type == "orin_flash":
        script = _orin_flash_script(target, package)
    else:
        script = _unsupported_flash_script(target, package)
    return CommandSpec(
        "执行线刷",
        script,
        dangerous=True,
        description="在本机解压线刷包并执行 S100/Orin 本机 USB 线刷命令",
        display_command=f"执行：线刷升级（{target.label}）",
        locks=("flash",),
    )


def _common_precheck_script(target: FlashTarget, package: str, package_type: str) -> str:
    lines = [
        "set -euo pipefail",
        f"PACKAGE={quote(package)}",
        f"TARGET_LABEL={quote(target.label)}",
        f"TARGET_KEY={quote(target.key)}",
        f"PACKAGE_TYPE={quote(package_type)}",
        *fastboot_setup_lines(),
        'echo "[flash] 目标: $TARGET_LABEL"',
        'echo "[flash] 包: $PACKAGE"',
        'test -f "$PACKAGE" || { echo "[ERROR] 线刷包不存在: $PACKAGE"; exit 2; }',
        'echo "[flash] 类型: " "$PACKAGE_TYPE"',
        'echo "[flash] 大小: $(du -h "$PACKAGE" | awk \'{print $1}\')"',
        'echo "[flash] fastboot: $FASTBOOT_BIN"',
        'FASTBOOT_DEVICES="$("$FASTBOOT_BIN" devices || true)"',
        *fastboot_device_count_lines(fatal=False),
        'if [ -z "$FASTBOOT_DEVICES" ]; then',
        '  echo "[WARN] 当前未检测到 fastboot 设备。"',
        "else",
        '  echo "[flash] fastboot 设备:"',
        '  printf "%s\\n" "$FASTBOOT_DEVICES"',
        "fi",
    ]
    if package_type == "s100_flash":
        lines.extend(
            [
                *_s100_remote_setup_lines(target),
                *_s100_remote_probe_lines(),
                "S100_SSH_PORT_OPEN=0",
                "S100_HAS_EMMC_DISK=0",
                "S100_HAS_UFS_DISK=0",
                *dfu_setup_lines(required=False),
                *_s100_fastboot_recovery_lines(),
                'echo "[flash] dfu-util: $DFU_BIN"',
                'DFU_DEVICES=""',
                'if [ -n "$DFU_BIN" ]; then',
                '  DFU_DEVICES="$("$DFU_BIN" -l 2>&1 || true)"',
                "fi",
                'if printf "%s\\n" "$DFU_DEVICES" | grep -Eiq "\\[3652:(6610|6615|6620|6625|6630|7610|7620|7630)\\]"; then',
                '  echo "[flash] 检测到 D-Robotics DFU 设备，可执行自动引导。"',
                "else",
                '  echo "[flash] 当前未检测到 3652:66xx/76xx DFU 设备。"',
                "fi",
                *_s100_package_precheck_lines(),
                *_s100_entry_help_lines(),
                *_s100_usb_diagnosis_lines(),
                *_s100_entry_readiness_lines(),
            ]
        )
    lines.extend(
        [
            'case "$PACKAGE_TYPE" in',
            '  s100_flash)',
            f"    case {quote(target.key)} in {'|'.join(S100_FLASH_TARGET_KEYS)}) ;; *) echo \"[ERROR] S100 DFU 线刷目前只允许小狗 L2 S100 或中狗环视 S100 目标。\"; exit 2 ;; esac",
            '    echo "[flash] S100 线刷入口: product/img_packages；执行线刷时会自动 DFU 引导或直接使用 fastboot。"',
            '    if [ -n "$S100_REMOTE_HOST" ] && [ -n "$S100_REMOTE_USER" ]; then',
            '      echo "[flash] 如系统仍可 SSH，执行线刷时会先尝试候选地址: $S100_REMOTE_HOST_CANDIDATES -> sudo reboot usb2 -f"',
            '      echo "[flash] 可设置 DOG_REMOTE_TOOL_S100_AUTO_REBOOT=0 禁用自动 SSH 进入刷写状态。"',
            '      if command -v sshpass >/dev/null 2>&1; then',
            '        echo "[flash] sshpass: 可用"',
            '        if s100_select_reachable_remote_host; then',
            '          S100_SSH_PORT_OPEN=1',
            '          echo "[flash] SSH 入口: $S100_REMOTE_HOST:22 可登录，执行线刷时可尝试自动进入刷写状态。"',
            "        else",
            '          S100_SSH_PORT_OPEN=0',
            '          echo "[WARN] SSH 候选地址均不可登录: $S100_REMOTE_HOST_CANDIDATES；如果 USB 也没有 DFU/fastboot，需要手动按键进入线刷模式。"',
            "        fi",
            "      else",
            '        echo "[WARN] sshpass 不可用；执行线刷时无法自动 SSH 进入刷写状态。"',
            '        S100_SSH_PORT_OPEN=0',
            "      fi",
            "    fi",
            '    s100_report_usb_state',
            '    if [ -n "$FASTBOOT_DEVICES" ]; then',
            '      BOOTINTF="$(s100_fastboot_getvar bootintf || true)"',
            '      if [ -z "$BOOTINTF" ]; then',
            '        s100_reset_fastboot_usb || true',
            '        FASTBOOT_DEVICES="$("$FASTBOOT_BIN" devices || true)"',
            '        BOOTINTF="$(s100_fastboot_getvar bootintf || true)"',
            "      fi",
            '      if [ -n "$BOOTINTF" ]; then',
            '        echo "[flash] bootintf: $BOOTINTF"',
            "      else",
            '        echo "[WARN] 未读取到 bootintf；执行线刷时会再次检查，避免厂商脚本默认走 scsi/UFS。"',
            "      fi",
            "    else",
            '      echo "[flash] 未连接 fastboot 设备，跳过 bootintf 读取。"',
            "    fi",
            '    s100_report_entry_readiness',
            "    ;;",
            '  orin_flash) echo "[flash] Orin NX 线刷入口: bootloader/flashcmd.txt" ;;',
            '  *) echo "[ERROR] 未识别线刷包类型，请选择 S100 或 Orin NX 线刷包。"; exit 2 ;;',
            "esac",
        ]
    )
    return "\n".join(lines)
