from __future__ import annotations

from pathlib import Path

import dog_remote_tool.modules.ota.backend_runner as _runner
import dog_remote_tool.modules.ota.manifest as _ota_manifest
from dog_remote_tool.modules.ota.inspect import inspect_tools_package
from dog_remote_tool.modules.ota.manifest_reader import package_manifest
from dog_remote_tool.modules.ota.package_classifier import package_motion
from dog_remote_tool.modules.ota.package_utils import human_bytes, is_zip, motion_label, target_motion
from dog_remote_tool.modules.ota.targets import OtaTarget


def validate_local_inputs(target: OtaTarget, package: Path, tools: Path | None):
    _runner.log(f"[local] 升级包: {package}")
    _runner.log(f"[local] 升级包大小: {human_bytes(package.stat().st_size)}")
    try:
        manifest = package_manifest(package)
        _runner.log(f"[local] 包清单: {_ota_manifest.manifest_summary(manifest)}")
        if target.family == "nx":
            payload_size = manifest.system_size
            _runner.log(f"[local] 包内 ota_package.tar: {human_bytes(payload_size)}")
            for module in manifest.modules:
                status = "随包带工具" if module.runnable else "缺少随包工具"
                detail = f"{module.name}: {module.firmware}"
                if module.tool:
                    detail += f" tool={module.tool}"
                _runner.log(f"[local] 固件模块({status}): {detail}")
            if is_zip(package) and any(module.name == "rtk_mcu" for module in manifest.modules) and target.key != "zgnx":
                _runner.die("该 ZIP 是中狗 NX 全量包，只允许在中狗 NX 目标下执行。")
            assert tools is not None
            inspect_tools_package(tools)
            _runner.log(f"[local] OTA 工具包: {tools}")
            _runner.log(f"[local] 工具包大小: {human_bytes(tools.stat().st_size)}")
        else:
            img, size = manifest.system_image, manifest.system_size
            _runner.log(f"[local] RKFW 镜像: {img} ({human_bytes(size)})")
            for module in manifest.modules:
                detail = f"{module.name}: {module.firmware}"
                if module.version:
                    detail += f" v{module.version}"
                if module.tool:
                    detail += f" tool={module.tool}"
                if is_zip(package):
                    status = "随包带工具" if module.runnable else "缺少随包工具"
                    _runner.log(f"[local] 固件模块({status}): {detail}")
                else:
                    _runner.log(f"[local] 固件模块: {detail}")
            if manifest.modules:
                if _ota_manifest.is_zg3588_full_zip_manifest(manifest) and target.key != "zg3588":
                    _runner.die("该 ZIP 是中狗 3588 全量包，只允许在中狗 3588 目标下执行。")
                coverage = _ota_manifest.rk3588_firmware_coverage(package, manifest)
                if coverage.supported:
                    supported_names = ", ".join(module.name for module in coverage.supported)
                    _runner.log(f"[local] 已掌握刷写参数的固件: {supported_names}")
                if coverage.unsupported:
                    unsupported_names = ", ".join(module.name for module in coverage.unsupported)
                    if coverage.note:
                        _runner.log(f"[local] 固件覆盖说明: {coverage.note}")
                    _runner.die(
                        "3588 包包含工具尚未覆盖的固件模块，不能执行默认全量刷写: "
                        f"{unsupported_names}。请补齐这些固件的官方刷写命令/工具后再刷。"
                    )
            expected_motion = target_motion(target.key)
            if expected_motion:
                actual_motion = package_motion(package)
                if not actual_motion:
                    _runner.log("[WARN] 未识别 3588 点足/轮足")
                elif actual_motion != expected_motion:
                    _runner.die(
                        "3588 点足/轮足包不匹配: "
                        f"目标 {motion_label(expected_motion)} / 包内 {motion_label(actual_motion)}。"
                        "请确认 606 为点足包、626 为轮足包。"
                    )
                else:
                    _runner.log(f"[local] 3588 包形态: {motion_label(actual_motion)}")
        return manifest
    except ValueError as exc:
        _runner.die(str(exc))
