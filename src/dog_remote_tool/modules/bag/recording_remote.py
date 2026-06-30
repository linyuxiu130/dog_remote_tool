from __future__ import annotations

import os
import shlex

from dog_remote_tool.modules.bag.names import safe_filename_component
from dog_remote_tool.modules.bag.remote_status import record_process_match_awk_functions


def start_recording_wrapper_command(script: str, remote_bag_paths: list[str]) -> str:
    name = safe_filename_component(os.path.basename(remote_bag_paths[0].rstrip("/")), "rosbag2")
    script_path = f"/tmp/dog_remote_tool_record_{name}.sh"
    log_path = f"/tmp/dog_remote_tool_record_{name}.log"
    pid_path = f"/tmp/dog_remote_tool_record_{name}.pid"
    path_args = " ".join(shlex.quote(path) for path in remote_bag_paths)
    return f"""
script_path={shlex.quote(script_path)}
log_path={shlex.quote(log_path)}
pid_path={shlex.quote(pid_path)}
paths=({path_args})
cat > "$script_path" <<'DOG_REMOTE_RECORD_SCRIPT'
{script}
DOG_REMOTE_RECORD_SCRIPT
chmod 700 "$script_path"
setsid nohup bash "$script_path" > "$log_path" 2>&1 < /dev/null &
pid=$!
printf '%s\\n' "$pid" > "$pid_path"
sleep 1
if ! kill -0 "$pid" 2>/dev/null; then
  echo "remote recording wrapper exited early" >&2
  tail -80 "$log_path" 2>/dev/null >&2 || true
  exit 1
fi
find_record_count() {{
  ps -eww -o pid=,cmd= | awk -v joined="${{paths[*]}}" '
    {record_process_match_awk_functions()}
    BEGIN {{ n = split(joined, paths, " ") }}
    index($0, "DOG_REMOTE_RECORD_SCRIPT") > 0 {{ next }}
    index($0, "ros2 bag record") > 0 {{
      for (i = 1; i <= n; i++) {{
        if (has_output_path($0, paths[i])) {{
          count++
          break
        }}
      }}
    }}
    END {{ print count + 0 }}'
}}
active=0
for _ in $(seq 1 15); do
  active=$(find_record_count)
  [ "$active" -gt 0 ] && break
  if ! kill -0 "$pid" 2>/dev/null; then
    echo "remote recording wrapper exited before ros2 bag became active" >&2
    tail -80 "$log_path" 2>/dev/null >&2 || true
    exit 1
  fi
  sleep 1
done
if [ "$active" -le 0 ]; then
  echo "remote ros2 bag record did not become active" >&2
  tail -80 "$log_path" 2>/dev/null >&2 || true
  exit 1
fi
printf '__DOG_REMOTE_RECORD_STARTED__ pid=%s log=%s\\n' "$pid" "$log_path"
"""


def stop_recording_command(remote_bag_paths: list[str]) -> str:
    path_args = " ".join(shlex.quote(path) for path in remote_bag_paths)
    return f"""
paths=({path_args})
find_record_pids() {{
  ps -eww -o pid=,cmd= | awk -v joined="${{paths[*]}}" '
    {record_process_match_awk_functions()}
    BEGIN {{ n = split(joined, paths, " ") }}
    index($0, "DOG_REMOTE_RECORD_SCRIPT") > 0 {{ next }}
    index($0, "ros2 bag record") > 0 {{
      for (i = 1; i <= n; i++) {{
        if (has_output_path($0, paths[i])) {{
          print $1
          break
        }}
      }}
    }}'
}}
pids="$(find_record_pids | tr '\\n' ' ')"
[ -z "$pids" ] && echo "no remote ros2 bag record process" && exit 0
wait_until_stopped() {{
  label="$1"
  seconds="$2"
  for _ in $(seq 1 "$seconds"); do
    pids="$(find_record_pids | tr '\\n' ' ')"
    [ -z "$pids" ] && echo "remote ros2 bag record stopped after $label" && exit 0
    sleep 1
  done
}}
echo "sending SIGINT to: $pids"
kill -INT $pids 2>/dev/null || true
wait_until_stopped SIGINT 180
echo "still running after SIGINT: $pids"
kill -TERM $pids 2>/dev/null || true
wait_until_stopped SIGTERM 15
echo "still running after SIGTERM: $pids"
kill -KILL $pids 2>/dev/null || true
wait_until_stopped SIGKILL 5
pids="$(find_record_pids | tr '\\n' ' ')"
echo "still running after SIGKILL: $pids" >&2
exit 1
"""
