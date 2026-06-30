from __future__ import annotations


def remote_common_shell(label: str, *, cleanup_robot_launch: bool = True) -> str:
    cleanup_body = (
        """
cleanup() {
  local code=$?
  if [ "$ROBOT_LAUNCH_STOPPED" = "1" ] && [ "$SKIP_ROBOT_LAUNCH_RESTART" != "1" ]; then
    log "恢复 robot-launch.service"
    sudo_run systemctl restart robot-launch.service || true
  fi
  exit "$code"
}
trap cleanup EXIT
"""
        if cleanup_robot_launch
        else ""
    )
    return f"""
log() {{ printf '[%s] [{label}] %s\\n' "$(date '+%F %T')" "$*"; }}
die() {{ printf '[%s] [{label}] 错误: %s\\n' "$(date '+%F %T')" "$*" >&2; exit 1; }}
sudo_run() {{ printf '%s\\n' "$SUDO_PASSWORD" | sudo -S -p '' "$@"; }}
{cleanup_body}find_one() {{
  local pattern="$1" label="$2" found
  found="$(find "$WORK_DIR" -type f -path "$WORK_DIR/$pattern" -print -quit)"
  if [ -z "$found" ] && [[ "$pattern" == */* ]]; then
    found="$(find "$WORK_DIR" -type f -path "$WORK_DIR/*/$pattern" -print -quit)"
  fi
  if [ -z "$found" ] && [[ "$pattern" == \\*/* ]]; then
    local stripped="${{pattern#*/}}"
    found="$(find "$WORK_DIR" -type f -path "$WORK_DIR/$stripped" -print -quit)"
  fi
  if [ -z "$found" ]; then
    found="$(find "$WORK_DIR" -type f -name "$pattern" -print -quit)"
  fi
  test -n "$found" || die "未找到 $label: $pattern"
  printf '%s\\n' "$found"
}}
run_retry() {{
  local label="$1" attempt
  shift
  for attempt in 1 2 3; do
    log "$label: 第 ${{attempt}}/3 次"
    if sudo_run "$@"; then
      log "$label: 成功"
      return 0
    fi
    sleep 1
  done
  die "$label: 失败"
}}
""".strip()


def human_bytes_shell() -> str:
    return r"""
human_bytes() {
  awk -v bytes="${1:-0}" 'BEGIN { split("B KiB MiB GiB TiB", u, " "); v=bytes+0; i=1; while (v>=1024 && i<5) {v/=1024; i++}; if (i==1) printf "%.0f %s", v, u[i]; else printf "%.2f %s", v, u[i] }'
}
space_bytes() { df -PB1 "$1" | awk 'NR==2 {print $4}'; }
""".strip()


def python_zip_extract_shell() -> str:
    return r"""
if command -v python3 >/dev/null 2>&1; then
  python3 - "$PACKAGE_PATH" "$WORK_DIR" <<'PY'
import sys
import zipfile
with zipfile.ZipFile(sys.argv[1]) as zf:
    zf.extractall(sys.argv[2])
PY
elif command -v unzip >/dev/null 2>&1; then
  unzip -q "$PACKAGE_PATH" -d "$WORK_DIR"
else
  die "缺少 zip 解压工具: python3/unzip"
fi
""".strip()
