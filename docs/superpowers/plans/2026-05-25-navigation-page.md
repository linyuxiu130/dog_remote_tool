# Navigation Page Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a production-ready “导航” page to Dog Remote Tool that mirrors the Mapping page visual language and drives the remote navigation flow by map, localization, navigation lifecycle, and navigation task status codes.

**Architecture:** Add a backend command builder module `dog_remote_tool.modules.navigation` for all remote ROS/SSH behavior and a PyQt page `dog_remote_tool.ui.pages.navigation_page` for UI/state orchestration. Reuse mapping/localization defaults and map-list helpers so device paths remain profile-driven instead of hardcoded in UI.

**Tech Stack:** Python 3, PyQt5, ROS 2 Humble shell commands over SSH, existing `CommandSpec`/`ProcessRunner` infrastructure.

---

### Task 1: Backend Navigation Commands

**Files:**
- Create: `src/dog_remote_tool/modules/navigation.py`
- Test: `tests/test_navigation.py`

- [ ] Add `navigation.py` with helpers for status interpretation, status probing, map loading, goal sending, cancel/stop, and package inspection.
- [ ] Add unit tests for status code mapping, command construction, and profile capability behavior.

### Task 2: Navigation UI Page

**Files:**
- Create: `src/dog_remote_tool/ui/pages/navigation_page.py`
- Modify: `src/dog_remote_tool/ui/main_window.py`
- Modify: `src/dog_remote_tool/core/profiles.py`

- [ ] Build a “导航” page using the Mapping page card/status visual style.
- [ ] Include map selector, status cards, precheck/load-map/start/cancel/stop buttons, goal x/y/yaw/speed/tolerance inputs, and a compact status explanation area.
- [ ] Register the page after “定位”.
- [ ] Add `navigation` capability to NX/S100/ZG algorithm targets.

### Task 3: Verification

**Files:**
- Compile and smoke test existing app.

- [ ] Run `python3 -m compileall src tests`.
- [ ] Run targeted `pytest tests/test_navigation.py tests/smoke_main_window.py`.
- [ ] Run an offscreen import/create smoke if needed to confirm the page registers.
