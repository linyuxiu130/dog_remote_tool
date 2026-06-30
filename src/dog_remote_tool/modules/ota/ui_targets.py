from __future__ import annotations

from dataclasses import dataclass

from dog_remote_tool.modules.ota.targets import TARGETS


L1_UI_TARGET_KEYS = (
    "xg_l1_point_3588",
    "xg_l1_wheel_3588",
    "xg_l1_point_nx",
    "xg_l1_wheel_nx",
    "zg3588",
    "zgnx",
)

PROFILE_TARGET_KEYS = {
    "xg3588": "xg3588",
    "xg1_nx": "xg_l1_point_nx",
    "zg3588": "zg3588",
    "zg_surround_3588": "zg3588",
    "zg_lidar_nx": "zgnx",
}

FLASH_PROFILE_TARGETS = {
    "xg2_3588": ("line_flash", ("s100_flash", "orin_flash")),
    "xg2_s100": ("s100_flash", ("s100_flash",)),
    "zg_surround_s100": ("s100_flash", ("s100_flash",)),
    "zg_lidar_nx": ("orin_flash", ("orin_flash",)),
}

PACKAGE_PROFILE_TARGET_KEYS = {
    ("zg_lidar_nx", "nx"): "zgnx",
}
SMALL_PACKAGE_TYPES = {"deb_deploy", "deb_package", "whl_package", "small_deploy_archive"}
SMALL_PACKAGE_PROFILE_TARGET_KEYS = {
    "zg_lidar_nx": "zgnx",
}


@dataclass(frozen=True)
class OtaUiTarget:
    key: str
    label: str
    family: str
    host: str
    user: str
    password: str
    remote_dir: str = "~/ota"
    operation: str = "ota"
    accepted_package_types: tuple[str, ...] = ()

    @property
    def is_flash(self) -> bool:
        return self.operation == "flash"


def default_remote_dir(target_key: str) -> str:
    if target_key == "zg3588":
        return "/userdata/upgrade"
    return "~/ota"


def ui_targets() -> list[OtaUiTarget]:
    return [
        OtaUiTarget(item.key, item.label, item.family, item.host, item.user, item.password, default_remote_dir(item.key))
        for item in (TARGETS[key] for key in L1_UI_TARGET_KEYS)
    ]


def _ota_target_from_profile(profile, target_key: str, *, family: str | None = None) -> OtaUiTarget:
    item = TARGETS[target_key]
    return OtaUiTarget(
        item.key,
        profile.label,
        family or item.family,
        profile.host,
        profile.user,
        profile.password,
        default_remote_dir(item.key),
    )


def target_for_profile(profile) -> OtaUiTarget | None:
    capabilities = getattr(profile, "capabilities", ())
    if "ota" in capabilities:
        target_key = PROFILE_TARGET_KEYS.get(profile.key)
        if target_key:
            return _ota_target_from_profile(profile, target_key)
    if "flash" in capabilities:
        family, accepted_types = FLASH_PROFILE_TARGETS.get(profile.key, ("line_flash", ("s100_flash", "orin_flash")))
        return OtaUiTarget(
            profile.key,
            profile.label,
            family,
            profile.host,
            profile.user,
            profile.password,
            "",
            "flash",
            accepted_types,
        )
    return None


def target_for_profile_package(profile, package_type: str) -> OtaUiTarget | None:
    if package_type in SMALL_PACKAGE_TYPES:
        target_key = SMALL_PACKAGE_PROFILE_TARGET_KEYS.get(profile.key)
        if target_key:
            return _ota_target_from_profile(profile, target_key, family="small_deploy")
    target_key = PACKAGE_PROFILE_TARGET_KEYS.get((profile.key, package_type))
    if target_key:
        return _ota_target_from_profile(profile, target_key)
    return target_for_profile(profile)
