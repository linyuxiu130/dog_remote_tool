# 中狗导航触发链路分析

Date: 2026-06-02

## Scope

- Product focus: medium dog ZG, especially `zg_lidar_nx` and `zg_surround_s100` for navigation, with RK3588 body control on `zg3588` / `zg_surround_3588`.
- Tool scope: `dog_remote_tool` navigation page and command generation.
- Evidence sources:
  - `/home/user/nav_analysis_merged/00_reports/l2_remote_pull_readme.md`
  - `/home/user/m1_navigation_0.7.0-zzdc-r7_analysis/README.md`
  - unpacked navigation package `navigation_0.7.0-zzdc-r7`
  - local `robots_dog_msgs` message definitions under `/home/user/测试工具/可视化工具/robot_visualizer/src/robots_dog_msgs/msg/`

## Normal App Chain

The app-side request path is owned by `robot_alg_manager`. App/SDK traffic enters one of its WebSocket ports, then the manager opens navigation control and publishes the ROS navigation task:

```text
App/SDK WebSocket -> robot_alg_manager -> change_control_to_nav -> /start_navigation
  -> waypoint_follower -> /navigation_state -> robot_alg_manager / alg_fsm
```

Remote `robot_alg_manager zg-arc` config observed on 2026-06-02:

- app WebSocket: `0.0.0.0:10010`
- SDK WebSocket: `0.0.0.0:10014`
- machine WebSocket: `0.0.0.0:10012`
- SDK ROS bridge: `0.0.0.0:10015`
- app multi-connection: disabled

The verified WebSocket envelope is `head + data`, not `header`. A read-only `get_nav_status` request to SDK port `10014` succeeded with this exact shape:

```json
{"head":{"type":"app_req","time_stamp":1780392817039,"source":"app","frame_count":9301},"data":{"req_func":"get_nav_status"}}
```

The response shape was:

```json
{"head":{"type":"app_resp","time_stamp":1780392815682,"source":"alg_control_node","frame_count":9301},"data":{"req_result":{"AppResponse":{"req_func":"get_nav_status","status":"ok","msg":"Normal","data":"StandBy","error_code":null}}}}
```

App logs for normal patrol show `start_ref_nav`, then `允许若干话题传输`, then `start navigation task: Patrol ... map_path ".../map.yaml" reference ".../map.txt" speed ...`, followed by `Sending change_control_to_nav to machine`.

`robot_alg_manager` strings confirm the request structs:

- `StartRefNavRequestV2`: `map_id`, `map_type`, `map_path`
- `StartMultiNavTaskRequest`: `tasks`
- `GoalMultiNavTaskRequest`: `reference_path`, `goals`, `speed`, `goal_tolerance`, `extra_info`

For the App patrol path seen in logs, `start_ref_nav` reports `map_type: None, map_path: None`; the request should therefore be treated as a manager map request, not a ROS `StartNavigation` task. The minimum inferred patrol request is:

```json
{"head":{"type":"app_req","time_stamp":1780392817039,"source":"app","frame_count":9302},"data":{"req_func":"start_ref_nav","map_id":"2026_06_02_23_28_59"}}
```

After receiving this, the manager resolves the stored map metadata and publishes the ROS task with `map.yaml`, `map.txt`, and speed.

Confirmed graph facts:

- `/start_navigation`
  - type: `robots_dog_msgs/msg/StartNavigation`
  - publisher: `kanon_rust_nav`
  - subscriber: `waypoint_follower`
- `/navigation_state`
  - type: `robots_dog_msgs/msg/NavigationState`
  - publisher: `waypoint_follower`
  - subscribers: `kanon_rust_nav`, `alg_fsm`

`robot_nav2` ZG params confirm:

- `waypoint_follower.node.start_navigation_topic: /start_navigation`
- `waypoint_follower.navigation_state_publisher.navigation_state_topic: /navigation_state`

Therefore direct ROS publishing to `/start_navigation` can verify the navigation package payload, but it does not fully mimic App behavior unless `robot_alg_manager` also grants navigation control. The tool must check `/robot_roamerx/is_in_nav_control` after sending, and report a manager-control failure instead of declaring success only because ROS accepted the message.

## Task Payload

`StartNavigation` is:

```text
std_msgs/Header header
uint8 cmd
NavigationTask[] tasks
```

