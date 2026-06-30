from __future__ import annotations

from dog_remote_tool.core.quoting import quote


def nx_precheck_script(
    remote_dir: str,
    package_name: str,
    package_is_zip: bool,
    package_size: int,
    payload_size: int,
    system_archive_size: int,
    tools_size: int,
    zip_extract_size: int,
) -> str:
    script = r"""
set -euo pipefail
REMOTE_DIR=__REMOTE_DIR__
PACKAGE_NAME=__PACKAGE_NAME__
PACKAGE_IS_ZIP=__PACKAGE_IS_ZIP__
PACKAGE_SIZE=__PACKAGE_SIZE__
PAYLOAD_SIZE=__PAYLOAD_SIZE__
SYSTEM_ARCHIVE_SIZE=__SYSTEM_ARCHIVE_SIZE__
TOOLS_SIZE=__TOOLS_SIZE__
ZIP_EXTRACT_SIZE=__ZIP_EXTRACT_SIZE__
SUDO_PASSWORD="${SUDO_PASSWORD:?}"
case "$REMOTE_DIR" in
  ~*) REMOTE_DIR="$HOME${REMOTE_DIR#\~}" ;;
esac
mkdir -p "$REMOTE_DIR"
test_file="$REMOTE_DIR/.ota_precheck_$$"
: > "$test_file"
rm -f "$test_file"
sudo_run() { printf '%s\n' "$SUDO_PASSWORD" | sudo -S -p '' "$@"; }
space_bytes() { df -PB1 "$1" | awk 'NR==2 {print $4}'; }
fs_dev() { df -P "$1" | awk 'NR==2 {print $1}'; }
human_bytes() {
  awk -v bytes="${1:-0}" 'BEGIN { split("B KiB MiB GiB TiB", u, " "); v=bytes+0; i=1; while (v>=1024 && i<5) {v/=1024; i++}; if (i==1) printf "%.0f %s", v, u[i]; else printf "%.2f %s", v, u[i] }'
}
command -v sudo >/dev/null 2>&1 || { echo "缺少 sudo"; exit 1; }
command -v python3 >/dev/null 2>&1 || { echo "缺少 python3"; exit 1; }
sudo_run mkdir -p /ota
sudo_run bash -lc ': > /ota/.ota_precheck_$$ && rm -f /ota/.ota_precheck_$$'
REMOTE_FREE="$(space_bytes "$REMOTE_DIR")"
ROOT_FREE="$(space_bytes /)"
OTA_FREE="$(sudo_run df -PB1 /ota | awk 'NR==2 {print $4}')"
REMOTE_DEV="$(fs_dev "$REMOTE_DIR")"
OTA_DEV="$(sudo_run df -P /ota | awk 'NR==2 {print $1}')"
UPLOAD_NEED=$((PACKAGE_SIZE + TOOLS_SIZE + ZIP_EXTRACT_SIZE))
OTA_NEED=$SYSTEM_ARCHIVE_SIZE
if [ "$PACKAGE_IS_ZIP" != "1" ]; then
  TARGET_PACKAGE_PATH="/ota/$PACKAGE_NAME"
  TARGET_SIZE="$(sudo_run bash -lc "if [ -f $(printf '%q' "$TARGET_PACKAGE_PATH") ]; then stat -c '%s' $(printf '%q' "$TARGET_PACKAGE_PATH"); fi")"
  if [ "$TARGET_SIZE" = "$SYSTEM_ARCHIVE_SIZE" ]; then
    OTA_NEED=0
    echo "/ota 目标文件已存在且大小一致，跳过 /ota 空间预留"
  fi
fi
ROOT_NEED=$((PAYLOAD_SIZE + 2147483648))
echo "远程目录: $REMOTE_DIR"
echo "远程目录可用: $(human_bytes "$REMOTE_FREE")"
echo "根分区可用: $(human_bytes "$ROOT_FREE")"
echo "/ota 可用: $(human_bytes "$OTA_FREE")"
echo "上传至少需要: $(human_bytes "$UPLOAD_NEED")"
echo "根分区至少需要: $(human_bytes "$ROOT_NEED")"
echo "/ota 至少需要: $(human_bytes "$OTA_NEED")"
if [ "$REMOTE_DEV" = "$OTA_DEV" ]; then
  COMBINED_NEED=$((UPLOAD_NEED + OTA_NEED))
  echo "远程目录和 /ota 同分区至少需要: $(human_bytes "$COMBINED_NEED")"
  test "$REMOTE_FREE" -ge "$COMBINED_NEED" || { echo "NX OTA 空间不足"; exit 1; }
else
  test "$REMOTE_FREE" -ge "$UPLOAD_NEED" || { echo "远程目录空间不足"; exit 1; }
  test "$OTA_FREE" -ge "$OTA_NEED" || { echo "/ota 空间不足"; exit 1; }
fi
test "$ROOT_FREE" -ge "$ROOT_NEED" || { echo "根分区空间不足"; exit 1; }
echo "远端预检: 通过"
""".replace("__REMOTE_DIR__", quote(remote_dir))
    replacements = {
        "__PACKAGE_NAME__": quote(package_name),
        "__PACKAGE_IS_ZIP__": "1" if package_is_zip else "0",
        "__PACKAGE_SIZE__": str(package_size),
        "__PAYLOAD_SIZE__": str(payload_size),
        "__SYSTEM_ARCHIVE_SIZE__": str(system_archive_size),
        "__TOOLS_SIZE__": str(tools_size),
        "__ZIP_EXTRACT_SIZE__": str(zip_extract_size),
    }
    for key, value in replacements.items():
        script = script.replace(key, value)
    return script


