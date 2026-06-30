# Alg Localization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make localization and navigation map preparation use the fast `robot_alg_manager` App WebSocket localization flow directly.

**Architecture:** Add a focused backend module for alg App localization commands and call it from the existing localization and navigation runtimes. Keep UI actions unchanged; `start_localization_command()`, `test_localization_once_command()`, and navigation map preparation continue to be the public entrypoints.

**Tech Stack:** Python, PyQt command builders, ROS 2 Humble remote shell, pytest.

---

### Task 1: Backend Alg Localization Command

**Files:**
- Create: `src/dog_remote_tool/modules/localization/alg.py`
- Modify: `src/dog_remote_tool/modules/localization/__init__.py`
- Test: `tests/test_map_helpers.py`

- [x] Add `alg_localization_load_inner(profile, map_pcd_path, timeout_seconds)` that validates `map.pcd` and `map.yaml`, derives the map ID from the path, connects to `robot_alg_manager:10010`, sends `loc_load_map`, polls `get_loc_status`, and exits nonzero on failed or timed out localization.
- [x] Export the helper through `dog_remote_tool.modules.localization`.
- [x] Add assertions that the generated command contains `loc_load_map`, `get_loc_status`, `ContinuousLoc`, map ID derivation, and does not start `robot_localization`.

### Task 2: Runtime Integration

**Files:**
- Modify: `src/dog_remote_tool/modules/localization/runtime.py`
- Test: `tests/test_map_helpers.py`

- [x] Update `start_localization_command()` to call the alg helper first, then start pose recording and the current pose bridge after alg localization succeeds.
- [x] Update `test_localization_once_command()` to use the alg helper before polling final pose and reporting success.
- [x] Initially kept the existing service-based startup/load flow available as a fallback function in the same runtime module.

### Task 3: Verification

**Files:**
- Test: `tests/test_map_helpers.py`
- Test: `tests/test_navigation.py`

- [x] Run `PYTHONPATH=src python3 -m pytest tests/test_map_helpers.py tests/test_navigation.py -q`.
- [x] Run a smoke command build for `zg_lidar_nx` and verify the command contains `loc_load_map` and the expected map ID.
- [x] Confirm no UI page method names changed.

### Task 4: Navigation Auto-Localization

**Files:**
- Modify: `src/dog_remote_tool/modules/navigation/map_localization.py`
- Test: `tests/test_navigation.py`

- [x] Initially made `load_localization_map_once_inner()` use `localization.alg.alg_localization_load_inner()` before the existing `/load_map_service` and `/robot_slam/localization_state_service` fallback.
- [x] Keep the current `MAP_PREP_LOCALIZATION_READY=1` and `MAP_PREP_MAP_PCD=...` outputs so the navigation page does not need UI changes.
- [x] Add assertions that navigation map load commands contain `loc_load_map`, `get_loc_status`, and only reach `LoadMap` after the alg attempt.

### Task 5: Remove Redundant Fallback Paths

**Files:**
- Modify: `src/dog_remote_tool/modules/localization/runtime.py`
- Modify: `src/dog_remote_tool/modules/navigation/map_localization.py`
- Test: `tests/test_map_helpers.py`
- Test: `tests/test_navigation.py`

- [x] Remove the runtime alg-to-legacy wrapper so `start_localization_command()` and `test_localization_once_command()` fail directly when alg localization fails.
- [x] Remove navigation's LoadMap, stale SLAM cleanup, and `/robot_slam/localization_state_service` fallback from map preparation.
- [x] Keep `MAP_PREP_LOCALIZATION_READY=1` and `MAP_PREP_MAP_PCD=...` outputs after alg success.
- [x] Update tests to assert that generated commands include `loc_load_map`/`get_loc_status` and do not include legacy fallback strings.
- [x] Run local pytest plus remote smoke tests for both navigation map preparation and start localization.
