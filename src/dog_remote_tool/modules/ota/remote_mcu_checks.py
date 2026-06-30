from __future__ import annotations


def mcu_maintenance_block(enabled: bool) -> str:
    if not enabled:
        return ""
    return r"""
ROBOT_LAUNCH_STOPPED=0
sudo_run() {
  if [ -n "$SUDO_PASSWORD" ] && command -v sudo >/dev/null 2>&1; then
    printf '%s\n' "$SUDO_PASSWORD" | sudo -S -p '' "$@"
  else
    "$@"
  fi
}
cleanup() {
  if [ "$ROBOT_LAUNCH_STOPPED" = "1" ]; then
    echo "MCU读取模式: 恢复 robot-launch.service"
    sudo_run systemctl start robot-launch.service >/dev/null 2>&1 || true
  fi
}
trap cleanup EXIT
if sudo_run systemctl is-active --quiet robot-launch.service; then
  echo "MCU读取模式: 临时停止 robot-launch.service，读取后自动恢复"
  if sudo_run systemctl stop robot-launch.service >/dev/null 2>&1; then
    ROBOT_LAUNCH_STOPPED=1
    sleep 3
  else
    echo "MCU读取模式: 停止 robot-launch.service 失败，按普通只读模式继续"
  fi
else
  echo "MCU读取模式: robot-launch.service 当前未运行，不自动启动"
fi
"""


def mcu_probe_block(enabled: bool) -> str:
    if not enabled:
        return ""
    return r"""
case "$TARGET_KEY" in
  xg_l1_point_3588|xg_l1_wheel_3588|xg3588)
    echo "目标MCU: 小狗3588: spline(spidev0.0/0.1), motorcontrol(spidev0.0/0.1), imu(ttyS1), power_board/SOC(ttyS3)"
    if [ -x /usr/local/bin/mcu_upgrade ]; then
      probe_mcu "motorcontrol(spidev0.0)" /usr/local/bin/mcu_upgrade -d /dev/spidev0.0 -l 0 -j 2 -s
      probe_mcu "motorcontrol(spidev0.1)" /usr/local/bin/mcu_upgrade -d /dev/spidev0.1 -l 0 -j 2 -s
      probe_mcu "imu(ttyS1)" /usr/local/bin/mcu_upgrade -d /dev/ttyS1 -i -s
      probe_mcu "power_board(ttyS3)" /usr/local/bin/mcu_upgrade -d /dev/ttyS3 -s
    else
      echo "当前MCU: 小狗3588: 读取失败: 缺少 /usr/local/bin/mcu_upgrade"
    fi
    ;;
  zg3588)
    echo "目标MCU: 中狗3588: imu(ttyS1), actuator_joint(all:1,2,3), actuator_wheel(all:4), uart2can(can0/can2), hot_swap/power/battery[1,2](ttyCH9344USB6)"
    if [ -x /opt/runtime/bin/mcu_upgrade ]; then
      probe_mcu "imu(ttyS1)" /opt/runtime/bin/mcu_upgrade -d /dev/ttyS1 -s -i
      probe_mcu "hot_swap(ttyCH9344USB6)" /opt/runtime/bin/mcu_upgrade -d /dev/ttyCH9344USB6 -s -o
      probe_mcu "power_control(ttyCH9344USB6)" /opt/runtime/bin/mcu_upgrade -d /dev/ttyCH9344USB6 -s
      probe_mcu "battery[1]" /opt/runtime/bin/mcu_upgrade -d /dev/ttyCH9344USB6 -s -b 1
      probe_mcu "battery[2]" /opt/runtime/bin/mcu_upgrade -d /dev/ttyCH9344USB6 -s -b 2
    else
      echo "当前MCU: 中狗3588 mcu_upgrade: 读取失败: 缺少 /opt/runtime/bin/mcu_upgrade"
    fi
    if [ -x /opt/runtime/bin/canfd_upgrade ]; then
      probe_mcu "uart2can(can0)" /opt/runtime/bin/canfd_upgrade -s -d /dev/uart2canfd-can0
      probe_mcu "uart2can(can2)" /opt/runtime/bin/canfd_upgrade -s -d /dev/uart2canfd-can2
    else
      echo "当前MCU: uart2can: 读取失败: 缺少 /opt/runtime/bin/canfd_upgrade"
    fi
    if [ -x /opt/runtime/bin/actuator_tool ]; then
      probe_mcu "actuator_joint(all:1,2,3)" /opt/runtime/bin/actuator_tool --firmware-version all:1,2,3
      probe_mcu "actuator_wheel(all:4)" /opt/runtime/bin/actuator_tool --firmware-version all:4
    else
      echo "当前MCU: actuator: 读取失败: 缺少 /opt/runtime/bin/actuator_tool"
    fi
    ;;
esac
"""


def mcu_helper_block(enabled: bool) -> str:
    if not enabled:
        return ""
    return r"""
run_readonly_sudo() {
  if [ -n "$SUDO_PASSWORD" ] && command -v sudo >/dev/null 2>&1; then
    printf '%s\n' "$SUDO_PASSWORD" | sudo -S -p '' timeout 8 "$@"
  else
    timeout 8 "$@"
  fi
}
compact_probe_output() {
  sed -n '1,8p' | tr '\n' ';' | sed 's/[[:space:]][[:space:]]*/ /g; s/;[; ]*/; /g; s/[; ]*$//'
}
probe_mcu() {
  label="$1"
  shift
  if output="$(run_readonly_sudo "$@" 2>&1)"; then
    summary="$(printf '%s\n' "$output" | compact_probe_output)"
    [ -n "$summary" ] || summary="无输出"
    if printf '%s\n' "$output" | grep -Eqi 'failed|invalid|time[ -]?out|timeout|error|unrecognized option|检测到 .*正在运行|请先停止'; then
      printf '当前MCU: %s: 读取失败: %s\n' "$label" "$summary"
      return 0
    fi
    printf '当前MCU: %s: %s\n' "$label" "$summary"
  else
    summary="$(printf '%s\n' "$output" | compact_probe_output)"
    [ -n "$summary" ] || summary="命令失败"
    printf '当前MCU: %s: 读取失败: %s\n' "$label" "$summary"
  fi
}
"""
