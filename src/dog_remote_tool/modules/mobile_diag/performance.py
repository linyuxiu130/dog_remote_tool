from __future__ import annotations

from dog_remote_tool.core.profiles import ProductProfile, get_product
from dog_remote_tool.core.shell import CommandSpec, quote, ssh_command
from dog_remote_tool.modules.mobile_diag.performance_script import performance_probe_script
from dog_remote_tool.modules.mobile_diag.temperature_script import temperature_probe_script


def performance_snapshot_command(profile: ProductProfile) -> CommandSpec:
    inner = r"""
echo '========================================'
echo '  性能监控快照'
echo '========================================'
echo '[INFO] time='$(date '+%F %T')
echo '[INFO] host='$(hostname 2>/dev/null || true)
echo ''
echo '===== Load average / uptime ====='
uptime || true
cat /proc/loadavg 2>/dev/null | awk '{print "loadavg_1m="$1" loadavg_5m="$2" loadavg_15m="$3" runnable="$4" last_pid="$5}' || true
echo ''
echo '===== Memory / Swap ====='
free -h || true
echo ''
grep -E '^(MemTotal|MemAvailable|MemFree|Buffers|Cached|SwapTotal|SwapFree|Dirty|Writeback):' /proc/meminfo 2>/dev/null || true
echo ''
echo '===== Swap devices ====='
swapon --show 2>/dev/null || true
echo ''
echo '===== CPU / top processes ====='
top -b -n 1 -o %MEM 2>/dev/null | sed -n '1,18p' || true
echo ''
echo '===== Top memory processes ====='
ps -eo pid,ppid,comm,%mem,%cpu,rss,vsz --sort=-rss 2>/dev/null | head -15 || true
echo ''
echo '===== Top CPU processes ====='
ps -eo pid,ppid,comm,%cpu,%mem,rss,vsz --sort=-%cpu 2>/dev/null | head -15 || true
echo ''
echo '===== Disk usage ====='
df -hT / /tmp /opt /ota /home 2>/dev/null | awk 'NR==1 || !seen[$1" "$7]++' || df -hT 2>/dev/null || true
echo ''
echo '===== IO snapshot ====='
vmstat 1 3 2>/dev/null || true
if command -v iostat >/dev/null 2>&1; then
  iostat -xz 1 2 2>/dev/null || true
else
  echo '[WARN] iostat 不存在，跳过磁盘 IO 详细统计。'
fi
echo ''
echo '===== 性能快照完成 ====='
"""
    return CommandSpec("性能监控快照", ssh_command(profile, f"bash -c {quote(inner)}"), display_command="执行：性能监控快照", concurrency="parallel")


def performance_sample_command(profile: ProductProfile) -> CommandSpec:
    inner = r"""
echo '========================================'
echo '  性能监控 30 秒采样'
echo '========================================'
echo '[INFO] time='$(date '+%F %T')
echo '[INFO] host='$(hostname 2>/dev/null || true)
echo ''
echo '===== vmstat 1s x 30 ====='
vmstat 1 30 2>/dev/null || true
echo ''
echo '===== final memory / swap ====='
free -h || true
echo ''
echo '===== final top memory processes ====='
ps -eo pid,ppid,comm,%mem,%cpu,rss,vsz --sort=-rss 2>/dev/null | head -15 || true
echo ''
echo '===== final top CPU processes ====='
ps -eo pid,ppid,comm,%cpu,%mem,rss,vsz --sort=-%cpu 2>/dev/null | head -15 || true
echo ''
if command -v iostat >/dev/null 2>&1; then
  echo '===== iostat 1s x 5 ====='
  iostat -xz 1 5 2>/dev/null || true
else
  echo '[WARN] iostat 不存在，跳过磁盘 IO 详细统计。'
fi
echo ''
echo '===== 30 秒采样完成 ====='
"""
    return CommandSpec("性能监控 30 秒采样", ssh_command(profile, f"bash -c {quote(inner)}"), display_command="执行：性能监控 30 秒采样", concurrency="parallel")


def paired_base_profile(profile: ProductProfile) -> ProductProfile | None:
    if profile.key == "xg2_s100":
        return get_product("xg2_3588")
    if profile.key == "zg_surround_s100":
        return get_product("zg3588")
    if profile.key in {"xg1_nx", "zg_lidar_nx"}:
        return get_product("xg3588") if profile.key == "xg1_nx" else get_product("zg3588")
    return None


def performance_probe_command(profile: ProductProfile) -> str:
    current_script = performance_probe_script() + temperature_probe_script(
        "CUR", profile.label, profile.platform == "RK3588", profile.ros_domain_id, profile.rmw
    )
    current_command = ssh_command(profile, f"bash -c {quote(current_script)}")
    paired = paired_base_profile(profile)
    if not paired:
        return current_command
    base_script = temperature_probe_script("BASE", paired.label, True, paired.ros_domain_id, paired.rmw)
    base_command = ssh_command(paired, f"bash -c {quote(base_script)}")
    return (
        "tmp1=$(mktemp); tmp2=$(mktemp); "
        f"({current_command}) >\"$tmp1\" 2>&1 & p1=$!; "
        f"({base_command}) >\"$tmp2\" 2>&1 & p2=$!; "
        "wait \"$p1\"; status=$?; "
        "wait \"$p2\" || true; "
        "cat \"$tmp1\"; cat \"$tmp2\"; "
        "rm -f \"$tmp1\" \"$tmp2\"; "
        "exit \"$status\""
    )
