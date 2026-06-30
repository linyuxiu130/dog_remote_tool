from __future__ import annotations

from dog_remote_tool.core.shell import quote
from dog_remote_tool.modules.ota.flash_extract import base_extract_script
from dog_remote_tool.modules.ota.flash_s100_dfu import s100_dfu_boot_lines
from dog_remote_tool.modules.ota.flash_s100_fastboot import s100_fastboot_recovery_lines
from dog_remote_tool.modules.ota.flash_tooling import fastboot_device_count_lines, xburn_setup_lines
from dog_remote_tool.modules.ota.flash_types import FlashTarget


def s100_flash_script(target: FlashTarget, package: str) -> str:
    lines = base_extract_script(target, package, "s100_flash", require_fastboot=False)
    lines.extend(
        [
            'FLASH_DIR="$(find -L "$WORKDIR" -path "*/product/img_packages/flash_all.sh" -printf "%h\\n" -quit)"',
            'if [ -z "$FLASH_DIR" ]; then echo "[ERROR] 未找到 S100 线刷入口 product/img_packages/flash_all.sh"; exit 2; fi',
            'S100_BOOT_ROOT="$(dirname "$FLASH_DIR")"',
            'test -d "$S100_BOOT_ROOT/xmodem_tools" || { echo "[ERROR] 未找到 S100 DFU 引导目录: $S100_BOOT_ROOT/xmodem_tools"; exit 2; }',
            'cd "$FLASH_DIR"',
            'for REQUIRED in flash_all.sh fpt.img HSM_FW.img HSM_RCA.img keyimage_ohp.img SBL.img scp.img spl.img MCU_S100_V1.0.img misc.img disk/miniboot_flash.img disk/miniboot_flash_nose.img system.img; do',
            '  test -f "$REQUIRED" || { echo "[ERROR] S100 线刷包缺少依赖: $REQUIRED"; exit 2; }',
            "done",
            *s100_dfu_boot_lines(target),
            *s100_fastboot_recovery_lines(),
            *xburn_setup_lines(),
            'FASTBOOT_DEVICES="$("$FASTBOOT_BIN" devices || true)"',
            *fastboot_device_count_lines(fatal=True),
            'if [ -z "$FASTBOOT_DEVICES" ]; then',
            '  echo "[ERROR] DFU 引导后仍未检测到 fastboot 设备，停止线刷。"',
            "  exit 2",
            "fi",
            'echo "[flash] fastboot 设备:"',
            'printf "%s\\n" "$FASTBOOT_DEVICES"',
            'if ! s100_select_bootintf; then',
            '  echo "[ERROR] 未读取到 bootintf，且无法从 DOG_REMOTE_TOOL_S100_STORAGE_TYPE 或包内唯一整盘镜像推断介质；停止线刷。"',
            '  exit 2',
            "fi",
            'case "$BOOTINTF" in',
            '  mmc)',
            '    test -f disk/emmc_disk.simg || { echo "[ERROR] bootintf=mmc，需要 eMMC 整盘镜像 disk/emmc_disk.simg，但当前包缺失；包和设备介质不匹配。"; exit 2; }',
            "    ;;",
            '  scsi)',
            '    test -f disk/ufs_disk.simg || { echo "[ERROR] bootintf=scsi，需要 UFS 整盘镜像 disk/ufs_disk.simg，但当前包缺失；包和设备介质不匹配，当前包不能刷 UFS 设备。"; exit 2; }',
            "    ;;",
            '  *)',
            '    echo "[ERROR] 未支持的 bootintf: $BOOTINTF"',
            "    exit 2",
            "    ;;",
            "esac",
            'test -f system.img || { echo "[ERROR] 未找到 system.img"; exit 2; }',
            'echo "[DOG_REMOTE_STAGE] upgrade_locked"',
            'echo "[flash] bootintf: $BOOTINTF${S100_BOOTINTF_SOURCE:+ ($S100_BOOTINTF_SOURCE)}"',
            'SECFLAG="$(s100_fastboot_getvar secflag || true)"',
            'LIFECYCLE="$(s100_fastboot_getvar lifecycle || true)"',
            'case "$SECFLAG" in',
            '  0|1) ;;',
            '  *)',
            '    case "${DOG_REMOTE_TOOL_S100_SECURITY_TYPE:-}" in',
            '      secure|secure_ohp) SECFLAG=1; echo "[WARN] 未从设备读取到 secflag，按手动指定安全类型继续: DOG_REMOTE_TOOL_S100_SECURITY_TYPE=${DOG_REMOTE_TOOL_S100_SECURITY_TYPE}" ;;',
            '      nosecure) SECFLAG=0; echo "[WARN] 未从设备读取到 secflag，按手动指定安全类型继续: DOG_REMOTE_TOOL_S100_SECURITY_TYPE=nosecure" ;;',
            '      "")',
            '        if [ "${S100_BOOT_SECURITY:-secure}" = "nosecure" ]; then SECFLAG=0; else SECFLAG=1; fi',
            '        echo "[WARN] 未从设备读取到 secflag，按 DFU 引导安全类型推断: S100_BOOT_SECURITY=${S100_BOOT_SECURITY:-secure} secflag=$SECFLAG"',
            '        ;;',
            '      *) echo "[ERROR] 不支持的 DOG_REMOTE_TOOL_S100_SECURITY_TYPE: ${DOG_REMOTE_TOOL_S100_SECURITY_TYPE}；可用值: secure、secure_ohp、nosecure。"; exit 2 ;;',
            '    esac',
            '    ;;',
            "esac",
            'case "$LIFECYCLE" in ""|*[!0-9]*) LIFECYCLE=0 ;; esac',
            'LIFECYCLE="${LIFECYCLE:-0}"',
            'if [ "$BOOTINTF" = "mmc" ]; then',
            '  MINIBOOT_IMG="miniboot_emmc.img"',
            '  DISK_IMG="emmc_disk.simg"',
            "else",
            '  MINIBOOT_IMG="miniboot_ufs.img"',
            '  DISK_IMG="ufs_disk.simg"',
            "fi",
            'if [ "$SECFLAG" = "1" ]; then',
            '  SECURITY_MODE="true"',
            '  FLASH_DISK_IMG="miniboot_flash.img"',
            '  XBURN_SECURITY_TYPE="secure"',
            "else",
            '  SECURITY_MODE="false"',
            '  FLASH_DISK_IMG="miniboot_flash_nose.img"',
            '  XBURN_SECURITY_TYPE="nosecure"',
            "fi",
            'if [ "$SECFLAG" = "1" ] && [ "$LIFECYCLE" -ge 4 ] 2>/dev/null; then',
            '  XBURN_SECURITY_TYPE="secure_ohp"',
            "fi",
            'if [ "$BOOTINTF" = "mmc" ]; then XBURN_STORAGE_TYPE="emmc"; else XBURN_STORAGE_TYPE="ufs"; fi',
            'S100_USE_XBURN="${DOG_REMOTE_TOOL_S100_USE_XBURN:-0}"',
            'if [ "$S100_USE_XBURN" != "0" ]; then',
            '  XBURN_INPUT_DIR="${S100_BOOT_ROOT:-$FLASH_DIR}"',
            '  XBURN_BATCH_NUM="${DOG_REMOTE_TOOL_S100_BATCH_NUM:-1}"',
            '  XBURN_REBOOT_ARGS=()',
            '  if [ "${DOG_REMOTE_TOOL_S100_XBURN_REBOOT:-0}" = "1" ]; then XBURN_REBOOT_ARGS+=(--reboot); fi',
            '  echo "[DOG_REMOTE_STAGE] upgrade_locked"',
            '  echo "[flash] bootintf: $BOOTINTF"',
            '  echo "[flash] 开始 S100 xburn 全量线刷: security=$XBURN_SECURITY_TYPE storage=$XBURN_STORAGE_TYPE input=$XBURN_INPUT_DIR batch=$XBURN_BATCH_NUM"',
            '  "$XBURN_BIN" -V info -p RDKS100 -l usb -d fastboot --storage_type "$XBURN_STORAGE_TYPE" --security_type "$XBURN_SECURITY_TYPE" -i "$XBURN_INPUT_DIR" --batch_num "$XBURN_BATCH_NUM" "${XBURN_REBOOT_ARGS[@]}"',
            '  echo "[flash] S100 xburn 线刷命令已完成，等待系统启动后恢复 SSH。"',
            "  exit 0",
            "fi",
            'FASTBOOT_SPARSE_SIZE="${DOG_REMOTE_TOOL_FASTBOOT_SPARSE_SIZE:-64M}"',
            'fastboot_checked() {',
            '  echo "[flash] fastboot $*"',
            '  "$FASTBOOT_BIN" "$@"',
            "}",
            'echo "[flash] 开始 S100 全量线刷: security=$SECURITY_MODE lifecycle=$LIFECYCLE miniboot=$MINIBOOT_IMG disk=$DISK_IMG sparse=$FASTBOOT_SPARSE_SIZE"',
            'echo "[flash] 阶段 1/3: MTD/NOR"',
            'fastboot_checked oem interface:mtd',
            'if [ "$SECURITY_MODE" = "true" ] && [ "$LIFECYCLE" -ge 4 ] 2>/dev/null; then',
            '  fastboot_checked flash fpt fpt.img',
            '  fastboot_checked flash HSM_FW HSM_FW.img',
            '  fastboot_checked flash HSM_FW_bak HSM_FW.img',
            '  fastboot_checked flash HSM_RCA HSM_RCA.img',
            '  fastboot_checked flash HSM_RCA_bak HSM_RCA.img',
            '  fastboot_checked flash keyimage keyimage_ohp.img',
            '  fastboot_checked flash keyimage_bak keyimage_ohp.img',
            '  fastboot_checked flash SBL SBL.img',
            '  fastboot_checked flash SBL_bak SBL.img',
            '  fastboot_checked flash scp_a scp.img',
            '  fastboot_checked flash scp_b scp.img',
            '  fastboot_checked flash spl_a spl.img',
            '  fastboot_checked flash spl_b spl.img',
            '  fastboot_checked flash MCU_a MCU_S100_V1.0.img',
            '  fastboot_checked flash MCU_b MCU_S100_V1.0.img',
            '  fastboot_checked flash misc misc.img',
            "else",
            '  test -f "disk/$FLASH_DISK_IMG" || { echo "[ERROR] 缺少 MTD 镜像: disk/$FLASH_DISK_IMG"; exit 2; }',
            '  fastboot_checked flash hb_vspiflash "disk/$FLASH_DISK_IMG"',
            "fi",
            'echo "[flash] 阶段 2/3: eMMC/UFS 整盘镜像"',
            'fastboot_checked oem interface:blk',
            'test -f "disk/$DISK_IMG" || { echo "[ERROR] 缺少整盘镜像: disk/$DISK_IMG"; exit 2; }',
            'fastboot_checked -S "$FASTBOOT_SPARSE_SIZE" flash 0x0 "disk/$DISK_IMG"',
            'echo "[flash] 阶段 3/3: reboot"',
            'fastboot_checked reboot',
            'echo "[flash] S100 全量线刷命令已完成，等待系统启动后恢复 SSH。"',
        ]
    )
    return "\n".join(lines)


