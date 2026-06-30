from __future__ import annotations

import re
from pathlib import Path

from PyQt5.QtCore import QTimer
from PyQt5.QtWidgets import QFileDialog

from dog_remote_tool.core.runner import ProcessRunner
from dog_remote_tool.modules import ota
from dog_remote_tool.modules.ota import package_locator as ota_package_locator
from dog_remote_tool.ui.components import CommandPage, DeviceBar
from dog_remote_tool.ui.pages.ota.actions import OtaActionsMixin
from dog_remote_tool.ui.pages.ota.device_info import OtaDeviceInfoMixin
from dog_remote_tool.ui.pages.ota.layout import OtaLayoutMixin
from dog_remote_tool.ui.process_utils import ProcessSlot
from dog_remote_tool.ui.widget_roles import set_widget_text_tooltip


FLASH_PROGRESS_PATTERN = re.compile(r"(?:Board\s+\d+\s+burn\s+progress|burn\s+progress)\s+([0-9]+(?:\.[0-9]+)?)%")
SPARSE_PROGRESS_PATTERN = re.compile(r"Sending sparse '[^']+'\s+(\d+)/(\d+)")

# Tests and action mixins patch this symbol through dog_remote_tool.ui.pages.ota.page.
_OTA_PAGE_MONKEYPATCH_EXPORTS = (QTimer,)


def parse_flash_progress(text: str) -> float | None:
    matches = FLASH_PROGRESS_PATTERN.findall(text)
    if matches:
        return float(matches[-1])
    sparse_matches = SPARSE_PROGRESS_PATTERN.findall(text)
    if sparse_matches:
        done, total = sparse_matches[-1]
        total_value = int(total)
        if total_value > 0:
            return 26.0 + (int(done) / total_value) * 59.0
    return None


