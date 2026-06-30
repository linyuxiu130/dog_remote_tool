from __future__ import annotations


def performance_probe_script() -> str:
    return r"""
printf 'PERF_BEGIN\n'
printf 'TIME=%s\n' "$(date '+%H:%M:%S' 2>/dev/null || true)"
printf 'HOSTNAME=%s\n' "$(hostname 2>/dev/null || true)"
awk '{print "LOAD_1="$1; print "LOAD_5="$2; print "LOAD_15="$3}' /proc/loadavg 2>/dev/null || true
CPU_CORES=$(nproc 2>/dev/null || grep -c '^processor' /proc/cpuinfo 2>/dev/null || echo 1)
printf 'CPU_CORES=%s\n' "$CPU_CORES"
free -m 2>/dev/null | awk '
  /^Mem:/ {
    print "MEM_TOTAL_MB="$2;
    print "MEM_USED_MB="$3;
    print "MEM_AVAILABLE_MB="$7;
  }
  /^Swap:/ {
    print "SWAP_TOTAL_MB="$2;
    print "SWAP_USED_MB="$3;
  }
'
vmstat 1 2 2>/dev/null | tail -1 | awk '{
  print "IO_BI="$9;
  print "IO_BO="$10;
  print "CPU_US_VMSTAT="$13;
  print "CPU_SY_VMSTAT="$14;
  print "CPU_IDLE_VMSTAT="$15;
  print "CPU_WA_VMSTAT="$16;
}'
top -b -n 1 2>/dev/null | awk '
  /%Cpu/ {
    gsub(",", "");
    for (i = 1; i <= NF; i++) {
      if ($i == "us") us = $(i - 1);
      if ($i == "sy") sy = $(i - 1);
      if ($i == "ni") ni = $(i - 1);
      if ($i == "id") idle = $(i - 1);
      if ($i == "wa") wa = $(i - 1);
      if ($i == "hi") hi = $(i - 1);
      if ($i == "si") si = $(i - 1);
      if ($i == "st") st = $(i - 1);
    }
  }
  END {
    if (idle == "") exit 0;
    used = 100 - idle;
    printf "CPU_US=%.1f\nCPU_SY=%.1f\nCPU_NI=%.1f\nCPU_IDLE=%.1f\nCPU_WA=%.1f\nCPU_HI=%.1f\nCPU_SI=%.1f\nCPU_ST=%.1f\nCPU_USED=%.1f\n", us + 0, sy + 0, ni + 0, idle + 0, wa + 0, hi + 0, si + 0, st + 0, used;
  }
'
ps -eo comm,%mem --sort=-%mem 2>/dev/null | awk 'NR==2{print "TOP_MEM_PROC="$1; print "TOP_MEM_PERCENT="$2}'
ps -eo pid=,comm=,%cpu=,%mem= --sort=-%cpu 2>/dev/null | head -6 | awk -v cores="$CPU_CORES" '{
  print "TOP_CPU_"NR"_PID="$1;
  print "TOP_CPU_"NR"_PROC="$2;
  print "TOP_CPU_"NR"_PERCENT="$3;
  printf "TOP_CPU_%d_TOTAL_PERCENT=%.1f\n", NR, ($3 + 0) / cores;
  print "TOP_CPU_"NR"_MEM="$4;
}'
ps -eo comm=,%cpu= 2>/dev/null | awk -v cores="$CPU_CORES" '
  function module_name(name, lower) {
    lower = tolower(name);
    if (lower ~ /(camera|ov2312|uvc|v4l|image|video)/) return "相机";
    if (lower ~ /(rslidar|lidar|laser|livox)/) return "雷达";
    if (lower ~ /(slam|mapping|nav|localization|planner|costmap)/) return "导航建图";
    if (lower ~ /(driver|imu|uwb|rtk|uss|sensor)/) return "传感器驱动";
    if (lower ~ /(ros2|robot_|joint|hal|monitor|manager|control)/) return "机器人框架";
    if (lower ~ /(python|python3)/) return "Python";
    if (lower ~ /(ssh|sshd|scp|sftp)/) return "SSH";
    if (lower ~ /(systemd|dbus|network|irq|kworker|rcu|migration|polkit)/) return "系统";
    return "其他";
  }
  {
    name = module_name($1);
    cpu[name] += $2 + 0;
  }
  END {
    for (name in cpu) {
      printf "%.1f\t%s\t%.1f\n", cpu[name], name, cpu[name] / cores;
    }
  }
' | sort -rn | head -6 | awk -F '\t' '{
  print "CPU_MODULE_"NR"_TOP_PERCENT="$1;
  print "CPU_MODULE_"NR"_NAME="$2;
  print "CPU_MODULE_"NR"_TOTAL_PERCENT="$3;
}'
df -Pm /dev/shm 2>/dev/null | awk 'NR==2 {
  gsub("%", "", $5);
  print "SHM_TOTAL_MB="$2;
  print "SHM_USED_MB="$3;
  print "SHM_AVAIL_MB="$4;
  print "SHM_USE_PERCENT="$5;
}'
find /dev/shm -maxdepth 1 -type f -name '*.zenoh' -printf '%s\n' 2>/dev/null | awk '
  {count++; total += $1; if ($1 >= 268435456) big++}
  END {
    print "SHM_ZENOH_COUNT="count + 0;
    printf "SHM_ZENOH_TOTAL_MB=%.0f\n", total / 1024 / 1024;
    print "SHM_ZENOH_256M_COUNT="big + 0;
  }
'
ps -eo args= 2>/dev/null | awk '
  /dog_remote_start_navigation_helper|dog_remote_tool_pose_stream|dog_remote_tool_plan_stream|dog_remote_tool_obstacle_stream|dog_remote_tool_nav_camera_overlay_stream|ros2cli.daemon.daemonize|ros2-daemon --ros-domain-id/ && !/awk/ {count++}
  END {print "SHM_DOG_REMOTE_HELPER_COUNT="count + 0}
'
printf 'PERF_END\n'
"""