def rk_precheck_script(remote_dir: str, package_name: str, package_size: int, img_path: str, img_size: int) -> str:
    script = r"""
set -euo pipefail
REMOTE_DIR=__REMOTE_DIR__
PACKAGE_NAME=__PACKAGE_NAME__
PACKAGE_SIZE=__PACKAGE_SIZE__
IMG_SIZE=__IMG_SIZE__
SUDO_PASSWORD="${SUDO_PASSWORD:?}"
case "$REMOTE_DIR" in
  ~*) REMOTE_DIR="$HOME${REMOTE_DIR#\~}" ;;
esac
mkdir -p "$REMOTE_DIR"
test_file="$REMOTE_DIR/.ota_precheck_$$"
: > "$test_file"
rm -f "$test_file"
command -v updateEngine >/dev/null 2>&1 || { echo "缺少 updateEngine"; exit 1; }
sudo_run() { printf '%s\n' "$SUDO_PASSWORD" | sudo -S -p '' "$@"; }
space_bytes() { df -PB1 "$1" | awk 'NR==2 {print $4}'; }
fs_dev() { df -P "$1" | awk 'NR==2 {print $1}'; }
human_bytes() {
  awk -v bytes="${1:-0}" 'BEGIN { split("B KiB MiB GiB TiB", u, " "); v=bytes+0; i=1; while (v>=1024 && i<5) {v/=1024; i++}; if (i==1) printf "%.0f %s", v, u[i]; else printf "%.2f %s", v, u[i] }'
}
command -v sudo >/dev/null 2>&1 || { echo "缺少 sudo"; exit 1; }
case "$PACKAGE_NAME" in
  *.zip)
    command -v python3 >/dev/null 2>&1 || command -v unzip >/dev/null 2>&1 || { echo "缺少 zip 解压工具: python3/unzip"; exit 1; }
    ;;
esac
sudo_run mkdir -p /userdata/update
sudo_run bash -lc ': > /userdata/update/.ota_precheck_$$ && rm -f /userdata/update/.ota_precheck_$$'
REMOTE_FREE="$(space_bytes "$REMOTE_DIR")"
UPDATE_FREE="$(sudo_run df -PB1 /userdata/update | awk 'NR==2 {print $4}')"
REMOTE_DEV="$(fs_dev "$REMOTE_DIR")"
UPDATE_DEV="$(sudo_run df -P /userdata/update | awk 'NR==2 {print $1}')"
REMOTE_NEED=$((PACKAGE_SIZE + IMG_SIZE))
UPDATE_NEED=$IMG_SIZE
echo "远程目录: $REMOTE_DIR"
echo "远程目录可用: $(human_bytes "$REMOTE_FREE")"
echo "/userdata/update 可用: $(human_bytes "$UPDATE_FREE")"
echo "RKFW 镜像: __IMG_PATH__ ($(human_bytes "$IMG_SIZE"))"
if [ "$REMOTE_DEV" = "$UPDATE_DEV" ]; then
  REMOTE_NEED=$((PACKAGE_SIZE + IMG_SIZE + IMG_SIZE))
  echo "同分区至少需要: $(human_bytes "$REMOTE_NEED")"
  test "$REMOTE_FREE" -ge "$REMOTE_NEED" || { echo "3588 OTA 空间不足"; exit 1; }
else
  echo "远程目录至少需要: $(human_bytes "$REMOTE_NEED")"
  echo "/userdata/update 至少需要: $(human_bytes "$UPDATE_NEED")"
  test "$REMOTE_FREE" -ge "$REMOTE_NEED" || { echo "远程目录空间不足"; exit 1; }
  test "$UPDATE_FREE" -ge "$UPDATE_NEED" || { echo "/userdata/update 空间不足"; exit 1; }
fi
echo "远端预检: 通过"
""".replace("__REMOTE_DIR__", quote(remote_dir))
    replacements = {
        "__PACKAGE_NAME__": quote(package_name),
        "__PACKAGE_SIZE__": str(package_size),
        "__IMG_SIZE__": str(img_size),
        "__IMG_PATH__": img_path,
    }
    for key, value in replacements.items():
        script = script.replace(key, value)
    return script
