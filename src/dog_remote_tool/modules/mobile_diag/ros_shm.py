from __future__ import annotations

from dog_remote_tool.core.profiles import ProductProfile
from dog_remote_tool.core.shell import CommandSpec, quote, ssh_command, sudo_run_shell
from dog_remote_tool.modules import navigation


def _ros_shm_common_functions() -> str:
    return sudo_run_shell(fallback_without_sudo=True, probe_sudo=True) + r"""
shm_percent() {
  df -P /dev/shm 2>/dev/null | awk 'NR==2 {gsub("%", "", $5); print $5 + 0}'
}
print_shm_summary() {
  echo '===== /dev/shm 使用情况 ====='
  df -hPT /dev/shm 2>/dev/null || true
  echo ''
  echo '===== 通信共享内存文件 ====='
  find /dev/shm -maxdepth 1 -type f -name '*.zenoh' -printf '%s %p\n' 2>/dev/null | awk '
    {count++; total += $1; if ($1 >= 268435456) big++}
    END {
      printf "ZENOH_COUNT=%d\n", count + 0;
      printf "ZENOH_TOTAL_MB=%.0f\n", total / 1024 / 1024;
      printf "ZENOH_256M_COUNT=%d\n", big + 0;
    }
  '
  find /dev/shm -maxdepth 1 -type f -name '*.zenoh' -size 256M -printf '%TY-%Tm-%Td %TH:%TM %10s %p\n' 2>/dev/null | sort | tail -40 || true
  echo ''
  percent=$(shm_percent)
  if [ "${percent:-0}" -ge 90 ]; then
    echo "[WARN] /dev/shm 使用率 ${percent}% >= 90%，ROS 2 通信组件可能无法创建新节点、服务或发送指令。"
  else
    echo "[INFO] /dev/shm 使用率 ${percent:-未知}%，未达到高危阈值。"
  fi
}
print_tool_processes() {
  echo ''
  echo '===== Dog Remote Tool 相关远端进程 ====='
  ps -eo pid=,ppid=,etime=,stat=,args= 2>/dev/null | awk '
    /dog_remote_start_navigation_helper|dog_remote_tool_pose_stream|dog_remote_tool_plan_stream|dog_remote_tool_obstacle_stream|dog_remote_tool_nav_camera_overlay_stream|ros2cli.daemon.daemonize|ros2-daemon --ros-domain-id/ && !/awk/ {print}
  ' || true
}
"""


def ros_shm_check_command(profile: ProductProfile) -> CommandSpec:
    script = (
        "echo '========================================'; "
        "echo '  ROS 共享内存 / Zenoh 检查'; "
        "echo '========================================'; "
        "echo '[INFO] time='$(date '+%F %T'); "
        "echo '[INFO] host='$(hostname 2>/dev/null || true); "
        + _ros_shm_common_functions()
        + r"""
print_shm_summary
print_tool_processes
echo ''
echo '===== 打开 /dev/shm 的进程（需要 sudo 时自动尝试） ====='
if [ "$sudo_ok" = 1 ]; then
  sudo_run lsof +D /dev/shm 2>/dev/null | awk 'NR==1 || /zenoh|dog_remote|ros2-daemon|robot_|slam|localization|navig|perception|driver|meb|image|lidar|imu|uwb|rtk|uss/' | tail -120 || true
else
  lsof +D /dev/shm 2>/dev/null | awk 'NR==1 || /zenoh|dog_remote|ros2-daemon|robot_|slam|localization|navig|perception|driver|meb|image|lidar|imu|uwb|rtk|uss/' | tail -120 || true
fi
echo ''
echo '===== 检查完成 ====='
"""
    )
    return CommandSpec(
        "检查 ROS 共享内存",
        ssh_command(profile, f"bash -c {quote(script)}"),
        display_command="执行：检查 ROS 共享内存",
        concurrency="parallel",
    )


def ros_shm_cleanup_command(profile: ProductProfile) -> CommandSpec:
    script = (
        "echo '========================================'; "
        "echo '  清理 Dog Remote Tool ROS 临时资源'; "
        "echo '========================================'; "
        "echo '[INFO] time='$(date '+%F %T'); "
        "echo '[INFO] host='$(hostname 2>/dev/null || true); "
        + _ros_shm_common_functions()
        + "echo '[INFO] 清理前'; print_shm_summary; print_tool_processes; "
        + navigation.cleanup_navigation_tool_helpers_inner(include_ros_daemon=True)
        + r"""
echo ''
echo '===== 清理未被进程占用的通信文件 ====='
open_files=$(mktemp /tmp/dog_remote_open_shm.XXXXXX)
if [ "$sudo_ok" = 1 ]; then
  sudo_run lsof +D /dev/shm 2>/dev/null | awk 'NR>1 {print $9}' | sort -u > "$open_files" || true
else
  lsof +D /dev/shm 2>/dev/null | awk 'NR>1 {print $9}' | sort -u > "$open_files" || true
fi
find /dev/shm -maxdepth 1 -type f -name '*.zenoh' -print 2>/dev/null | while IFS= read -r file; do
  if grep -Fx -- "$file" "$open_files" >/dev/null 2>&1; then
    echo "[KEEP] still open: $file"
  else
    if sudo_run rm -f -- "$file" 2>/dev/null; then
      echo "[CLEAN] 已删除未占用文件: $file"
    else
      echo "[WARN] remove failed: $file"
    fi
  fi
done
rm -f "$open_files" 2>/dev/null || true
echo ''
echo '[INFO] 清理后'
print_shm_summary
percent=$(shm_percent)
if [ "${percent:-0}" -ge 90 ]; then
  echo '[WARN] 清理后仍然高危，主要占用可能来自业务进程。建议重启相关 robot-launch 服务或检查 ROS 2 共享内存配置。'
fi
echo '===== 清理完成 ====='
"""
    )
    return CommandSpec(
        "清理 ROS 共享内存临时资源",
        ssh_command(profile, f"bash -c {quote(script)}"),
        dangerous=True,
        display_command="执行：清理 ROS 共享内存临时资源",
    )
