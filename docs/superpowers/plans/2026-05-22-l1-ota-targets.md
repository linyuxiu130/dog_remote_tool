# L1 OTA Targets Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fold the standalone small-dog L1 3588/NX OTA target semantics into Dog Remote Tool's OTA page.

**Architecture:** Keep the existing Python OTA backend as the single execution path. Add explicit UI/backend target keys for small-dog L1 point-foot and wheel-foot variants while reusing the two real upgrade families: RK3588 uses `updateEngine`, NX uses `nv_ota_start.sh`.

**Tech Stack:** Python 3, PyQt5, `sshpass`, `rsync`/`scp`, remote shell commands.

---

### Task 1: Add L1 OTA Targets

**Files:**
- Modify: `src/dog_remote_tool/modules/ota_backend.py`
- Modify: `src/dog_remote_tool/modules/ota.py`

- [x] Add backend target keys for `xg_l1_point_3588`, `xg_l1_wheel_3588`, `xg_l1_point_nx`, and `xg_l1_wheel_nx`.
- [x] Keep legacy aliases `xg3588`, `nx`, and `zgnx` available for commands.
- [x] Make the OTA UI list only the small-dog L1 targets by default.
- [x] Verify with:

```bash
PYTHONPATH=src python3 -m dog_remote_tool.modules.ota_backend --help
PYTHONPATH=src python3 - <<'PY'
from dog_remote_tool.modules import ota
print([target.key for target in ota.ui_targets()])
PY
```

### Task 2: Improve OTA UI Guidance

**Files:**
- Modify: `src/dog_remote_tool/ui/main_window.py`

- [x] Update OTA package info text to show the selected target's platform family and endpoint.
- [x] Keep validation strict on package family (`rk3588` vs `nx`) and explicit that point-foot/wheel-foot is selected by target, not inferred from package bytes.
- [x] Verify by constructing `OtaPage` offscreen and checking target labels.

### Task 3: Verify

**Files:**
- No new files.

- [x] Run Python compile checks:

```bash
python3 -m py_compile src/dog_remote_tool/modules/ota_backend.py src/dog_remote_tool/modules/ota.py src/dog_remote_tool/ui/main_window.py
python3 -m compileall -q src/dog_remote_tool
```

- [x] Run command-generation checks for a 3588 and NX target and confirm the expected family and script path are used.
