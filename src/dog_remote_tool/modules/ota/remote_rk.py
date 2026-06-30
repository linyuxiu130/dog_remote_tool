from __future__ import annotations

from dog_remote_tool.modules.ota.remote_shell import python_zip_extract_shell, remote_common_shell


def rk_remote_script() -> str:
    common_shell = remote_common_shell("远程3588")
    zip_extract_shell = python_zip_extract_shell()
    script = r"""
set -euo pipefail
PACKAGE_NAME="${PACKAGE_NAME:?}"
REMOTE_DIR="${REMOTE_DIR:?}"
SUDO_PASSWORD="${SUDO_PASSWORD:?}"
RUN_UPGRADE="${RUN_UPGRADE:-0}"
TARGET_KEY="${TARGET_KEY:-}"
AUTO_REBOOT_DELAY=5
ROBOT_LAUNCH_STOPPED=0
SKIP_ROBOT_LAUNCH_RESTART=0
__COMMON_SHELL__
upgrade_known_firmware() {
  if ! sudo_run test -x /usr/local/bin/mcu_upgrade; then
    die "远端缺少 /usr/local/bin/mcu_upgrade，不能执行完整固件刷写"
  fi
  shopt -s nullglob
  local files file
  files=("$WORK_DIR"/spline_release_*.bin)
  for file in "${files[@]}"; do
    log "刷写 spline 固件到 spi2CAN A: $file"
    sudo_run fuser -k -9 /dev/spidev0.0 /dev/spidev0.1 2>/dev/null || true
    sudo_run /usr/local/bin/mcu_upgrade -d /dev/spidev0.0 -f "$file"
    log "刷写 spline 固件到 spi2CAN B: $file"
    sudo_run /usr/local/bin/mcu_upgrade -d /dev/spidev0.1 -f "$file"
  done
  files=("$WORK_DIR"/power_board_release_*.bin)
  for file in "${files[@]}"; do
    log "刷写 power_board 固件: $file"
    sudo_run fuser -k -9 /dev/ttyS3 2>/dev/null || true
    sudo_run /usr/local/bin/mcu_upgrade -d /dev/ttyS3 -f "$file"
  done
  shopt -u nullglob
}
is_xg3588_target() {
  case "$TARGET_KEY" in
    xg_l1_point_3588|xg_l1_wheel_3588|xg3588) return 0 ;;
    *) return 1 ;;
  esac
}
check_xg3588_soc() {
  local output soc limit
  if [[ "$PACKAGE_STEM" == 6* ]]; then
    limit=25
  else
    limit=10
  fi
  log "读取小狗 3588 SOC，阈值 ${limit}%"
  if ! output="$(sudo_run /usr/local/bin/mcu_upgrade -d /dev/ttyS3 -p 2>&1)"; then
    die "读取 SOC 失败: $output"
  fi
  soc="$(printf '%s\n' "$output" | awk '{for (i=1;i<=NF;i++) if ($i ~ /^[0-9]+$/) v=$i} END {print v}')"
  if [ -z "$soc" ]; then
    die "SOC 输出无法解析: $output"
  fi
  log "当前 SOC: ${soc}%"
  if [ "$soc" -lt "$limit" ]; then
    die "SOC ${soc}% 低于阈值 ${limit}%，停止 OTA"
  fi
}
xg3588_motor_mask() {
  case "$1:$2" in
    0:1) printf '0x1 0x1\n' ;;
    0:2) printf '0x1 0x2\n' ;;
    0:3) printf '0x1 0x4\n' ;;
    0:4) printf '0x1 0x8\n' ;;
    1:1) printf '0x2 0x1\n' ;;
    1:2) printf '0x2 0x2\n' ;;
    1:3) printf '0x2 0x4\n' ;;
    1:4) printf '0x2 0x8\n' ;;
    *) return 1 ;;
  esac
}
upgrade_xg3588_motorcontrol_device() {
  local device="$1" output line current_leg joint sw hw file expected_sw leg_mask joint_mask attempt changed result
  declare -A motor_fw=()
  declare -A motor_sw=()
  shopt -s nullglob
  for file in "$WORK_DIR"/motorcontrol_*.bin; do
    local base="${file##*/}" rest
    rest="${base#*-}"
    hw="${rest%%-*}"
    rest="${rest#*-}"
    sw="${rest%%-*}"
    if [ -n "$hw" ] && [ -n "$sw" ] && [ "$hw" != "$base" ]; then
      motor_fw["$hw"]="$file"
      motor_sw["$hw"]="$sw"
    fi
  done
  shopt -u nullglob
  if [ "${#motor_fw[@]}" -eq 0 ]; then
    log "未找到 motorcontrol 固件，跳过 $device"
    return 0
  fi
  for attempt in 1 2 3 4 5; do
    changed=0
    log "读取 motorcontrol 版本: $device，第 ${attempt}/5 轮"
    if ! output="$(sudo_run /usr/local/bin/mcu_upgrade -d "$device" -l 0 -j 2 -s 2>&1)"; then
      die "读取 motorcontrol 版本失败: $device: $output"
    fi
    current_leg=""
    while IFS= read -r line; do
      set -- $line
      if [ "${1:-}" = "leg" ] && [ "${2:-}" = "idx" ] && [ "$#" -eq 3 ]; then
        current_leg="$3"
        continue
      fi
      if [ "${1:-}" != "joint" ] || [ "$#" -ne 9 ] || [ -z "$current_leg" ]; then
        continue
      fi
      joint="$2"
      sw="$5"
      hw="$8"
      if [ "$hw" = "0" ] || [ -z "${motor_fw[$hw]:-}" ]; then
        continue
      fi
      expected_sw="${motor_sw[$hw]}"
      if [ "$sw" = "$expected_sw" ]; then
        continue
      fi
      read -r leg_mask joint_mask < <(xg3588_motor_mask "$current_leg" "$joint") || die "未知 motorcontrol leg/joint: $current_leg/$joint"
      file="${motor_fw[$hw]}"
      log "刷写 motorcontrol $device leg=$current_leg joint=$joint hw=$hw sw=$sw -> $expected_sw"
      if ! result="$(sudo_run /usr/local/bin/mcu_upgrade -d "$device" -l "$leg_mask" -j "$joint_mask" -f "$file" 2>&1)"; then
        die "刷写 motorcontrol 失败: $result"
      fi
      if ! printf '%s\n' "$result" | grep -q "joint upgrade"; then
        die "motorcontrol 返回缺少 joint upgrade: $result"
      fi
      if printf '%s\n' "$result" | grep -qi "failed"; then
        die "motorcontrol 返回 failed: $result"
      fi
      if ! printf '%s\n' "$result" | grep -q "data end"; then
        die "motorcontrol 返回缺少 data end: $result"
      fi
      changed=1
    done <<< "$output"
    if [ "$changed" = "0" ]; then
      log "motorcontrol $device 已是目标版本"
      return 0
    fi
  done
  die "motorcontrol $device 刷写后 5 轮仍未确认目标版本"
}
upgrade_xg3588_pre_system_firmware() {
  if ! sudo_run test -x /usr/local/bin/mcu_upgrade; then
    die "远端缺少 /usr/local/bin/mcu_upgrade，不能执行小狗 3588 固件刷写"
  fi
  log "停止 robot-launch.service，释放小狗 3588 HAL/CAN/串口设备"
  sudo_run systemctl stop robot-launch.service
  ROBOT_LAUNCH_STOPPED=1
  sudo_run fuser -k -9 /dev/spidev0.0 /dev/spidev0.1 /dev/ttyS1 /dev/ttyS3 2>/dev/null || true
  check_xg3588_soc

  shopt -s nullglob
  local files file
  files=("$WORK_DIR"/spline_release_*.bin)
  for file in "${files[@]}"; do
    run_retry "刷写 spline spi2CAN A" /usr/local/bin/mcu_upgrade -d /dev/spidev0.0 -f "$file"
    run_retry "刷写 spline spi2CAN B" /usr/local/bin/mcu_upgrade -d /dev/spidev0.1 -f "$file"
  done
  upgrade_xg3588_motorcontrol_device /dev/spidev0.0
  upgrade_xg3588_motorcontrol_device /dev/spidev0.1
  files=("$WORK_DIR"/imu_board_release_*.bin)
  for file in "${files[@]}"; do
    run_retry "刷写 imu_board" /usr/local/bin/mcu_upgrade -d /dev/ttyS1 -i -f "$file"
  done
  shopt -u nullglob
}
upgrade_xg3588_power_board() {
  shopt -s nullglob
  local files file
  files=("$WORK_DIR"/power_board_release_*.bin)
  for file in "${files[@]}"; do
    run_retry "刷写 power_board" /usr/local/bin/mcu_upgrade -d /dev/ttyS3 -f "$file"
  done
  shopt -u nullglob
}
reboot_xg3588_battery_board() {
  log "通过 power_board 触发小狗 3588 电池板断电重启"
  sudo_run /usr/local/bin/mcu_upgrade -d /dev/ttyS3 -r 5
}
upgrade_zg3588_full_firmware() {
  local mcu_tool actuator_tool uart_tool
  local imu joint wheel uart hot_swap power battery
  mcu_tool="$(find_one 'tool/mcu_upgrade_tool*' 'mcu_upgrade_tool')"
  actuator_tool="$(find_one 'tool/actuator_upgrade_tool*' 'actuator_upgrade_tool')"
  uart_tool="$(find_one 'tool/uart2can_upgrade_tool*' 'uart2can_upgrade_tool')"
  imu="$(find_one 'firmware/imu*.bin' 'imu 固件')"
  joint="$(find_one 'firmware/motorcontrol_SMGRB_P85*.bin' 'actuator_joint 固件')"
  wheel="$(find_one 'firmware/motorcontrol_SMGRB_W190*.bin' 'actuator_wheel 固件')"
  uart="$(find_one 'firmware/uart2canfd*.bin' 'uart2can 固件')"
  hot_swap="$(find_one 'firmware/hot_swap_board*.bin' 'hot_swap 固件')"
  power="$(find_one 'firmware/power_zg*.bin' 'power_control 固件')"
  battery="$(find_one 'firmware/I0930B_APP*.bin' 'battery 固件')"

  chmod +x "$mcu_tool" "$actuator_tool" "$uart_tool"
  log "停止 robot-launch.service，释放 HAL/CAN/串口设备"
  sudo_run systemctl stop robot-launch.service
  ROBOT_LAUNCH_STOPPED=1

  run_retry "刷写 imu" "$mcu_tool" -i -d /dev/ttyS1 -f "$imu"
  run_retry "刷写 actuator_joint all:1,2,3" "$actuator_tool" --update "$joint" all:1,2,3
  run_retry "刷写 actuator_wheel all:4" "$actuator_tool" --update "$wheel" all:4
  run_retry "刷写 uart2can can2" "$uart_tool" --uart2canfd -d /dev/uart2canfd-can2 -f "$uart"
  run_retry "刷写 uart2can can0" "$uart_tool" --uart2canfd -d /dev/uart2canfd-can0 -f "$uart"
  run_retry "刷写 hot_swap" "$mcu_tool" -d /dev/ttyCH9344USB6 -f "$hot_swap"
  run_retry "刷写 power_control" "$mcu_tool" -d /dev/ttyCH9344USB6 -f "$power"
  for battery_id in 1 2; do
    sudo_run fuser -k /dev/ttyCH9344USB6 2>/dev/null || true
    run_retry "刷写 battery[$battery_id]" "$mcu_tool" -d /dev/ttyCH9344USB6 -f "$battery" -b "$battery_id"
  done
}
PACKAGE_PATH="$REMOTE_DIR/$PACKAGE_NAME"
test -f "$PACKAGE_PATH" || die "升级包不存在: $PACKAGE_PATH"
command -v updateEngine >/dev/null 2>&1 || die "远端缺少 updateEngine"

PACKAGE_STEM="$PACKAGE_NAME"
case "$PACKAGE_NAME" in
  *.tar.gz) PACKAGE_STEM="${PACKAGE_NAME%.tar.gz}" ;;
  *.zip) PACKAGE_STEM="${PACKAGE_NAME%.zip}" ;;
esac
WORK_DIR="$REMOTE_DIR/${PACKAGE_STEM}_$(date +%Y%m%d_%H%M%S)"
rm -rf "$WORK_DIR"
mkdir -p "$WORK_DIR"
log "解压升级包"
case "$PACKAGE_NAME" in
  *.tar.gz)
    tar --sparse -xzf "$PACKAGE_PATH" -C "$WORK_DIR" --strip-components=1
    ;;
  *.zip)
__ZIP_EXTRACT_SHELL__
    chmod +x "$WORK_DIR"/tool/* 2>/dev/null || true
    ;;
  *)
    die "不支持的 3588 包格式: $PACKAGE_NAME"
    ;;
esac
IMG="$(find "$WORK_DIR" -type f -name '*.img' | head -n 1)"
test -n "$IMG" || die "未找到 .img"
MAGIC="$(dd if="$IMG" bs=4 count=1 2>/dev/null)"
test "$MAGIC" = RKFW || die ".img 不是 RKFW 镜像"
log "RKFW 镜像: $IMG"
log "prepare-only 阶段完成"

if [ "$RUN_UPGRADE" != "1" ]; then
  log "未执行 updateEngine"
  exit 0
fi

echo "[DOG_REMOTE_STAGE] upgrade_locked"
if [ "$TARGET_KEY" = "zg3588" ] && [ -d "$WORK_DIR/tool" ]; then
  upgrade_zg3588_full_firmware
elif is_xg3588_target; then
  upgrade_xg3588_pre_system_firmware
else
  upgrade_known_firmware
fi
RECOVERY_DIR="/userdata/update/$PACKAGE_STEM"
RECOVERY_IMG="$RECOVERY_DIR/$(basename "$IMG")"
log "复制镜像到 $RECOVERY_IMG"
sudo_run mkdir -p "$RECOVERY_DIR"
sudo_run cp -f "$IMG" "$RECOVERY_IMG"
sync
sudo_run touch "$RECOVERY_IMG.done"
log "执行 updateEngine"
if [ "$TARGET_KEY" = "zg3588" ]; then
  sudo_run updateEngine --misc=update --image_url="$RECOVERY_IMG" --partition=0xFFFC00
else
  sudo_run updateEngine --misc=update --image_url="$RECOVERY_IMG"
fi
sudo_run rm -rf /userdata/rootfs_overlay* || true
sync
SKIP_ROBOT_LAUNCH_RESTART=1
if is_xg3588_target; then
  upgrade_xg3588_power_board
  reboot_xg3588_battery_board
else
  log "updateEngine finished，${AUTO_REBOOT_DELAY} 秒后自动重启"
  sudo_run bash -lc "nohup sh -c 'sleep ${AUTO_REBOOT_DELAY}; sync; reboot' >/dev/null 2>&1 &"
fi
"""
    return script.replace("__COMMON_SHELL__", common_shell).replace("__ZIP_EXTRACT_SHELL__", zip_extract_shell)