Relevant command constants:

- `CMD_START=1`
- `CMD_PAUSE=2`
- `CMD_CONTINUE=3`
- `CMD_STOP=4`

Relevant task constants:

- `NavigationTask.TASK_TYPE_INITIAL=2`
- `NavigationTask.TASK_TYPE_GOAL=3`
- `GoalTask.GOAL_TASK_TYPE_GOAL_2D=1`
- `GoalTask.GOAL_TASK_TYPE_GOAL_ROUTE=3`
- `GoalTask.SOURCE_TYPE_GOAL=0`
- `GoalTask.SOURCE_TYPE_REFERENCE_LINE=1`
- `GoalTask.SOURCE_TYPE_REFERENCE_LINE_FILE=2`
- `GoalTask.MAP_TYPE_MAP_2D=1`
- `GoalTask.MAP_TYPE_MAP_ROUTE=3`

For map initialization, ordinary clicked goals, multi-point, and map-track cruise, use `map_type=1` with the selected 2D `map.yaml` when the tool has an explicit selected map. Do not use `map_type=2`: the package defines it as 3D map, and `goal_2d.xml` branches on `map_type=1` for 2D and `map_type=3` for route. `robot_visualizer` only sends `map_type=0` and `map_path=""` when its `current_map_path_` is empty; after a map is selected it sends `MAP_TYPE_MAP_2D` and the current map path.

The local tool mirrors the successful `robot_visualizer` separation: map loading publishes a standalone `CMD_INITIALIZE=0` message with one `InitialTask`; ordinary clicked-goal START then sends only the navigation `GoalTask` and reuses the initialized map. Keeping the initialization task out of the start message avoids treating map-loading state as the actual target-navigation task, and keeping ordinary goals on the fast START path avoids repeated map reload and initialization latency.

Standalone map initialization:

```yaml
header:
  frame_id: map
cmd: 0
tasks:
  - task_type: 2
    initial_task:
      initial_task_type: 1
      map_type: 1
      map_path: /opt/data/.robot/map/map.yaml
```

Minimal ordinary goal start shape:

```yaml
header:
  frame_id: map
cmd: 1
tasks:
  - task_type: 3
    goal_task:
      goal_task_type: 1
      source_type: 0
      map_type: 1
      map_path: /opt/data/.robot/map/map.yaml
      goal: <geometry_msgs/Pose>
      speed: {x: 0.6, y: 0.0, z: 1.2}
      goal_tolerance: {x: 0.0, y: 0.0, theta: 0.0}
```

Multi-point uses the same 2D map fields with:

```yaml
goal_task:
  goal_task_type: 1
  source_type: 1
  reference_line: [<Pose>, <Pose>, ...]
```

Map-track cruise uses:

```yaml
goal_task:
  goal_task_type: 1
  source_type: 2
  reference_line_file_path: /opt/data/.robot/map/history_map/<time>/map.txt
```

Route navigation uses:

```yaml
goal_task:
  goal_task_type: 3
  map_type: 3
```

and must load the route graph through `/RouteGraphPlanner/update_graph` before sending the route target.

## Preconditions

Before sending a navigation task, the tool should keep the fast gate aligned with the App path:

- selected `map.pcd` exists and is non-empty
- `/load_map_service` exists and accepts the selected map
- `/start_navigation` has at least one subscriber
- localization reaches navigation-ready status

The tool no longer blocks on license files, calibration files, Nav2 action servers, `/odom/current_pose`, or perception topics in the normal navigation gate. Those checks are either not part of the App trigger path or are too slow/noisy for repeated App-side navigation testing.

## Feedback And Acceptance

Publishing to `/start_navigation` only proves the message was published. The stronger acceptance signal is `/navigation_state` from `waypoint_follower`.

The tool treats:

- current package codes:
  - `state=140`: initializing, accepted
  - `state=100`: active, accepted
  - `state=200`: succeeded, accepted
  - `state=201`: cancelled, failure for a just-sent start task
  - `state=202`: failed
- compatibility with older observed reports:
  - `state=2`: active, accepted
  - `state=5`: succeeded, accepted
  - `state=4`: cancelled
  - `state=6`: failed
  - `state=1` is only accepted when `task_status` has already entered initializing/executing/succeeded, because current message definitions use `state=1` for standby

