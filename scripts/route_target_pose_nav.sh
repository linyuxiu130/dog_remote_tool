#!/usr/bin/env bash
set -euo pipefail

TARGET_FILE="/ota/alg_data/map/target_pose.txt"
ROUTE_FILE="/ota/alg_data/map/map.geojson"
MAP_YAML="/ota/alg_data/map/map.yaml"
MODE="auto"
INDEX="-1"
PCD_NAME=""
YAW="0"
SPEED="0.6"
TOLERANCE="0.25"
UPDATE_GRAPH="1"
MODE_SWITCH="1"
DRY_RUN="0"

usage() {
  cat <<'USAGE'
Usage:
  route_target_pose_nav.sh [options]

Read x/y targets from /ota/alg_data/map/target_pose.txt and send a navigation
goal through /start_navigation. In auto mode, the script uses route-network
navigation when map.geojson exists, otherwise it sends a normal 2D map goal.

Options:
  --target-file PATH   Target pose file. Default: /ota/alg_data/map/target_pose.txt
  --route-file PATH    Route GeoJSON file. Default: /ota/alg_data/map/map.geojson
  --map-yaml PATH      2D navigation map YAML. Default: /ota/alg_data/map/map.yaml
  --mode MODE          auto, route, or goal2d. Default: auto
  --index N            1-based line index. Negative values count from the end. Default: -1
  --pcd NAME           Select the line whose third column equals NAME
  --yaw RAD            Goal yaw in radians. Default: 0
  --speed MPS          Linear speed x. Default: 0.6
  --tolerance M        Goal x/y tolerance. Default: 0.25
  --no-update-graph    Skip /RouteGraphPlanner/update_graph
  --no-mode-switch     Skip /control_right/test=true pulse
  --dry-run            Print selected target and ROS payloads without publishing
  -h, --help           Show this help

Examples:
  ./route_target_pose_nav.sh
  ./route_target_pose_nav.sh --index -1
  ./route_target_pose_nav.sh --pcd 1782155255299987078.pcd
USAGE
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --target-file) TARGET_FILE="${2:?missing value for --target-file}"; shift 2 ;;
    --route-file) ROUTE_FILE="${2:?missing value for --route-file}"; shift 2 ;;
    --map-yaml) MAP_YAML="${2:?missing value for --map-yaml}"; shift 2 ;;
    --mode) MODE="${2:?missing value for --mode}"; shift 2 ;;
    --index) INDEX="${2:?missing value for --index}"; shift 2 ;;
    --pcd) PCD_NAME="${2:?missing value for --pcd}"; shift 2 ;;
    --yaw) YAW="${2:?missing value for --yaw}"; shift 2 ;;
    --speed) SPEED="${2:?missing value for --speed}"; shift 2 ;;
    --tolerance) TOLERANCE="${2:?missing value for --tolerance}"; shift 2 ;;
    --no-update-graph) UPDATE_GRAPH="0"; shift ;;
    --no-mode-switch) MODE_SWITCH="0"; shift ;;
    --dry-run) DRY_RUN="1"; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "[ERROR] Unknown argument: $1" >&2; usage >&2; exit 2 ;;
  esac
done

if [ ! -s "$TARGET_FILE" ]; then
  echo "[ERROR] target pose file is missing or empty: $TARGET_FILE" >&2
  exit 2
fi

case "$MODE" in
  auto|route|goal2d) ;;
  *) echo "[ERROR] invalid --mode: $MODE" >&2; exit 2 ;;
esac

if [ "$MODE" = "auto" ]; then
  if [ -s "$ROUTE_FILE" ]; then
    MODE="route"
  else
    MODE="goal2d"
  fi
fi

if [ "$MODE" = "route" ] && [ ! -s "$ROUTE_FILE" ]; then
  echo "[ERROR] route GeoJSON file is missing or empty: $ROUTE_FILE" >&2
  exit 2
fi

if [ "$MODE" = "goal2d" ] && [ ! -s "$MAP_YAML" ]; then
  echo "[ERROR] 2D navigation map YAML is missing or empty: $MAP_YAML" >&2
  exit 2
fi

BUILD_OUTPUT="$(
  python3 - "$TARGET_FILE" "$ROUTE_FILE" "$MAP_YAML" "$MODE" "$INDEX" "$PCD_NAME" "$YAW" "$SPEED" "$TOLERANCE" <<'PY'
import json
import math
import shlex
import sys

target_file, route_file, map_yaml, mode, index_text, pcd_name, yaw_text, speed_text, tolerance_text = sys.argv[1:]

def parse_float(text, name):
    try:
        return float(text)
    except ValueError:
        raise SystemExit(f"[ERROR] invalid {name}: {text}")

try:
    index = int(index_text)
except ValueError:
    raise SystemExit(f"[ERROR] invalid --index: {index_text}")

yaw = parse_float(yaw_text, "yaw")
speed = parse_float(speed_text, "speed")
tolerance = parse_float(tolerance_text, "tolerance")

rows = []
with open(target_file, "r", encoding="utf-8") as handle:
    for line_no, raw_line in enumerate(handle, start=1):
        stripped = raw_line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        fields = stripped.split()
        if len(fields) < 3:
            continue
        try:
            x = float(fields[0])
            y = float(fields[1])
        except ValueError:
            continue
        rows.append((line_no, x, y, fields[2]))

if not rows:
    raise SystemExit(f"[ERROR] no valid target rows in {target_file}")

if pcd_name:
    matches = [row for row in rows if row[3] == pcd_name]
    if not matches:
        raise SystemExit(f"[ERROR] pcd target not found: {pcd_name}")
    selected = matches[-1]
