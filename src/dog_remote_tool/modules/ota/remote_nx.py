from __future__ import annotations

from dog_remote_tool.modules.ota.remote_shell import human_bytes_shell, python_zip_extract_shell, remote_common_shell


def nx_remote_script() -> str:
    common_shell = remote_common_shell("远程NX")
    size_shell = human_bytes_shell()
    zip_extract_shell = python_zip_extract_shell()
    script = r"""
set -euo pipefail
PACKAGE_NAME="${PACKAGE_NAME:?}"
TOOLS_NAME="${TOOLS_NAME:?}"
REMOTE_DIR="${REMOTE_DIR:?}"
SUDO_PASSWORD="${SUDO_PASSWORD:?}"
RUN_UPGRADE="${RUN_UPGRADE:-0}"
SKIP_NX_MCU="${SKIP_NX_MCU:-0}"
AUTO_REBOOT_DELAY=5
ROBOT_LAUNCH_STOPPED=0
SKIP_ROBOT_LAUNCH_RESTART=0

__COMMON_SHELL__
__SIZE_SHELL__
inspect_ota_package() {
  python3 - "$1" <<'PY'
import json
import os
import re
import sys
import tarfile
import zipfile

path = sys.argv[1]

def inspect_tar(stream):
    with tarfile.open(fileobj=stream, mode="r|gz") as tf:
        for member in tf:
            if member.name.lstrip("./") == "ota_package.tar":
                return member.size
    raise SystemExit("未找到 ota_package.tar")

if zipfile.is_zipfile(path):
    with zipfile.ZipFile(path) as zf:
        data = {}
        info_names = ["package_info.json"] + sorted(
            info.filename
            for info in zf.infolist()
            if not info.is_dir() and info.filename.endswith("/package_info.json")
        )
        for name in info_names:
            try:
                data = json.loads(zf.read(name).decode("utf-8"))
                break
            except Exception:
                pass
        try:
            pattern = re.compile(data.get("system", {}).get("image_regex", ""))
        except Exception:
            pattern = None
        members = [info for info in zf.infolist() if not info.is_dir()]
        candidates = [info for info in members if pattern and pattern.search(info.filename)]
        if not candidates:
            candidates = [info for info in members if info.filename.lower().endswith((".tar.gz", ".tgz")) and "ota" in info.filename.lower()]
        if not candidates:
            raise SystemExit("未找到系统 OTA 包")
        info = candidates[0]
        with zf.open(info) as stream:
            payload_size = inspect_tar(stream)
        print(f"{payload_size}\t{info.filename}\t{info.file_size}\tzip")
else:
    with open(path, "rb") as stream:
        payload_size = inspect_tar(stream)
    print(f"{payload_size}\t{path}\t{os.path.getsize(path)}\ttar")
PY
}
PACKAGE_PATH="$REMOTE_DIR/$PACKAGE_NAME"
TOOLS_PATH="$REMOTE_DIR/$TOOLS_NAME"
if [ ! -f "$PACKAGE_PATH" ] && sudo_run test -f "/ota/$PACKAGE_NAME"; then
  log "远程目录未找到升级包，复用 /ota/$PACKAGE_NAME"
  PACKAGE_PATH="/ota/$PACKAGE_NAME"
fi
test -f "$PACKAGE_PATH" || die "升级包不存在: $PACKAGE_PATH"
test -f "$TOOLS_PATH" || die "工具包不存在: $TOOLS_PATH"
command -v python3 >/dev/null 2>&1 || die "缺少 python3"

log "预检升级包和磁盘空间"
PACKAGE_SIZE="$(stat -c '%s' "$PACKAGE_PATH")"
IFS="$(printf '\t')" read -r OTA_PAYLOAD_SIZE SYSTEM_MEMBER SYSTEM_ARCHIVE_SIZE PACKAGE_KIND <<EOF_INFO
$(inspect_ota_package "$PACKAGE_PATH")
EOF_INFO
ROOT_FREE_BYTES="$(space_bytes /)"
sudo_run mkdir -p /ota
OTA_FREE_BYTES="$(sudo_run df -PB1 /ota | awk 'NR==2 {print $4}')"
TARGET_PACKAGE_PATH="/ota/$(basename "$SYSTEM_MEMBER")"
TARGET_SIZE="$(sudo_run bash -lc "if [ -f $(printf '%q' "$TARGET_PACKAGE_PATH") ]; then stat -c '%s' $(printf '%q' "$TARGET_PACKAGE_PATH"); fi")"
if [ "$PACKAGE_KIND" = "tar" ] && [ "$TARGET_SIZE" = "$SYSTEM_ARCHIVE_SIZE" ] && [ "$PACKAGE_PATH" != "$TARGET_PACKAGE_PATH" ]; then
  log "/ota 目标文件已完整，删除远端暂存包释放空间"
  rm -f "$PACKAGE_PATH"
  PACKAGE_PATH="$TARGET_PACKAGE_PATH"
  ROOT_FREE_BYTES="$(space_bytes /)"
  OTA_FREE_BYTES="$(sudo_run df -PB1 /ota | awk 'NR==2 {print $4}')"
fi
REQUIRED_ROOT_FREE_BYTES="$((OTA_PAYLOAD_SIZE + 2147483648))"
log "升级包大小: $(human_bytes "$PACKAGE_SIZE")"
log "系统 OTA 包: $SYSTEM_MEMBER ($(human_bytes "$SYSTEM_ARCHIVE_SIZE"))"
log "包内 ota_package.tar: $(human_bytes "$OTA_PAYLOAD_SIZE")"
log "根分区可用: $(human_bytes "$ROOT_FREE_BYTES")"
log "/ota 可用: $(human_bytes "$OTA_FREE_BYTES")"
if (( ROOT_FREE_BYTES < REQUIRED_ROOT_FREE_BYTES )); then die "根分区空间不足，至少需要 $(human_bytes "$REQUIRED_ROOT_FREE_BYTES")"; fi
if (( OTA_FREE_BYTES < SYSTEM_ARCHIVE_SIZE )); then die "/ota 空间不足，至少需要 $(human_bytes "$SYSTEM_ARCHIVE_SIZE")"; fi

log "解压 ota tools"
OTA_RUNTIME_DIR="$HOME/ota_runtime"
rm -rf "$OTA_RUNTIME_DIR"
mkdir -p "$OTA_RUNTIME_DIR"
tar xpf "$TOOLS_PATH" -C "$OTA_RUNTIME_DIR"
OTA_TOOL_DIR="$OTA_RUNTIME_DIR/Linux_for_Tegra/tools/ota_tools/version_upgrade"
test -f "$OTA_TOOL_DIR/nv_ota_start.sh" || die "未找到 nv_ota_start.sh"

PACKAGE_STEM="$PACKAGE_NAME"
case "$PACKAGE_NAME" in
  *.tar.gz) PACKAGE_STEM="${PACKAGE_NAME%.tar.gz}" ;;
  *.zip) PACKAGE_STEM="${PACKAGE_NAME%.zip}" ;;
esac
WORK_DIR="$REMOTE_DIR/${PACKAGE_STEM}_$(date +%Y%m%d_%H%M%S)"
SYSTEM_SOURCE="$PACKAGE_PATH"

if [ "$PACKAGE_KIND" = "zip" ]; then
  rm -rf "$WORK_DIR"
  mkdir -p "$WORK_DIR"
  log "解压中狗 NX ZIP 包"
__ZIP_EXTRACT_SHELL__
  SYSTEM_SOURCE="$WORK_DIR/$SYSTEM_MEMBER"
  test -f "$SYSTEM_SOURCE" || die "未找到系统 OTA 包: $SYSTEM_SOURCE"
  chmod +x "$WORK_DIR"/*/tool/* "$WORK_DIR"/tool/* 2>/dev/null || true
fi

log "准备升级文件"
TARGET_PACKAGE_PATH="/ota/$(basename "$SYSTEM_SOURCE")"
TARGET_SIZE="$(sudo_run bash -lc "if [ -f $(printf '%q' "$TARGET_PACKAGE_PATH") ]; then stat -c '%s' $(printf '%q' "$TARGET_PACKAGE_PATH"); fi")"
if [ "$TARGET_SIZE" = "$SYSTEM_ARCHIVE_SIZE" ]; then
  log "目标文件已存在且大小一致，跳过复制"
else
  sudo_run cp "$SYSTEM_SOURCE" /ota/
fi
FINAL_SIZE="$(sudo_run stat -c '%s' "$TARGET_PACKAGE_PATH")"
test "$FINAL_SIZE" = "$SYSTEM_ARCHIVE_SIZE" || die "/ota 文件大小校验失败"
log "prepare-only 阶段完成"

if [ "$RUN_UPGRADE" != "1" ]; then
  log "未执行 nv_ota_start.sh"
  exit 0
fi

echo "[DOG_REMOTE_STAGE] upgrade_locked"
if [ "$PACKAGE_KIND" = "zip" ] && [ "$SKIP_NX_MCU" != "1" ]; then
  rtk_fw="$(find_one '*/firmware/rtk*.bin' 'rtk_mcu 固件')"
  rtk_tool="$(find_one '*/tool/mcu_upgrade*' 'mcu_upgrade')"
  chmod +x "$rtk_tool"
  log "停止 robot-launch.service，释放 NX 串口设备"
  sudo_run systemctl stop robot-launch.service
  ROBOT_LAUNCH_STOPPED=1
  run_retry "刷写 rtk_mcu" "$rtk_tool" -d /dev/ttyTHS3 -t rtk_mcu -f "$rtk_fw"
elif [ "$PACKAGE_KIND" = "zip" ]; then
  log "跳过 rtk_mcu 刷写"
fi
log "执行 OTA 升级"
cd "$OTA_TOOL_DIR"
sudo_run ./nv_ota_start.sh "$TARGET_PACKAGE_PATH"
log "OTA 命令已完成，${AUTO_REBOOT_DELAY} 秒后自动重启"
SKIP_ROBOT_LAUNCH_RESTART=1
sudo_run bash -lc "nohup sh -c 'sleep ${AUTO_REBOOT_DELAY}; sync; reboot' >/dev/null 2>&1 &"
"""
    return (
        script.replace("__COMMON_SHELL__", common_shell)
        .replace("__SIZE_SHELL__", size_shell)
        .replace("__ZIP_EXTRACT_SHELL__", zip_extract_shell)
    )
