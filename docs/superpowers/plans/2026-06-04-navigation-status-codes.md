# Navigation Status Codes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Show the current remote navigation status codes in the Navigation page, including tasks started outside Dog Remote Tool.

**Architecture:** Keep the existing `/navigation_state` polling path. Extend the remote probe to expose current task metadata, add a formatter in `navigation_status.py`, and render the formatted status code summary below the Navigation status cards.

**Tech Stack:** Python, PyQt5, ROS 2 shell probes, pytest.

---

### Task 1: Probe And Formatting

**Files:**
- Modify: `src/dog_remote_tool/modules/navigation_probe.py`
- Modify: `src/dog_remote_tool/modules/navigation_status.py`
- Test: `tests/test_navigation.py`

- [x] Add probe output for `NAV_CURRENT_TASK_IDX`, `NAV_DISTANCE_FROM_START`, `NAV_ESTIMATED_DISTANCE_REMAINING`, and `NAV_ESTIMATED_TIME_REMAINING_SEC`.
- [x] Add `navigation_code_summary(values)` that formats raw codes like `state=100 ACTIVE / 执行中`.
- [x] Add tests for active remote navigation status and missing `/navigation_state`.

### Task 2: Navigation UI

**Files:**
- Modify: `src/dog_remote_tool/ui/pages/navigation_page.py`
- Test: `tests/test_navigation.py`

- [x] Add `self.nav_code_detail` below the status cards with restrained styling.
- [x] Update `set_cards_from_values()` to keep this label synchronized from `navigation_code_summary`.
- [x] Add fake-page coverage so remote active values appear in the UI.

### Task 3: Verification

- [x] Run `PYTHONPATH=src pytest tests/test_navigation.py -q`.
- [x] Run `PYTHONPATH=src pytest tests/test_map_helpers.py -q`.
- [x] Run `PYTHONPATH=src python3 -m py_compile $(find src tests -name '*.py')`.
- [x] Run `QT_QPA_PLATFORM=offscreen PYTHONPATH=src python3 tests/smoke_main_window.py`.