else:
    if index == 0:
        raise SystemExit("[ERROR] --index is 1-based; 0 is invalid")
    position = index - 1 if index > 0 else len(rows) + index
    if position < 0 or position >= len(rows):
        raise SystemExit(f"[ERROR] --index out of range: {index}; valid rows={len(rows)}")
    selected = rows[position]

line_no, x, y, pcd = selected
half = yaw / 2.0
z = math.sin(half)
w = math.cos(half)
quoted_route = json.dumps(route_file, ensure_ascii=False)
quoted_map_yaml = json.dumps(map_yaml, ensure_ascii=False)
update_payload = "{filepath: " + quoted_route + "}"
if mode == "route":
    nav_payload = (
        "{header: {frame_id: \"map\"}, cmd: 1, tasks: ["
        "{task_type: 3, goal_task: {goal_task_type: 3, source_type: 0, map_type: 3, map_path: "
        + quoted_route
        + ", "
        + f"goal: {{position: {{x: {x:.6f}, y: {y:.6f}, z: 0.0}}, "
        + f"orientation: {{x: 0.0, y: 0.0, z: {z:.9f}, w: {w:.9f}}}}}, "
        + f"speed: {{x: {speed:.3f}, y: 0.000, z: 1.200}}, "
        + f"goal_tolerance: {{x: {tolerance:.3f}, y: {tolerance:.3f}, theta: 0.100}}"
        + "}}]}"
    )
else:
    theta_tolerance = 0.0 if abs(tolerance) < 1e-9 else 0.1
    nav_payload = (
        "{header: {frame_id: \"map\"}, cmd: 1, tasks: ["
        "{task_type: 3, goal_task: {goal_task_type: 1, source_type: 0, map_type: 1, map_path: "
        + quoted_map_yaml
        + ", "
        + f"goal: {{position: {{x: {x:.6f}, y: {y:.6f}, z: 0.0}}, "
        + f"orientation: {{x: 0.0, y: 0.0, z: {z:.9f}, w: {w:.9f}}}}}, "
        + f"speed: {{x: {speed:.3f}, y: 0.000, z: 1.200}}, "
        + f"goal_tolerance: {{x: {tolerance:.3f}, y: {tolerance:.3f}, theta: {theta_tolerance:.3f}}}"
        + "}}]}"
    )

for key, value in {
    "NAV_MODE": mode,
    "SELECTED_LINE": str(line_no),
    "TARGET_X": f"{x:.9f}",
    "TARGET_Y": f"{y:.9f}",
    "TARGET_PCD": pcd,
    "UPDATE_GRAPH_PAYLOAD": update_payload,
    "START_NAV_PAYLOAD": nav_payload,
}.items():
    print(f"{key}={shlex.quote(value)}")
PY
)"

eval "$BUILD_OUTPUT"

echo "[INFO] selected target: line=${SELECTED_LINE} x=${TARGET_X} y=${TARGET_Y} pcd=${TARGET_PCD}"
if [ "$NAV_MODE" = "route" ]; then
  echo "[INFO] navigation mode: route"
  echo "[INFO] route file: ${ROUTE_FILE}"
else
  echo "[INFO] navigation mode: goal2d"
  echo "[INFO] map yaml: ${MAP_YAML}"
fi

if [ "$DRY_RUN" = "1" ]; then
  if [ "$NAV_MODE" = "route" ]; then
    echo "[DRY-RUN] update_graph payload:"
    printf '%s\n' "$UPDATE_GRAPH_PAYLOAD"
  fi
  echo "[DRY-RUN] /start_navigation payload:"
  printf '%s\n' "$START_NAV_PAYLOAD"
  exit 0
fi

export ROS_DOMAIN_ID="${ROS_DOMAIN_ID:-24}"
export RMW_IMPLEMENTATION="${RMW_IMPLEMENTATION:-rmw_zenoh_cpp}"
export ROS_LOCALHOST_ONLY="${ROS_LOCALHOST_ONLY:-0}"

if [ -f /opt/runtime/env.bash ]; then
  # shellcheck disable=SC1091
  source /opt/runtime/env.bash >/dev/null 2>&1 || true
fi
if [ -f /opt/ros/humble/setup.bash ]; then
  # shellcheck disable=SC1091
  source /opt/ros/humble/setup.bash >/dev/null 2>&1 || true
fi
if [ -f /opt/robot/robot_nav/install/setup.bash ]; then
  # shellcheck disable=SC1091
  source /opt/robot/robot_nav/install/setup.bash >/dev/null 2>&1 || true
fi

if ! command -v ros2 >/dev/null 2>&1; then
  echo "[ERROR] ros2 command not found after sourcing environment" >&2
  exit 3
fi

if [ "$NAV_MODE" = "route" ] && [ "$UPDATE_GRAPH" = "1" ]; then
  echo "[INFO] checking /RouteGraphPlanner/update_graph"
  if ! timeout 4s ros2 service list --no-daemon 2>/dev/null | grep -Fx -- /RouteGraphPlanner/update_graph >/dev/null; then
    echo "[ERROR] /RouteGraphPlanner/update_graph is not ready" >&2
    exit 4
  fi
  echo "[INFO] updating route graph"
  timeout 20s ros2 service call /RouteGraphPlanner/update_graph robots_dog_msgs/srv/UpdateGraph "$UPDATE_GRAPH_PAYLOAD"
fi

if [ "$MODE_SWITCH" = "1" ]; then
  echo "[INFO] enabling navigation control mode"
  timeout 1s ros2 topic pub -r 20 /control_right/test std_msgs/msg/Bool "{data: true}" >/dev/null 2>&1 || true
fi

echo "[INFO] publishing route navigation goal"
timeout 8s ros2 topic pub -1 /start_navigation robots_dog_msgs/msg/StartNavigation "$START_NAV_PAYLOAD"
echo "[INFO] route navigation goal submitted"