class OtaPage(OtaLayoutMixin, OtaActionsMixin, CommandPage, OtaDeviceInfoMixin):
    def __init__(self, runner: ProcessRunner, device_bar: DeviceBar) -> None:
        super().__init__("OTA / 线刷", runner, device_bar)
        self.page_active = False
        self.device_info_slot = ProcessSlot(self, reserve_runner=False)
        self.motion_warning_ack: set[tuple[str, str, str, str]] = set()
        self.body.addWidget(self._build_ota_workbench())
        self.device_bar.profile_changed.connect(self._profile_changed)
        for edit in (self.device_bar.host, self.device_bar.user, self.device_bar.password):
            edit.textChanged.connect(lambda _text: self.apply_target_defaults(refresh=False, stop_current_read=True))
        self.runner.state_changed.connect(lambda _running: self.refresh_page_stop_button())
        self.runner.task_status_changed.connect(self.refresh_page_stop_button)
        self.refresh_page_stop_button()
        self.apply_target_defaults()

    def refresh_page_stop_button(self) -> None:
        running = self.runner.is_running()
        if self.runner.stop_locked:
            self.stop_task_btn.setEnabled(False)
            set_widget_text_tooltip(self.stop_task_btn, "刷机锁定", "已进入正式刷写阶段，本地停止已锁定。")
        elif running:
            self.stop_task_btn.setEnabled(True)
            set_widget_text_tooltip(self.stop_task_btn, "停止任务", "停止当前本地执行任务；进入正式刷写阶段后会锁定。")
        else:
            self.stop_task_btn.setEnabled(False)
            set_widget_text_tooltip(self.stop_task_btn, "无运行任务", "当前没有正在运行的任务。")

    def current_ota_target(self):
        package_type = ota.package_type_hint(self.package.text().strip()) if hasattr(self, "package") else ""
        return ota.target_for_profile_package(self.profile(), package_type)

    def _package_changed(self, _text: str = "") -> None:
        self.apply_target_defaults(refresh=False, stop_current_read=True)

    def _profile_changed(self, _profile) -> None:
        self.apply_target_defaults(stop_current_read=True)

    def apply_target_defaults(self, refresh: bool = True, stop_current_read: bool = False) -> None:
        if stop_current_read:
            self._stop_device_info_process()
        target = self.current_ota_target()
        supported = target is not None
        is_flash = bool(target and target.is_flash)
        self.upgrade_btn.setEnabled(supported)
        self.precheck_btn.setEnabled(supported)
        self.browse_pkg.setEnabled(supported)
        self.browse_dir.setEnabled(supported)
        self.entry_btn.setEnabled(bool(target and target.family == "s100_flash" and target.is_flash))
        self.refresh_btn.setEnabled(supported and not is_flash)
        self.mcu_read_btn.setEnabled(self._mcu_supported_for_target(target))
        self.nx_mcu_check.setVisible(self._nx_mcu_option_visible(target))
        self.nx_mcu_check.setEnabled(self._nx_mcu_option_visible(target))
        self.upgrade_btn.setText(self._upgrade_button_text(target))
        self._update_mcu_visibility()
        if target:
            if target.key != self.current_mcu_target_key:
                self.current_mcu_target_key = target.key
                self.current_mcu_values.clear()
            family_text = {
                "nx": "NX OTA 通道",
                "rk3588": "3588 OTA 通道",
                "s100_flash": "S100 线刷",
                "orin_flash": "Orin NX 线刷",
                "line_flash": "线刷",
            }.get(target.family, target.family)
            self.target_status.setText(f"{target.label} · {family_text}")
            if is_flash:
                self.target_meta.setText("本机 USB DFU/fastboot 线刷 · 不走远端 OTA")
                self.target_status.setToolTip("线刷目标跟随顶部当前设备；S100 可通过 3652:6610 DFU 或 fastboot 执行。")
                self.target_meta.setToolTip("请把设备接到本机；S100 预检会提示 SSH 自动进入、3652:6610 DFU 和 fastboot 状态。")
                self._set_device_info_message("线刷目标不读取远端设备信息；请使用预检检查本机 fastboot 和包类型。")
            else:
                self.target_meta.setText("远端升级目录已就绪")
                self.target_status.setToolTip("OTA 目标跟随顶部当前设备和登录信息。")
                self.target_meta.setToolTip("升级包会上传到目标设备的升级目录。")
        else:
            self.current_mcu_target_key = ""
            self.current_mcu_values.clear()
            profile = self.profile()
            self.target_status.setText(f"{profile.label} 不支持 OTA/线刷")
            self.target_meta.setText("请切换到支持 OTA 或线刷的设备")
            self.target_status.setToolTip("请在顶部当前设备中切换到支持 OTA 或线刷的设备。")
            self.target_meta.setToolTip("")
            self._set_device_info_message("当前设备不支持 OTA/线刷")
        self.update_info_label()
        if supported and refresh and not is_flash:
            self.refresh_device_info()

    def _mcu_supported_for_target(self, target=None) -> bool:
        target = self.current_ota_target() if target is None else target
        return bool(target and target.family == "rk3588" and not target.is_flash)

    def _nx_mcu_option_visible(self, target=None) -> bool:
        return False

    def _upgrade_button_text(self, target=None) -> str:
        target = self.current_ota_target() if target is None else target
        if not target:
            return "升级/线刷"
        if target.is_flash:
            return "执行线刷"
        if target.family == "nx":
            return "升级 NX"
        if target.family == "rk3588":
            return "升级 3588"
        return "升级/线刷"

    def _update_mcu_visibility(self) -> bool:
        visible = self._mcu_supported_for_target()
        self.mcu_read_btn.setVisible(visible)
        if self.mcu_section is not None:
            self.mcu_section.setVisible(visible)
        if self.device_info_hint is not None:
            if visible:
                self.device_info_hint.setText("打开页面会自动刷新一次设备版本和升级空间；MCU 当前版本需要手动读取。")
            else:
                self.device_info_hint.setText("打开页面会自动刷新设备版本和升级空间；当前目标不需要 MCU 版本对比。")
        return visible

    def choose_package(self) -> bool:
        path = self._choose_package_path()
        if path:
            self.package.setText(path)
            self.update_info_label()
            return True
        return False

    def choose_deploy_dir(self) -> bool:
        path = self._choose_deploy_dir_path()
        if path:
            self.package.setText(path)
            self.update_info_label()
            return True
        return False

    def _choose_package_path(self) -> str:
        current_path = Path(self.package.text().strip()).expanduser()
        start_dir = str(Path.home() / "Downloads")
        resource_dir = ota_package_locator.RESOURCE_PACKAGE_DIR
        if resource_dir.is_dir():
            start_dir = str(resource_dir)
        if current_path.parent.is_dir():
            start_dir = str(current_path.parent)
        dialog = QFileDialog(
            self,
            "选择升级包/线刷包",
            start_dir,
            "升级包/线刷包 (*.tar.gz *.zip);;All (*)",
        )
        dialog.setOption(QFileDialog.DontUseNativeDialog, True)
        dialog.setFileMode(QFileDialog.ExistingFile)
        dialog.setAcceptMode(QFileDialog.AcceptOpen)
        dialog.setViewMode(QFileDialog.Detail)
        dialog.setMinimumSize(1100, 720)
        dialog.resize(1180, 760)
        dialog.setLabelText(QFileDialog.FileName, "文件")
        dialog.setLabelText(QFileDialog.FileType, "类型")
        dialog.setLabelText(QFileDialog.Accept, "选择")
        dialog.setLabelText(QFileDialog.Reject, "取消")
        if current_path.name:
            dialog.selectFile(current_path.name)
        if dialog.exec_() != QFileDialog.Accepted:
            return ""
        selected = dialog.selectedFiles()
        return selected[0] if selected else ""

    def _choose_deploy_dir_path(self) -> str:
        current_path = Path(self.package.text().strip()).expanduser()
        start_dir = str(Path.home() / "下载")
        if current_path.is_dir():
            start_dir = str(current_path)
        elif current_path.parent.is_dir():
            start_dir = str(current_path.parent)
        return QFileDialog.getExistingDirectory(self, "选择 deploy 小包目录", start_dir)

    def update_info_label(self) -> None:
        target = self.current_ota_target()
        package_name = Path(self.package.text()).name if self.package.text().strip() else "未选择升级包"
        package_path = self.package.text().strip()
        package_type = ota.package_type_hint(package_path)
        if not package_type and target and not target.is_flash:
            selected = Path(package_path).expanduser()
            suffixes = [suffix.lower() for suffix in selected.suffixes]
            if selected.suffix.lower() == ".zip" or suffixes[-2:] == [".tar", ".gz"]:
                package_type = target.family
        package_version = ota.package_version(self.package.text().strip())
        package_summary = ota.package_light_summary(package_path)
        type_text = {
            "nx": "NX OTA 包",
            "rk3588": "3588 OTA 包",
            "s100_flash": "S100 线刷包",
            "orin_flash": "Orin NX 线刷包",
            "line_flash": "线刷包",
            "deb_deploy": "小包部署目录",
            "deb_package": "Debian 小包",
            "whl_package": "Python wheel 小包",
            "small_deploy_archive": "小包压缩包",
        }.get(package_type, "待校验")
        version_text = f"，版本：{package_version}" if package_version else ""
        summary_text = f"；{package_summary}" if package_summary else ""
        family_text = {
            "nx": "NX OTA 通道",
            "rk3588": "3588 OTA 通道",
            "s100_flash": "S100 线刷",
            "orin_flash": "Orin NX 线刷",
            "line_flash": "线刷",
        }.get(target.family, target.family) if target else "--"
        endpoint = "本机 USB DFU/fastboot" if target and target.is_flash else "目标设备"
        target_text = "目标：" + (target.label if target else "当前设备不支持 OTA/线刷")
        compact_parts = [f"包：{package_name}", f"类型：{type_text}{version_text}"]
        if package_summary:
            compact_parts.append(package_summary)
        self.info_label.setText("；".join(compact_parts))
        self.info_label.setToolTip(
            self._shorten(
                f"{target_text}\n执行方式：{endpoint}\n通道：{family_text}\n包：{package_name}\n"
                f"{type_text}{version_text}{summary_text}\n"
                "选包阶段只做轻量展示；执行前会按目标校验 OTA 包或线刷包。",
                700,
            )
        )
        self.update_package_detail()
        self.update_mcu_table()
