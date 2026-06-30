# Navigation Flow Fast Path Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reduce redundant localization, route graph, and navigation dispatch work while preserving real success/failure checks.

**Architecture:** Keep confirmed robot APIs: alg App WebSocket for localization/reset/status and `/start_navigation` for navigation tasks. Add only safe caches with remote-state guards: localization cache requires current `ContinuousLoc` and matching tool marker; route graph cache requires matching route file stat and unchanged nav container pid.

**Tech Stack:** Python command builders, shell snippets over SSH, ROS 2 Humble topics/services, pytest command-generation tests.

---

### Task 1: Localization Cache

**Files:**
- Modify: `src/dog_remote_tool/modules/localization/alg.py`
- Test: `tests/test_map_helpers.py`

- [x] **Step 1: Add command-generation assertions**

Assert generated localization command contains `DOG_REMOTE_LOC_MAP_MARKER`, `ContinuousLoc`, and skips `loc_load_map` when map marker matches current continuous localization.

- [x] **Step 2: Implement marker guard**

Before `loc_load_map`, read `/tmp/dog_remote_localization_map_id`; when it equals requested map id and `get_loc_status` is continuous, return immediately. After successful continuous localization, write the marker.

- [x] **Step 3: Verify**

Run: `PYTHONPATH=src pytest tests/test_map_helpers.py -q -k 'localization_alg_load_inner or localization_runtime_uses_alg or localization_once_command_uses_alg'`

### Task 2: Route Graph Cache

**Files:**
- Modify: `src/dog_remote_tool/modules/navigation/map_commands.py`
- Test: `tests/test_navigation.py`

- [x] **Step 1: Add command-generation assertions**

Assert route goal command contains `DOG_REMOTE_ROUTE_GRAPH_CACHE`, route file `stat -c`, nav container pid, and a cache-hit message.

- [x] **Step 2: Implement guarded cache**

In `_update_route_graph_inner`, compute route file stat and nav container pid. If both match the cache file, skip `/RouteGraphPlanner/update_graph`; otherwise update graph and write the cache.

- [x] **Step 3: Verify**

Run: `PYTHONPATH=src pytest tests/test_navigation.py -q -k 'route_goal or zg_lidar_route_navigation or initializes_route_map or start_route_goal'`

### Task 3: Multi/Track Fast Dispatch

**Files:**
- Modify: `src/dog_remote_tool/modules/navigation/goal_commands.py`
- Test: `tests/test_navigation.py`

- [x] **Step 1: Add command-generation assertions**

Assert multi-point/cruise/track commands publish task before `data: true` and no longer include `NAV_START_DEADLINE`.

- [x] **Step 2: Remove duplicate pre-start mode and synchronous active wait**

For non-loop multi-point, cruise, and reference-line-file commands, remove `_pre_start_navigation_mode_inner()` and `_wait_navigation_active_after_start_inner()`, matching point/route dispatch.

- [x] **Step 3: Verify**

Run: `PYTHONPATH=src pytest tests/test_navigation.py -q -k 'reference_line_command or reference_line_file_command or start_goal_command'`

### Task 4: Remote Smoke

**Files:**
- No source changes.

- [x] **Step 1: Run local checks**

Run py_compile for touched modules and focused pytest groups.

- [x] **Step 2: Run remote non-motion checks**

Use existing map `2026_06_16_18_25_22` to verify localization cache second run is fast and safe. Generate route command structure to verify no body bridge and graph cache guard exists.
