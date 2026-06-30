from __future__ import annotations

import os
import sys

from dog_remote_tool.core.shell import CommandSpec
from dog_remote_tool.modules.ota import commands as ota_commands
from dog_remote_tool.modules.ota import flash as ota_flash
from dog_remote_tool.modules.ota import package_display as _package_display
import dog_remote_tool.modules.ota.ui_targets as _ui_targets


L1_UI_TARGET_KEYS = _ui_targets.L1_UI_TARGET_KEYS
PROFILE_TARGET_KEYS = _ui_targets.PROFILE_TARGET_KEYS
FLASH_PROFILE_TARGETS = _ui_targets.FLASH_PROFILE_TARGETS
OtaUiTarget = _ui_targets.OtaUiTarget
default_remote_dir = _ui_targets.default_remote_dir
ui_targets = _ui_targets.ui_targets
target_for_profile = _ui_targets.target_for_profile
target_for_profile_package = _ui_targets.target_for_profile_package


def backend_python() -> str:
    return os.environ.get("DOG_REMOTE_TOOL_PYTHON") or sys.executable or "python3"


target_motion = _package_display.target_motion
latest_local = _package_display.latest_local
latest_package = _package_display.latest_package
package_type = _package_display.package_type
package_type_hint = _package_display.package_type_hint
package_light_summary = _package_display.package_light_summary
package_motion_type = _package_display.package_motion_type
package_summary = _package_display.package_summary
package_firmware_summary = _package_display.package_firmware_summary
package_detail_rows = _package_display.package_detail_rows
package_selection_detail_rows = _package_display.package_selection_detail_rows
MCU_DISPLAY_SLOTS = _package_display.MCU_DISPLAY_SLOTS
mcu_display_slots = _package_display.mcu_display_slots
mcu_slot_for_name = _package_display.mcu_slot_for_name
package_mcu_target_versions = _package_display.package_mcu_target_versions
_ui_package_manifest = _package_display._ui_package_manifest
_cached_ui_package_manifest = _package_display._cached_ui_package_manifest
package_manifest = _package_display.package_manifest
human_bytes = _package_display.human_bytes
package_release_name = _package_display.package_release_name
_package_release_name = _package_display.package_release_name
_firmware_version_from_name = _package_display._firmware_version_from_name
package_version = _package_display.package_version
default_tools_path = _package_display.default_tools_path
flash_type_label = _package_display.flash_type_label


def flash_precheck_command(target: OtaUiTarget, package: str) -> CommandSpec:
    flash_target = ota_flash.FlashTarget(
        target.key,
        target.label,
        target.family,
        target.accepted_package_types,
        target.host,
        target.user,
        target.password,
    )
    return ota_flash.flash_precheck_command(flash_target, package)


def s100_entry_monitor_command(target: OtaUiTarget) -> CommandSpec:
    flash_target = ota_flash.FlashTarget(
        target.key,
        target.label,
        target.family,
        target.accepted_package_types,
        target.host,
        target.user,
        target.password,
    )
    return ota_flash.s100_entry_monitor_command(flash_target)


def flash_upgrade_command(target: OtaUiTarget, package: str) -> CommandSpec:
    flash_target = ota_flash.FlashTarget(
        target.key,
        target.label,
        target.family,
        target.accepted_package_types,
        target.host,
        target.user,
        target.password,
    )
    return ota_flash.flash_upgrade_command(flash_target, package)


def masked_command(command: str, password: str) -> str:
    return ota_commands.masked_command(command, password)


def device_info_command(target: str, host: str, user: str, password: str, remote_dir: str) -> CommandSpec:
    return ota_commands.device_info_command(backend_python, target, host, user, password, remote_dir)


def mcu_maintenance_info_command(target: str, host: str, user: str, password: str, remote_dir: str) -> CommandSpec:
    return ota_commands.mcu_maintenance_info_command(backend_python, target, host, user, password, remote_dir)


def verify_command(target: str, host: str, user: str, password: str, remote_dir: str) -> CommandSpec:
    return ota_commands.verify_command(backend_python, target, host, user, password, remote_dir)


def precheck_command(
    target: str,
    host: str,
    user: str,
    password: str,
    remote_dir: str,
    package: str,
    tools: str,
) -> CommandSpec:
    return ota_commands.precheck_command(backend_python, target, host, user, password, remote_dir, package, tools)


def small_precheck_command(
    target: str,
    host: str,
    user: str,
    password: str,
    remote_dir: str,
    package: str,
) -> CommandSpec:
    return ota_commands.small_precheck_command(backend_python, target, host, user, password, remote_dir, package)


def prepare_command(
    target: str,
    host: str,
    user: str,
    password: str,
    remote_dir: str,
    package: str,
    tools: str,
) -> CommandSpec:
    return ota_commands.prepare_command(backend_python, target, host, user, password, remote_dir, package, tools)


def upgrade_command(
    target: str,
    host: str,
    user: str,
    password: str,
    remote_dir: str,
    package: str,
    tools: str,
    skip_mcu: bool = False,
) -> CommandSpec:
    return ota_commands.upgrade_command(backend_python, target, host, user, password, remote_dir, package, tools, skip_mcu)


def small_deploy_command(
    target: str,
    host: str,
    user: str,
    password: str,
    remote_dir: str,
    package: str,
) -> CommandSpec:
    return ota_commands.small_deploy_command(backend_python, target, host, user, password, remote_dir, package)
