# 小狗导航不动问题证据收集

Date: 2026-06-03

## 结论摘要

当前证据更支持“小狗机器人侧导航/感知/ARC 包或配置组合不匹配”导致异常，而不是 DogRemoteTool 单独导致。

不能只凭现有证据断言“就是某一个小包版本本身导致”，但 2026-06-03 14:25 小狗重新可达后补采到的证据显示，当前小狗包组合与 `/home/user/下载/M1-武高所基线版本` 不是完整一致的小狗基线，更像是部分组件混装或包组合不一致。已观察到的异常集中在小狗机器人侧：

- `robot_alg_manager` 启动阶段依赖 `/robot_type`，NX 未收到该话题时会卡在启动前置流程。
- 导航任务能被 `/start_navigation` 接受并进入 ACTIVE，但没有确认到底盘实际运动。
- 速度链路没有稳定产生有效非零输出；日志显示局部控制器/碰撞监控持续受 `/laser_scan` 时间戳或缓存异常影响。
- 小狗 `/laser_scan` 的 QoS 组合和中狗不同：小狗 `perception_jobs` 发布 BEST_EFFORT，而 `controller_server` 订阅 RELIABLE；中狗当前 `/laser_scan` 发布 RELIABLE，和控制器 RELIABLE 订阅匹配。
- 小狗日志出现 `laser scan timeout`，甚至在把超时放宽到 5s 后仍出现 24s、56s 级别的 scan dt，说明不是简单阈值过小。
- 当前现场状态下 `/localization_state` 为 `status: 1`，描述为 `Ready: sensor OK, waiting for map to load.`；普通导航栈 lifecycle active，但定位未进入 active 可导航状态。
- 当前 `robot-launch list` 显示 `app-node` 为 `errored`，这会影响从 App 侧进入导航/标记流程。
- 当前 `arc_state_machine_node` 使用 XG 参数反复 exit code -11 崩溃，充电桩/ARC 标定链路处于明确异常状态。

因此可以把问题归类为：小狗当前机器人侧包/配置/运行环境的导航输入链异常，重点在 `perception -> /laser_scan -> controller_server/FollowPathLocalPlanner -> velocity_optimizer/collision_monitor`。

## 已确认事实

### 2026-06-03 14:25 小狗重新可达后的现场状态

1. 普通导航生命周期 active，但定位未加载地图。
   - `/map_server`、`/controller_server`、`/planner_server`、`/bt_navigator`、`/waypoint_follower`、`/velocity_optimizer` 均为 `active [3]`。
   - `/navigation_state` 为 idle，`errors: []`。
   - `/localization_state` 为 `status: 1`，描述：`Ready: sensor OK, waiting for map to load.`。
   - `/ota/alg_data/map/map.pcd` 和 `/ota/alg_data/map/map.yaml` 存在，但当前定位节点未进入 map-loaded active 状态。

2. App/ARC 链路异常明确。
   - `robot-launch list` 显示 `app-node` 为 `errored`。
   - 最近 ROS 日志显示 `arc_state_machine_node` 持续崩溃：`exit code -11`。
   - 崩溃命令使用 XG 配置：`arc_state_machine_params.yaml`。
   - 这能解释从 App 进入标记充电桩/ARC 流程失败；它不等同于普通点到点导航失败。

3. `/laser_scan` 现场 QoS 仍不匹配。
   - publisher：`perception_jobs`，Reliability `BEST_EFFORT`。
   - `controller_server` subscriber：Reliability `RELIABLE`。
   - `local_costmap` 和 `collision_monitor` subscriber：`BEST_EFFORT`。
   - 现场 `/laser_scan` 频率约 10 Hz，header 延迟约 0.5s；频率本身正常，但 controller 的 QoS 订阅仍是高风险点。

4. 当前小狗安装包。
   - `navigation 0.7.0-zzdc-r7`
   - `robot-slam 0.4.9-r10`
   - `robots_dog_msgs 0.8.3`
   - `robot-alg-manager 0.2.6-r9`
   - `robot-arc 0.3.2`
   - `det-inference-nx 0.5.7-onnx-r3`

5. `/home/user/下载/M1-武高所基线版本` 包目录对比。
   - 目录中 `navigation_0.7.0-zzdc-r7_arm64.deb`、`robot-slam_0.4.9-r10_arm64.deb`、`robots_dog_msgs_0.8.3...deb` 与当前小狗部分组件版本一致。
   - 目录中 `robot-alg-manager_0.2.7-api-rzt3_arm64.deb` 与当前小狗 `0.2.6-r9` 不一致。
   - 目录中 `robot-arc_0.3.2-r7_arm64.deb` 与当前小狗 `0.3.2` 不一致。
   - 目录中感知包是 `perception-zg_0.5.6~zg-r1-onnx_arm64.deb`，当前小狗是 `det-inference-nx 0.5.7-onnx-r3`，不是同一条小狗感知包线。
   - 该 M1 目录更像中狗/武高所基线包集合；不能直接作为小狗整包基线安装。

### 小狗当时的直接故障

1. `robot_alg_manager xg` 启动曾被 `/robot_type` 卡住。
   - RK3588 侧有 `/robot_type` 发布，但 NX 侧未收到。
   - 给 `/opt/robot/nx-launch/script/alg-manager.sh` 加了 XG fallback 后，`robot_alg_manager xg` 和 Nav2 才能稳定启动。
   - 这是启动脚本/跨板通信/包假设问题，不是导航目标点本身问题。