If `/navigation_state` does not enter initialize/active/succeeded soon after sending, the tool reports that the navigation task was not observed entering state.

For live diagnosis, inspect:

- `/navigation_state`
- `/navigo/ea/cmn/intf/nav_errors`
- `/perception/detection2d`
- `/navigation_cmd`
- `/handle_vel`
- `/cmd_vel`
- `/robot_control_server/nav_pose`
- `/robot_control_server/mc_state`
- `/robot_roamerx/is_in_nav_control`

## Motion Chain

The navigation package exposes the high-level motion chain as:

```text
controller / behavior
  -> /navigo/cs/cmn/intf/cmd_vel_raw
  -> velocity_optimizer
  -> /navigo/cs/cmn/intf/cmd_vel_smoothed
  -> collision_monitor
  -> /cmd_vel
  -> NavigationCmd / body bridge
  -> chassis
```

`navigo_util::NavigationCmdPublisher` converts `TwistStamped` into `robots_dog_msgs/msg/NavigationCmd`, fills `source=SOURCE_NAV`, sets an MC mode command, and copies the twist into `vel_cmd`.

The tool should not publish direct speed commands to `/cmd_vel`, `/navigation_cmd`, or `/handle_vel` for normal navigation. It should publish the high-level navigation task and then observe whether these topics have output.

## Medium-Dog Manual Control Split

Manual keyboard/body control is a separate channel:

- target: RK3588 body side, usually `192.168.234.1:8081`
- protocol: robot_remote / RobotSDK WebSocket
- remote frame type: `1003`

For `zg_lidar_nx` and `zg_surround_s100`, the tool maps manual body control to the corresponding medium-dog RK3588 profile. This path is for joystick/manual motion only. It is not the normal app navigation trigger.

## Current DogRemoteTool Behavior

The navigation page now:

- sends ordinary/multi-point/cruise navigation through `/start_navigation`
- publishes map initialization as a separate `CMD_INITIALIZE` message from the load-map action, matching `robot_visualizer`
- uses `map_type=1` and the selected `map.yaml` for ordinary clicked-goal START when a map is selected, matching `robot_visualizer::createGoalTasks`
- uses `map_type=1` for multi-point and map-track 2D navigation, and `map_type=3` for route navigation
- loads route graph before route target navigation
- ordinary clicked-goal START directly sends the selected map and target; status/precheck remains available as diagnostics instead of blocking every click
- marks navigation start commands as dangerous because the robot may move
- marks pause, continue, and stop navigation control commands as dangerous because they modify the remote navigation task state; continue may resume robot movement
- route, cruise, and multi-point commands keep stricter checks; ordinary clicked-goal START returns after publish and starts the release watcher
- when `robot_alg_manager` is running, including `zg-arc`, checks `/robot_roamerx/is_in_nav_control`; lack of manager control is reported as a warning and diagnosis clue, but the tool no longer immediately stops an already accepted ROS-direct task
- sends patrol speed fields for ordinary goal (`y=0.0`, `z=1.2`) instead of the earlier manager-inferred `y=0.5`, `z=1.5`
- enables navigation mode after ordinary goal START
- treats ordinary clicked-goal navigation as a quick command: it checks the selected map files, sends START first, then emits a short `/control_right/test=true` pulse and returns control to the UI
- starts a remote background release watcher for ordinary clicked-goal navigation; when `/navigation_state` reaches succeeded/cancelled/failed/standby/idle, it sends `stop_nav` to `robot_alg_manager` WebSocket so alg_manager emits `remove_nav_control` to the machine side and tablet/`robot_remote` can take control again. `/control_right/test=false` is only a fallback when alg_manager is absent.
- samples `/navigation_cmd`, `/handle_vel`, and `/cmd_vel` in status precheck to show whether movement commands are being produced

Follow-up verification on 2026-06-03 sent a low-speed real navigation target through the tool command. The task was accepted and entered `ACTIVE`; actual motion was then blocked by collision-monitor/path selection errors. Source comparison showed that selected-map clicked goals should carry `map_type=1`, selected `map.yaml`, and patrol speed fields (`speed={x:0.6,y:0,z:1.2}`), which explains why the earlier direct tool payload could diverge from the working path.
