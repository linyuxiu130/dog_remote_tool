from __future__ import annotations

from dog_remote_tool.core.log_format import log_line
from dog_remote_tool.core.profiles import PRODUCTS, ProductProfile


class MainWindowProfilesMixin:
    def _ensure_page_profile(self, index: int) -> bool:
        spec = self.page_specs[index]
        required = spec.required_capability
        if not required:
            return False
        return self._ensure_capability_profile(required, spec.title, self.device_bar.current_profile())

    def _profile_changed_for_current_page(self, profile: ProductProfile) -> None:
        index = self.nav.currentRow()
        if not (0 <= index < len(self.page_specs)):
            return
        spec = self.page_specs[index]
        if spec.required_capability:
            self._ensure_capability_profile(spec.required_capability, spec.title, profile)
        self._apply_page_platform_restrictions(index)

    def _ensure_capability_profile(self, capability: str, title: str, profile: ProductProfile) -> bool:
        if capability in profile.capabilities:
            return False
        target_key = self._preferred_profile_key_for_capability(profile, capability)
        if not target_key:
            return False
        target = PRODUCTS[target_key]
        if self.device_bar.switch_profile_key(target_key):
            self._append_log(log_line("info", f"{title} 需要 {target.platform}，已切换到 {target.label}。"))
            return True
        return False

    def _preferred_profile_key_for_capability(self, profile: ProductProfile, capability: str) -> str:
        selection = getattr(self.device_bar.selector, "KEY_TO_SELECTION", {}).get(profile.key)
        combinations = getattr(self.device_bar.selector, "COMBINATIONS", {})
        if selection:
            family_key, _platform_key = selection
            family_target = combinations.get((family_key, "nx_s100"), "")
            if family_target and capability in PRODUCTS[family_target].capabilities:
                return family_target
        for key, candidate in PRODUCTS.items():
            if capability in candidate.capabilities:
                return key
        return ""

    def _apply_page_platform_restrictions(self, index: int) -> None:
        if not (0 <= index < len(self.page_specs)):
            self.device_bar.set_disabled_platform_keys(set())
            return
        spec = self.page_specs[index]
        if not spec.required_capability:
            self.device_bar.set_disabled_platform_keys(set())
            return
        self.device_bar.set_disabled_platform_keys(self._unsupported_platform_keys_for_current_family(spec.required_capability))

    def _unsupported_platform_keys_for_current_family(self, capability: str) -> set[str]:
        profile = self.device_bar.current_profile()
        selection = getattr(self.device_bar.selector, "KEY_TO_SELECTION", {}).get(profile.key)
        combinations = getattr(self.device_bar.selector, "COMBINATIONS", {})
        if not selection:
            return set()
        family_key, _platform_key = selection
        disabled: set[str] = set()
        for platform_key, _label in getattr(self.device_bar.selector, "PLATFORMS", ()):
            product_key = combinations.get((family_key, platform_key), "")
            if product_key and capability not in PRODUCTS[product_key].capabilities:
                disabled.add(platform_key)
        return disabled
