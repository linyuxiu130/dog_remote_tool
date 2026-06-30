from __future__ import annotations

from dog_remote_tool.core.profiles import ProductProfile
from dog_remote_tool.core.shell import CommandSpec, echo_message, remote_env, ssh_command


MC_MODE_LABELS = {
    1: "对膝 WALK",
    3: "同膝 WALK",
}


def _navigation_mc_mode_script(profile: ProductProfile, mc_mode: int) -> str:
    sequence = [1] if mc_mode == 1 else [1, mc_mode]
    return f"""set -e
{remote_env(profile)}
source /opt/robot/robot_nav/install/setup.bash >/dev/null 2>&1 || true
NAV_MSG=$(timeout 2s ros2 topic echo --once /navigation_state --no-daemon 2>/dev/null || true)
NAV_STATE=$(printf '%s\\n' "$NAV_MSG" | awk '/^state:/ {{print $2; exit}}')
NAV_TASK_STATUS=$(printf '%s\\n' "$NAV_MSG" | awk '/task_status:/ {{print $NF; exit}}')
case "$NAV_STATE:$NAV_TASK_STATUS" in
  2:*|3:*|100:*|140:*|141:*|*:1|*:2|*:3)
    printf '%s\\n' "[ERROR] 当前导航仍在执行或暂停，拒绝手动切换运控模式。NAV_STATE=${{NAV_STATE:-}} NAV_TASK_STATUS=${{NAV_TASK_STATUS:-}}"
    exit 3
    ;;
esac
if [ -z "$NAV_MSG" ]; then
  printf '%s\\n' "[WARN] 未读到 /navigation_state，继续执行零速运控模式切换。"
fi
CMD_TOPIC=/navigo/cs/cmn/intf/cmd_vel_raw
CMD_TYPE=$(timeout 2s ros2 topic type "$CMD_TOPIC" --no-daemon 2>/dev/null || true)
if [ "$CMD_TYPE" != "robots_dog_msgs/msg/VelCmd" ]; then
  printf '%s\\n' "[ERROR] $CMD_TOPIC 类型不是 robots_dog_msgs/msg/VelCmd，当前为: ${{CMD_TYPE:-无数据}}"
  exit 2
fi
python3 - <<'PY'
import time

import rclpy
from geometry_msgs.msg import Twist
from robots_dog_msgs.msg import VelCmd

sequence = {sequence!r}
duration_by_mode = {{1: 1.1}}
default_duration = 0.8

rclpy.init(args=None)
node = rclpy.create_node("dog_remote_navigation_mc_mode")
pub = node.create_publisher(VelCmd, "/navigo/cs/cmn/intf/cmd_vel_raw", 10)
deadline = time.time() + 1.5
while time.time() < deadline and pub.get_subscription_count() < 1:
    rclpy.spin_once(node, timeout_sec=0.05)

subs = pub.get_subscription_count()
if subs < 1:
    print("[WARN] /navigo/cs/cmn/intf/cmd_vel_raw 暂未发现订阅者，仍发布零速模式帧。", flush=True)

for mode in sequence:
    duration = duration_by_mode.get(mode, default_duration)
    end = time.time() + duration
    while time.time() < end:
        msg = VelCmd()
        msg.vel_cmd = Twist()
        msg.mc_mode_cmd = int(mode)
        pub.publish(msg)
        rclpy.spin_once(node, timeout_sec=0.0)
        time.sleep(0.05)
    print(f"[INFO] 已发布零速 mc_mode_cmd={{mode}} 持续 {{duration:.1f}}s", flush=True)

node.destroy_node()
rclpy.shutdown()
PY
"""


def navigation_mc_mode_command(profile: ProductProfile, mc_mode: int) -> CommandSpec:
    label = MC_MODE_LABELS.get(mc_mode)
    if label is None:
        return CommandSpec("导航运控模式", echo_message(f"[ERROR] 不支持的 mc_mode_cmd: {mc_mode}"))
    if profile.key not in {"zg_lidar_nx", "zg_surround_s100"}:
        return CommandSpec("导航运控模式", echo_message("[ERROR] 当前仅支持中狗 NX/S100 导航运控模式切换。"))
    script = _navigation_mc_mode_script(profile, mc_mode)
    return CommandSpec(
        f"导航运控模式：{label}",
        ssh_command(profile, script),
        dangerous=True,
        description="会在导航待命时向 /navigo/cs/cmn/intf/cmd_vel_raw 发布零速 VelCmd，只切换 mc_mode_cmd，不发送位移速度。",
        display_command=f"执行：导航运控模式 {label}",
    )
