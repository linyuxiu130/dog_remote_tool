# Navigation Dispatch Cancel Optimization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make Dog Remote Tool navigation dispatch distinguish command acceptance from final result, avoid premature stop on route-network multi-task progress, and make cancel faster.

**Architecture:** Keep the existing shell-command generation pattern. Tighten state parsing in `helper_control.py`, speed route start readiness in `map_commands.py`, and shorten stop confirmation in `control_commands.py`; update focused assertions in `tests/test_navigation.py`.

**Tech Stack:** Python 3, PyQt UI command runner, ROS 2 Humble shell commands, pytest.

---

### Task 1: Prevent Premature Auto Stop

**Files:**
- Modify: `src/dog_remote_tool/modules/navigation/helper_control.py`
- Test: `tests/test_navigation.py`

- [ ] Parse the full `/navigation_state.task_status_list` in `_release_navigation_control_when_done_inner`.
- [ ] Treat `state=200` as releasable only when every listed task is terminal, or when no tasks remain after an active state.
- [ ] Keep blocking/recovery active states under observation instead of sending `stop_nav`.

### Task 2: Speed Route Start Handshake

**Files:**
- Modify: `src/dog_remote_tool/modules/navigation/map_commands.py`
- Modify: `src/dog_remote_tool/modules/navigation/goal_commands.py`
- Test: `tests/test_navigation.py`

- [ ] Let route initialization continue after `SUCCEEDED(200)` when no task is active.
- [ ] Reduce route init settle time while preserving failure checks.
- [ ] Keep START acceptance separate from final navigation success.

### Task 3: Fast Cancel Path

**Files:**
- Modify: `src/dog_remote_tool/modules/navigation/helper_control.py`
- Modify: `src/dog_remote_tool/modules/navigation/control_commands.py`
- Test: `tests/test_navigation.py`

- [ ] Add configurable release timeouts for stop.
- [ ] Use shorter stop confirmation polling.
- [ ] Preserve final UI refresh and plan-layer cleanup.

### Task 4: Verification

**Commands:**
- `PYTHONPATH=src pytest tests/test_navigation.py -q`
- `PYTHONPATH=src python3 -m py_compile src/dog_remote_tool/modules/navigation/helper_control.py src/dog_remote_tool/modules/navigation/map_commands.py src/dog_remote_tool/modules/navigation/goal_commands.py src/dog_remote_tool/modules/navigation/control_commands.py`
- Remote self-test: generate a stop command against `zg_lidar_nx`, run it, then read `/navigation_state` and recent `robot_alg_manager.log` to confirm fast stop/standby behavior.
