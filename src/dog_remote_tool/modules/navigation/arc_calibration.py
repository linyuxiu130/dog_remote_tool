from __future__ import annotations

from dog_remote_tool.core.profiles import ProductProfile
from dog_remote_tool.core.shell import CommandSpec, echo_message, quote, remote_env, ssh_command
from dog_remote_tool.modules.navigation import payloads as _payloads
from dog_remote_tool.modules.navigation import probe as _probe


def start_arc_calibration_command(profile: ProductProfile, tag_id: int = 0, monitor_seconds: int = 45) -> CommandSpec:
    payload = _payloads._start_arc_calibration_payload(tag_id)
    monitor_seconds = max(10, min(int(monitor_seconds), 120))
    config_dir = "/opt/robot/robot_arc/install/apriltag_localization/config"
    pc_config = f"{config_dir}/apriltag_localization_pc_config.yaml"
    middle_dog_config = f"{config_dir}/apriltag_localization_pc_config_middle_dog.yaml"
    inner = (
        f"{remote_env(profile)}; "
        "source /opt/robot/robot_arc/install/setup.bash >/dev/null 2>&1 || true; "
        "if ! ros2 interface show robots_dog_msgs/msg/StartArc >/dev/null 2>&1; then "
        "echo '[ERROR] robots_dog_msgs/msg/StartArc 不可用，请检查 robot_arc 环境'; exit 2; fi; "
        "ARC_SUBS=$(" + _probe.topic_subscription_count("/arc/start_arc", timeout=2) + "); "
        "if [ \"$ARC_SUBS\" -lt 1 ]; then echo '[ERROR] /arc/start_arc 没有订阅者，arc_state_machine 可能未运行'; exit 3; fi; "
        "CFG_STAT=$(mktemp /tmp/dog_remote_arc_calibration_cfg.XXXXXX); "
        "POSE_SAMPLES=$(mktemp /tmp/dog_remote_arc_calibration_pose.XXXXXX); "
        f"for cfg in {quote(pc_config)} {quote(middle_dog_config)}; do "
        "if [ -f \"$cfg\" ]; then echo \"$cfg $(stat -c %Y \"$cfg\" 2>/dev/null || echo 0)\" >> \"$CFG_STAT\"; fi; "
        "done; "
        f"{echo_message(f'[INFO] 发送充电桩标定请求: tag_id={int(tag_id)}')}; "
        "PUB_LOG=$(mktemp /tmp/dog_remote_arc_calibration_pub.XXXXXX); "
        "trap 'rm -f \"$PUB_LOG\" \"$CFG_STAT\" \"$POSE_SAMPLES\"' EXIT; "
        f"if timeout 8s ros2 topic pub --once /arc/start_arc robots_dog_msgs/msg/StartArc {quote(payload)} > \"$PUB_LOG\" 2>&1; then "
        "echo '[INFO] 标定请求已发送，开始回读 /arc/calibration_state 和 /arc/arc_state'; "
        "else echo '[ERROR] 标定请求发送失败'; cat \"$PUB_LOG\"; exit 7; fi; "
        f"END=$((SECONDS + {monitor_seconds})); "
        "LAST_SNAPSHOT=; "
        "SAW_ARC_SUCCESS=0; SAW_ARC_FAILURE=0; FINAL_ARC_STATE=; FINAL_CALIB_STATE=; "
        "while [ \"$SECONDS\" -lt \"$END\" ]; do "
        "CALIB_MSG=$(timeout 1s ros2 topic echo --once /arc/calibration_state --no-daemon 2>/dev/null || true); "
        "ARC_MSG=$(timeout 1s ros2 topic echo --once /arc/arc_state --no-daemon 2>/dev/null || true); "
        "CALIB_STATE=$(printf '%s\\n' \"$CALIB_MSG\" | awk '/^state:/ {print $2; exit}'); "
        "ARC_STATE=$(printf '%s\\n' \"$ARC_MSG\" | awk '/^state:/ {print $2; exit}'); "
        "ARC_DESC=$(printf '%s\\n' \"$ARC_MSG\" | sed -n \"s/^description:[[:space:]]*//p\" | head -1 | sed \"s/^'//;s/'$//\"); "
        "FINAL_ARC_STATE=${ARC_STATE:-$FINAL_ARC_STATE}; FINAL_CALIB_STATE=${CALIB_STATE:-$FINAL_CALIB_STATE}; "
        "SNAPSHOT=\"calibration_state=${CALIB_STATE:-无} arc_state=${ARC_STATE:-无} ${ARC_DESC:-}\"; "
        "if [ \"$SNAPSHOT\" != \"$LAST_SNAPSHOT\" ]; then echo '[INFO] '\"$SNAPSHOT\"; LAST_SNAPSHOT=\"$SNAPSHOT\"; fi; "
        "case \"$ARC_STATE\" in 10) SAW_ARC_SUCCESS=1; break ;; 11|12) SAW_ARC_FAILURE=1; break ;; esac; "
        "sleep 2; "
        "done; "
        "if [ \"$SAW_ARC_FAILURE\" = 1 ]; then echo '[ERROR] ARC 状态机返回标定失败: arc_state='\"${FINAL_ARC_STATE:-无}\"; "
        "elif [ \"$SAW_ARC_SUCCESS\" = 1 ]; then echo '[INFO] ARC 状态机返回标定成功'; "
        "else echo '[WARN] 监控窗口内未看到 ARC SUCCESS，最后状态: arc_state='\"${FINAL_ARC_STATE:-无}\"' calibration_state='\"${FINAL_CALIB_STATE:-无}\"; fi; "
        f"echo '[INFO] AprilTag 配置目录: {config_dir}'; "
        "CFG_CHANGED=0; "
        "while read -r cfg old_mtime; do "
        "[ -n \"$cfg\" ] || continue; "
        "new_mtime=$(stat -c %Y \"$cfg\" 2>/dev/null || echo 0); "
        "human_mtime=$(stat -c %y \"$cfg\" 2>/dev/null | cut -d. -f1); "
        "if [ \"$new_mtime\" != \"$old_mtime\" ]; then CFG_CHANGED=1; changed=yes; else changed=no; fi; "
        "echo '[INFO] config='\"$cfg\"' mtime='\"$human_mtime\"' changed='\"$changed\"; "
        "grep -n 'T_tag_dockbase_calib\\|T_tagonchargingbox_chargingbox' \"$cfg\" || true; "
        "python3 -c 'import re,sys; text=open(sys.argv[1],encoding=\"utf-8\",errors=\"ignore\").read(); "
        "m=re.search(r\"T_tag_dockbase_calib:.*?data:\\\\s*\\\\[(.*?)\\\\]\", text, re.S); "
        "nums=[float(x) for x in re.findall(r\"[-+]?\\\\d+(?:\\\\.\\\\d*)?(?:[eE][-+]?\\\\d+)?\", m.group(1))] if m else []; "
        "print(\"[INFO] T_tag_dockbase_calib平移: tx=%.6fm ty=%.6fm tz=%.6fm\" % (nums[3], nums[7], nums[11])) if len(nums) >= 12 else None' \"$cfg\" || true; "
        "done < \"$CFG_STAT\"; "
        "echo '[INFO] 开始标定后精度采样：/arc/perception_dock_pose，核心看 y 横向偏差和 yaw 航向偏差；机器人保持静止时 jitter 越小越好'; "
        "for i in 1 2 3 4 5 6 7 8; do "
        "POSE_MSG=$(timeout 1s ros2 topic echo --once /arc/perception_dock_pose --no-daemon 2>/dev/null || true); "
        "PX=$(printf '%s\\n' \"$POSE_MSG\" | awk '/position:/ {p=1; next} p && /^[[:space:]]*x:/ {print $2; exit}'); "
        "PY=$(printf '%s\\n' \"$POSE_MSG\" | awk '/position:/ {p=1; next} p && /^[[:space:]]*y:/ {print $2; exit}'); "
        "PZ=$(printf '%s\\n' \"$POSE_MSG\" | awk '/position:/ {p=1; next} p && /^[[:space:]]*z:/ {print $2; exit}'); "
        "QX=$(printf '%s\\n' \"$POSE_MSG\" | awk '/orientation:/ {o=1; next} o && /^[[:space:]]*x:/ {print $2; exit}'); "
        "QY=$(printf '%s\\n' \"$POSE_MSG\" | awk '/orientation:/ {o=1; next} o && /^[[:space:]]*y:/ {print $2; exit}'); "
        "QZ=$(printf '%s\\n' \"$POSE_MSG\" | awk '/orientation:/ {o=1; next} o && /^[[:space:]]*z:/ {print $2; exit}'); "
        "QW=$(printf '%s\\n' \"$POSE_MSG\" | awk '/orientation:/ {o=1; next} o && /^[[:space:]]*w:/ {print $2; exit}'); "
        "YAW=$(python3 -c 'import math,sys; q=list(map(float, sys.argv[1:5])); x,y,z,w=q; print(math.atan2(2*(w*z+x*y), 1-2*(y*y+z*z)))' ${QX:-0} ${QY:-0} ${QZ:-0} ${QW:-1} 2>/dev/null || echo 0); "
        "CONF=$(printf '%s\\n' \"$POSE_MSG\" | awk '/^confidence:/ {print $2; exit}'); "
        "if [ -n \"$PX\" ] && [ -n \"$PY\" ]; then echo \"$PX $PY ${PZ:-0} ${YAW:-0} ${CONF:-0}\" >> \"$POSE_SAMPLES\"; fi; "
        "sleep 0.25; "
        "done; "
        "SAMPLE_COUNT=$(wc -l < \"$POSE_SAMPLES\" | tr -d ' '); "
        "if [ \"$SAMPLE_COUNT\" -lt 3 ]; then echo '[WARN] /arc/perception_dock_pose 有效样本不足，无法判断标定后感知稳定性'; "
        "else awk 'NR==1{minx=maxx=$1; miny=maxy=$2; minz=maxz=$3; minyaw=maxyaw=$4; minc=maxc=$5} {sx+=$1;sy+=$2;sz+=$3;syaw+=$4;if($1<minx)minx=$1;if($1>maxx)maxx=$1;if($2<miny)miny=$2;if($2>maxy)maxy=$2;if($3<minz)minz=$3;if($3>maxz)maxz=$3;if($4<minyaw)minyaw=$4;if($4>maxyaw)maxyaw=$4;if($5<minc)minc=$5;if($5>maxc)maxc=$5} END{myaw=syaw/NR; printf \"[INFO] 对桩精度核心: samples=%d mean_x=%.4fm mean_y=%.4fm mean_yaw=%.4frad(%.2fdeg)\\n\", NR, sx/NR, sy/NR, myaw, myaw*57.2957795; printf \"[INFO] 感知稳定性: jitter_x=%.4fm jitter_y=%.4fm jitter_yaw=%.4frad(%.2fdeg) dz=%.4fm confidence=%.3f..%.3f\\n\", maxx-minx, maxy-miny, maxyaw-minyaw, (maxyaw-minyaw)*57.2957795, maxz-minz, minc, maxc}' \"$POSE_SAMPLES\"; fi; "
        "if [ \"$CFG_CHANGED\" = 1 ]; then echo '[INFO] 标定配置已更新。若后续感知或建图结果仍未更新，请重启 ARC 感知、状态机、arc_mapping 后复测'; "
        "else echo '[WARN] 未检测到配置文件更新时间变化；如果状态机显示成功，也需要确认该版本是否只在内存中生效或写入了其他配置文件'; fi; "
        "echo '[INFO] 下一步：确认 /arc/perception_dock_pose 稳定，再执行标记充电桩；标记完成后检查 map.yaml 中 arc_position_flag=1'; "
        "if [ \"$SAW_ARC_FAILURE\" = 1 ]; then exit 8; fi; "
    )
    return CommandSpec(
        "标定充电桩",
        ssh_command(profile, inner),
        dangerous=True,
        description=(
            "请确认机器狗已经趴在充电桩上正确标定位置，触点/姿态稳定后再继续。"
            "该操作会向 ARC 状态机发送充电桩标定请求，可能改变远端 ARC 标定结果。"
        ),
        display_command="执行：ARC 标定充电桩",
        concurrency="parallel",
        locks=("arc", "motion"),
    )
