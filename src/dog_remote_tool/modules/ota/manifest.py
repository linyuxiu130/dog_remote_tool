from __future__ import annotations

from pathlib import Path

from dog_remote_tool.modules.ota.package_utils import human_bytes, is_zip
from dog_remote_tool.modules.ota.types import OtaFirmwareCoverage, OtaFirmwareModule, OtaPackageManifest


ZG3588_FULL_ZIP_MODULES = frozenset(
    {
        "imu",
        "actuator_joint",
        "actuator_wheel",
        "uart2can",
        "hot_swap",
        "power_control",
        "battery",
    }
)

XG3588_KNOWN_TAR_MODULES = frozenset(
    {
        "imu_board",
        "power_board",
        "spline",
    }
)

XG3588_FACTORY_BUNDLED_NON_OTA_MODULES = frozenset(
    {
        "charge_board",
        "battery",
    }
)


def is_zg3588_full_zip_manifest(manifest: OtaPackageManifest) -> bool:
    module_names = {module.name for module in manifest.modules}
    return ZG3588_FULL_ZIP_MODULES.issubset(module_names) and all(module.runnable for module in manifest.modules)


def manifest_summary(manifest: OtaPackageManifest) -> str:
    if manifest.family == "nx":
        if manifest.modules:
            runnable_count = manifest.runnable_module_count
            if runnable_count == len(manifest.modules):
                module_text = f"；{len(manifest.modules)} 个固件模块均带工具"
            elif runnable_count:
                module_text = f"；{len(manifest.modules)} 个固件模块，{runnable_count} 个带工具"
            else:
                module_text = f"；{len(manifest.modules)} 个固件模块，未随包提供刷写工具"
        else:
            module_text = ""
        return f"NX 系统包: {manifest.system_image}；ota_package.tar ({human_bytes(manifest.system_size)}){module_text}"
    module_count = len(manifest.modules)
    runnable_count = manifest.runnable_module_count
    if module_count == 0:
        return f"3588 系统镜像: {manifest.system_image} ({human_bytes(manifest.system_size)})"
    if runnable_count == module_count:
        module_text = f"{module_count} 个固件模块均带工具"
    elif runnable_count:
        module_text = f"{module_count} 个固件模块，{runnable_count} 个带工具"
    elif manifest.package.lower().endswith((".tar.gz", ".tgz")):
        module_text = f"{module_count} 个固件模块，依赖远端 mcu_upgrade 刷写"
    else:
        module_text = f"{module_count} 个固件模块，未随包提供刷写工具"
    if is_zg3588_full_zip_manifest(manifest):
        module_text += "；中狗 3588 全量固件齐全，已按 ZsmFactory v0.2.2 参数接入"
    return f"3588 系统镜像: {manifest.system_image} ({human_bytes(manifest.system_size)})；{module_text}"


def rk3588_firmware_coverage(package: Path, manifest: OtaPackageManifest) -> OtaFirmwareCoverage:
    if manifest.family != "rk3588" or not manifest.modules:
        return OtaFirmwareCoverage()
    if is_zip(package):
        if is_zg3588_full_zip_manifest(manifest):
            return OtaFirmwareCoverage(
                supported=manifest.modules,
                note=(
                    "中狗 3588 ZIP 包已包含系统镜像、7 个固件模块和随包工具；"
                    "ZsmFactory v0.2.2 反编译流程已确认 imu、actuator_joint、actuator_wheel、uart2can、hot_swap、power_control、battery 的刷写参数；"
                    "battery 按上位机流程分别刷写 battery[1] 和 battery[2]"
                ),
            )
        return OtaFirmwareCoverage(
            unsupported=manifest.modules,
            note="ZIP 包随包工具已可识别，但工具参数尚未接入自动执行",
        )

    supported: list[OtaFirmwareModule] = []
    unsupported: list[OtaFirmwareModule] = []
    for module in manifest.modules:
        name = module.name.lower()
        firmware = Path(module.firmware).name.lower()
        if name == "spline" or firmware.startswith("spline_release_"):
            supported.append(module)
        elif name.startswith("motorcontrol") or firmware.startswith("motorcontrol_"):
            supported.append(module)
        elif name == "imu_board" or firmware.startswith("imu_board_release_"):
            supported.append(module)
        elif name == "power_board" or firmware.startswith("power_board_release_"):
            supported.append(module)
        elif name in XG3588_FACTORY_BUNDLED_NON_OTA_MODULES:
            continue
        else:
            unsupported.append(module)
    known_note = (
        "小狗 3588 tar 包依赖远端 /usr/local/bin/mcu_upgrade；"
        "AgibotD1 v0.8.4 jupdate 反编译流程已确认 spline、motorcontrol、imu_board、power_board 的刷写参数，"
        "并已接入 SOC 预检和 /dev/ttyS3 -r 5 电池板重启；"
        "charge_board 与 battery 固件随产线包放置，常规 3588 OTA 不执行"
    )
    return OtaFirmwareCoverage(
        tuple(supported),
        tuple(unsupported),
        known_note,
    )