def orin_flash_script(target: FlashTarget, package: str) -> str:
    lines = base_extract_script(target, package, "orin_flash")
    lines.extend(
        [
            'FLASHCMD="$(find -L "$WORKDIR" -path "*/bootloader/flashcmd.txt" -print -quit)"',
            'if [ -z "$FLASHCMD" ]; then echo "[ERROR] 未找到 Orin NX 线刷入口 bootloader/flashcmd.txt"; exit 2; fi',
            'FLASH_DIR="$(dirname "$FLASHCMD")"',
            'cd "$FLASH_DIR"',
            'test -f system.img || { echo "[ERROR] 未找到 bootloader/system.img"; exit 2; }',
            'echo "[DOG_REMOTE_STAGE] upgrade_locked"',
            'echo "[flash] 开始 Orin NX 线刷: bash $FLASHCMD"',
            "bash ./flashcmd.txt",
        ]
    )
    return "\n".join(lines)


def unsupported_flash_script(target: FlashTarget, package: str) -> str:
    return "\n".join(
        [
            "set -euo pipefail",
            f"PACKAGE={quote(package)}",
            f"TARGET_LABEL={quote(target.label)}",
            'echo "[flash] 目标: $TARGET_LABEL"',
            'echo "[flash] 包: $PACKAGE"',
            'echo "[ERROR] 未识别线刷包类型，不能自动执行。请选择 S100 flash_all.sh 包或 Orin bootloader/flashcmd.txt 包。"',
            "exit 2",
        ]
    )


def unsupported_s100_target_script(target: FlashTarget, package: str) -> str:
    return "\n".join(
        [
            "set -euo pipefail",
            f"PACKAGE={quote(package)}",
            f"TARGET_LABEL={quote(target.label)}",
            'echo "[flash] 目标: $TARGET_LABEL"',
            'echo "[flash] 包: $PACKAGE"',
            'echo "[ERROR] S100 DFU 线刷目前只允许在小狗 L2 S100 或中狗环视 S100 目标下执行。"',
            'echo "[ERROR] 请先在顶部当前设备切到 小狗二代 S100 或 中狗环视版 S100。"',
            "exit 2",
        ]
    )