2. Nav2 生命周期后来已经 active，地图加载和定位也能进入 active。
   - `/map_server`、`/controller_server`、`/planner_server`、`/bt_navigator`、`/waypoint_follower`、`/collision_monitor`、`/velocity_optimizer` 均 active。
   - `/load_map_service` 能成功加载 `/ota/alg_data/map/map.pcd`。
   - `/localization_state` 可到 `status=3`。

3. 小狗任务被接受但未确认实际运动。
   - 用户现场反馈没有实际移动。
   - 之前看到的 pose/distance 变化不能当作底盘运动成功，因为可能来自定位重定位/位姿跳变。
   - 后续应只用速度链和底盘状态确认运动。

4. 小狗速度/感知链阻塞证据。
   - 导航日志出现 `local_planner_controller: laser scan timeout`。
   - 放宽 `FollowPathLocalPlanner.laser_scan.scan_timeout` 到 5.0 后仍有大 dt，例如 24s、56s 级 scan timeout。
   - `collision_monitor` 日志曾出现 scan 与节点当前时间差过大并忽略 source 的模式。
   - `/laser_scan` 时间戳曾出现相对当前时间异常，且控制器侧缓存疑似冻结。

5. 小狗 QoS 差异。
   - 小狗：`/laser_scan` publisher `perception_jobs` 是 BEST_EFFORT；`controller_server` subscriber 是 RELIABLE。
   - 中狗：`/laser_scan` publisher 是 RELIABLE；`controller_server` subscriber 也是 RELIABLE。
   - 这能解释为什么同样是 FollowPathLocalPlanner，中狗的 controller 更容易拿到 scan，而小狗 controller 可能收不到或缓存异常。

### 中狗对照证据

1. 当前中狗 NX 导航包日志：
   - `Version: 0.7.0`
   - `Revision: zzdc-r6`
   - `Built at: May 15 2026 18:40:22`

2. 本机历史小狗日志显示老包：
   - `Version: 0.6.9`
   - `Built at: Apr 18 2026 00:19:48`
   - 注意：这是 2026-05-08/2026-05-20 本机历史日志，不等于今天小狗当前安装版本。

3. 中狗当前曾误报激光/定位超时。
   - 实测 `/laser_scan` 10 Hz，header 延迟约 0.3-0.4s。
   - 但 `navigo_error_aggregator` 默认 `delay_threshold_sec: 0.2`，所以误报。
   - 已把中狗错误聚合器配置调整为 delay 0.8s、timeout 2.0s 并重启 `robot-alg-manager`。
   - 修复后中狗 `/navigation_state.errors=[]`。

## 不是主要根因的项

- DogRemoteTool 本地 bug：曾用 `ps comm` 检测 `robot_alg_manager`，被 Linux 截断成 `robot_alg_manag`，导致工具误报“未检测到 manager”。这只影响工具提示，不会导致机器人不动。
- 单纯 `/start_navigation` 发布成功：只能说明 ROS 任务被发出，不能证明 App/manager 控制权切换，也不能证明底盘运动。
- 单纯定位 pose 变化：不能证明机器人实际移动。

## 待补采证据

小狗恢复可达后，需要立刻采这些命令来确认是否确实是包版本/小包导致：

```bash
sshpass -p 1 ssh robot@192.168.234.234 '
source /opt/ros/humble/setup.bash
source /opt/robot/robot_nav/install/setup.bash 2>/dev/null || true
export ROS_DOMAIN_ID=24 RMW_IMPLEMENTATION=rmw_zenoh_cpp ROS_LOCALHOST_ONLY=0

echo "=== package versions ==="
dpkg -l | grep -Ei "navigation|robot_nav|perception|robot_slam|robot-alg|robot_alg|robots-dog-msgs" || true

echo "=== navigation build info ==="
grep -nEi "Build Info|Version|Revision|Built at|robot_type|params_file" /tmp/log/alg_data/navigation_with_setup.log | tail -80

echo "=== laser qos ==="
ros2 topic info -v /laser_scan

echo "=== scan timing ==="
python3 - <<PY
import subprocess, time, re
s=subprocess.run(["bash","-lc","timeout 3s ros2 topic echo --once /laser_scan 2>/dev/null"], text=True, stdout=subprocess.PIPE).stdout
m=re.search(r"stamp:\\n\\s*sec:\\s*(\\d+)\\n\\s*nanosec:\\s*(\\d+)", s)
if m:
    stamp=int(m.group(1))+int(m.group(2))/1e9
    print("now", time.time(), "stamp", stamp, "dt", time.time()-stamp)
else:
    print("no stamp")
PY

echo "=== nav params ==="
ros2 param get /controller_server FollowPathLocalPlanner.laser_scan.scan_timeout || true
ros2 param get /collision_monitor source_timeout || true

echo "=== recent nav errors ==="
grep -nEi "laser scan|timeout|timestamps differ|Ignoring the source|cmd_vel|Goals accepted|state transition|ERROR|FAILED" /tmp/log/alg_data/navigation_with_setup.log | tail -160
'
```

## 当前判断

如果“小包版本”指的是小狗上的导航/感知/alg-manager 小包，那么它是高度可疑项。更准确地说，异常不像是单个 UI 操作引起，而像是小狗当前包组合或配置导致：

- `robot_type` 跨板获取逻辑不稳；
- `/laser_scan` QoS 与 controller 订阅不匹配；
- scan 时间戳或缓存新鲜度不满足 FollowPathLocalPlanner/collision_monitor；
- 导航接单后不能形成可信的非零底盘速度链。

要最终定责，需要拿到小狗当天的 installed package versions 和 `/laser_scan` QoS/timing 现场输出。
