from __future__ import annotations

from pathlib import Path

from dog_remote_tool.core.paths import app_root, resource_path

PLATFORM_TOOLS_BIN = Path("platform-tools") / "linux-x86_64" / "bin"
XBURN_BIN = Path("xburn") / "linux-x86_64" / "bin"


def tool_root() -> Path:
    return app_root()


def bundled_fastboot_path() -> Path:
    return resource_path(*PLATFORM_TOOLS_BIN.parts, "fastboot")


def bundled_dfu_util_path() -> Path:
    return resource_path(*PLATFORM_TOOLS_BIN.parts, "dfu-util")


def bundled_xburn_path() -> Path:
    return resource_path(*XBURN_BIN.parts, "xburn")
