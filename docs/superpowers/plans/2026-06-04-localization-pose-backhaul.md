# Localization Pose Backhaul Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make single localization show one pose on the map after success, add an operator-controlled pose backhaul switch, keep continuous localization lightweight, and preserve localization page state across page switches.

**Architecture:** Keep remote localization start/stop behavior unchanged. Add UI state for pose backhaul, parse pulled pose records locally, and apply the final single-test pose once. Continuous localization continues to use local preview overlays from pose stream/pose polling and does not save success map artifacts on stop.

**Tech Stack:** PyQt5, `ProcessSlot`, existing localization modules, pytest.

---

### Task 1: Pose Backhaul State And UI

**Files:**
- Modify: `src/dog_remote_tool/ui/pages/localization_page.py`
- Test: `tests/test_map_helpers.py`

- [x] **Step 1: Add `QCheckBox` import and a checked `self.pose_backhaul_toggle` in the localization action panel.**
- [x] **Step 2: Add `pose_backhaul_enabled()` helper and use it in single and continuous localization start paths.**
- [x] **Step 3: Add tests proving backhaul disabled passes `record_pose=False` and does not set pending pull.**

### Task 2: Single Localization Pose Application

**Files:**
- Modify: `src/dog_remote_tool/ui/pages/localization_page.py`
- Test: `tests/test_map_helpers.py`

- [x] **Step 1: Add a parser for the last valid `x,y,z` line in a pulled pose record.**
- [x] **Step 2: Add `apply_single_pose_record_if_pending(local_file)` that updates `loc_pose`, appends one track point, redraws once, then clears the pending flag.**
- [x] **Step 3: Call that helper only after `pose_record_finished(... action='pull')`.**
- [x] **Step 4: Add tests proving one pull updates the map once and a second pull does not update again.**

### Task 3: Continuous Localization Performance And Page Switch State

**Files:**
- Modify: `src/dog_remote_tool/ui/pages/localization_page.py`
- Test: `tests/test_map_helpers.py`

- [x] **Step 1: Remove automatic success image/route saving from continuous stop. The preview map keeps the in-memory trajectory overlay.**
- [x] **Step 2: Let `on_localization_runner_finished` preserve status even if the page is inactive; defer pose-record pull until the page is active again.**
- [x] **Step 3: On activation, restart UI polling/stream for continuous localization and run deferred pose-record pull if requested.**
- [x] **Step 4: Add tests for inactive task completion preserving success state and deferring pull.**

### Task 4: Verification

**Files:**
- Test: `tests/test_map_helpers.py`
- Test: `tests/smoke_main_window.py`

- [x] **Step 1: Run `PYTHONPATH=src pytest tests/test_map_helpers.py -q`.**
- [x] **Step 2: Run `PYTHONPATH=src pytest tests/test_navigation.py -q` to catch map drawing regressions nearby.**
- [x] **Step 3: Run `PYTHONPATH=src python3 -m py_compile $(find src tests -name '*.py')`.**
- [x] **Step 4: Run `QT_QPA_PLATFORM=offscreen PYTHONPATH=src python3 tests/smoke_main_window.py`.**
