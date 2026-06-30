# Navigation And Remote Control Cleanup

## Goal

Make navigation exit cleanup reliable on normal and abnormal exits, and make medium-dog realtime remote control recover from `robot_roamerx` holding the motion requester.

## Plan

1. Navigation release should always try all cleanup channels:
   - `robot_alg_manager stop_nav` as a best-effort App request.
   - Direct `/start_navigation` STOP publish.
   - `/control_right/test=false` plus body UDP fallback.
2. Navigation background cleanup should also release control on timeout or early terminal/failure states, with a short grace period to avoid releasing immediately on old standby state before a new task is accepted.
3. Remote navigation loop scripts should run the same cleanup on `INT`, `TERM`, and unexpected script exit.
4. RobotSDK remote control should inspect `/robot_control_server/current_requester_info`; when `robot_roamerx` owns control, stop `robot_roamerx` before posture or realtime stream commands.
5. Update focused command-generation tests and run the navigation/control test slices.
