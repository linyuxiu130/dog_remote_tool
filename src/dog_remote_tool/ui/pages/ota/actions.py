from __future__ import annotations

from pathlib import Path

from PyQt5.QtCore import QProcess
from PyQt5.QtWidgets import QMessageBox

from dog_remote_tool.modules import ota


def _ota_page_module():
    from dog_remote_tool.ui.pages.ota import page as ota_page

    return ota_page


class OtaActionsMixin:
    def display_command_for_log(self) -> str:
        if not self.current_spec:
            return ""
        if self.current_spec.display_command:
            return self.current_spec.display_command
        return self.current_spec.title

    def ota_args(self) -> tuple[str, str, str, str, str, str, str]:
        target = self.current_ota_target()
        if not target:
            raise RuntimeError("当前设备不支持 OTA/线刷")
        return (
            target.key,
            target.host,
            target.user,
            target.password,
            target.remote_dir,
            self.package.text().strip(),
            ota.default_tools_path() if target.family == "nx" else "",
        )

    def device_info_spec(self):
        target, host, user, password, remote_dir, _package, _tools = self.ota_args()
        return ota.device_info_command(target, host, user, password, remote_dir)

    def mcu_maintenance_info_spec(self):
        target, host, user, password, remote_dir, _package, _tools = self.ota_args()
        return ota.mcu_maintenance_info_command(target, host, user, password, remote_dir)

    def precheck_spec(self):
        target, host, user, password, remote_dir, package, tools = self.ota_args()
        current = self.current_ota_target()
        if current and current.is_flash:
            return ota.flash_precheck_command(current, package)
        if ota.package_type_hint(package) in {"deb_deploy", "deb_package", "whl_package", "small_deploy_archive"}:
            return ota.small_precheck_command(target, host, user, password, remote_dir, package)
        return ota.precheck_command(target, host, user, password, remote_dir, package, tools)

    def entry_monitor_spec(self):
        current = self.current_ota_target()
        if not current or current.family != "s100_flash" or not current.is_flash:
            raise RuntimeError("当前设备不支持 S100 刷写入口观察")
        return ota.s100_entry_monitor_command(current)

    def upgrade_spec(self):
        target, host, user, password, remote_dir, package, tools = self.ota_args()
        current = self.current_ota_target()
        if current and current.is_flash:
            return ota.flash_upgrade_command(current, package)
        if ota.package_type_hint(package) in {"deb_deploy", "deb_package", "whl_package", "small_deploy_archive"}:
            return ota.small_deploy_command(target, host, user, password, remote_dir, package)
        skip_mcu = self._skip_nx_mcu_for_upgrade(current, package)
        return ota.upgrade_command(target, host, user, password, remote_dir, package, tools, skip_mcu)

    def refresh_device_info(self, *, mcu_maintenance: bool = False) -> bool:
        if not self.page_active:
            return False
        if not self.current_ota_target():
            self._set_device_info_message("当前设备不支持 OTA/线刷")
            return False
        if getattr(self.current_ota_target(), "is_flash", False):
            self._set_device_info_message("线刷目标不读取远端设备信息；请使用预检检查本机 fastboot 和包类型。")
            return False
        if self.device_info_slot.is_running():
            return False
        spec = self.mcu_maintenance_info_spec() if mcu_maintenance else self.device_info_spec()
        self.device_info_is_mcu_read = mcu_maintenance
        if mcu_maintenance:
            self.mcu_reading = True
            self.update_mcu_table()
        else:
            self._set_summary_message("读取中...")
        process, request_id = self.device_info_slot.start_spec(spec)
        if process is None:
            if mcu_maintenance:
                self.mcu_reading = False
                self.update_mcu_table()
            else:
                self._set_summary_message("任务未启动")
            return False
        process.readyReadStandardOutput.connect(lambda: self.read_device_info_output(process, request_id))
        process.finished.connect(lambda exit_code, _status: self.device_info_finished(process, request_id, exit_code))
        process.start()
        return True

    def run_mcu_maintenance_read(self) -> bool:
        target = self.current_ota_target()
        if not target or target.family != "rk3588":
            QMessageBox.warning(self, "当前设备不支持", "读取 MCU 版本仅支持 3588 目标。")
            return False
        if self.device_info_slot.is_running():
            QMessageBox.information(self, "正在读取", "当前已有设备信息读取任务，请稍后再试。")
            return False
        answer = QMessageBox.question(
            self,
            "读取 MCU 版本",
            (
                f"目标：{target.label}\n\n"
                "该操作会临时停止远端 robot-launch.service，读取 MCU 固件版本后自动恢复。\n"
                "不会刷写固件或修改升级包。\n\n"
                "确认继续？"
            ),
            QMessageBox.Yes | QMessageBox.Cancel,
            QMessageBox.Cancel,
        )
        if answer == QMessageBox.Yes:
            return self.refresh_device_info(mcu_maintenance=True)
        return False

    def activate_page(self) -> None:
        if self.page_active:
            return
        self.page_active = True
        _ota_page_module().QTimer.singleShot(200, self.refresh_device_info)

    def deactivate_page(self) -> None:
        self._deactivate_device_info_polling()

    def shutdown_processes(self) -> None:
        self._deactivate_device_info_polling()

    def _deactivate_device_info_polling(self) -> None:
        self.page_active = False
        self._stop_device_info_process()

    def _stop_device_info_process(self) -> None:
        self.device_info_slot.stop()
        self.device_info_is_mcu_read = False
        self.mcu_reading = False

    def read_device_info_output(self, process: QProcess, request_id: int) -> bool:
        return self.device_info_slot.read_available_output(process, request_id)

    def device_info_finished(self, process: QProcess, request_id: int, exit_code: int) -> bool:
        output = self.device_info_slot.finish(process, request_id)
        if output is None:
            return False
        was_mcu_read = self.device_info_is_mcu_read
        self.device_info_is_mcu_read = False
        if exit_code == 0:
            self.update_device_info(output, update_summary=not was_mcu_read)
        else:
            if was_mcu_read:
                self.mcu_reading = False
                self.update_mcu_table("读取失败")
            else:
                self._set_summary_message("读取失败")
        return True

    def _shorten(self, text: str, limit: int) -> str:
        if len(text) <= limit:
            return text
        return text[: max(0, limit - 1)].rstrip() + "…"

    def _skip_nx_mcu_for_upgrade(self, target, package: str) -> bool:
        if not target or target.family != "nx" or target.is_flash:
            return False
        return True

    def validate_package_for_target(self) -> bool:
        target = self.current_ota_target()
        if not target:
            QMessageBox.warning(self, "当前设备不支持", "请先在顶部当前设备中选择支持 OTA 或线刷的设备。")
            return False
        package = self.package.text().strip()
        if not package:
            QMessageBox.warning(self, "请选择升级包", "请先手动选择升级包或线刷包。")
            return False
        package_path = Path(package).expanduser()
        if not package_path.exists():
            QMessageBox.warning(self, "升级包不存在", "请选择存在的升级包或线刷包。")
            return False
        if package_path.is_dir():
            package_type = ota.package_type_hint(package)
            if package_type == "deb_deploy" and not target.is_flash:
                return True
            QMessageBox.warning(self, "升级包格式不支持", "请选择 .zip/.tar.gz 升级包，或包含 deb/whl 的小包目录。")
            return False
        suffixes = [suffix.lower() for suffix in package_path.suffixes]
        package_type = ota.package_type_hint(package)
        is_small_package = package_type in {"deb_package", "whl_package", "small_deploy_archive"}
        is_supported_archive = package_path.suffix.lower() == ".zip" or suffixes[-2:] == [".tar", ".gz"]
        if is_small_package and not target.is_flash:
            return True
        if not is_supported_archive:
            QMessageBox.warning(self, "升级包格式不支持", "请选择 .zip/.tar.gz 升级包/线刷包，或 .deb/.whl 小包。")
            return False
        if target.is_flash:
            accepted = set(target.accepted_package_types)
            if not package_type or package_type not in accepted:
                expected = "、".join(ota.flash_type_label(item) for item in target.accepted_package_types)
                actual = ota.flash_type_label(package_type) if package_type else "未识别包"
                QMessageBox.warning(self, "线刷包不匹配", f"当前目标需要 {expected}，但选择的是 {actual}。")
                return False
            return True
        if package_type and package_type != target.family:
            expected = "NX 包" if target.family == "nx" else "3588 包"
            actual = {
                "nx": "NX 包",
                "rk3588": "3588 包",
                "s100_flash": "S100 线刷包",
                "orin_flash": "Orin NX 线刷包",
                "small_deploy_archive": "小包压缩包",
            }.get(package_type, "未识别包")
            QMessageBox.warning(self, "升级包不匹配", f"当前目标需要 {expected}，但选择的是 {actual}。")
            return False
        return True

    def run_upgrade(self) -> bool:
        if not self.validate_package_for_target():
            return False
        self.current_spec = self.upgrade_spec()
        return self.run_current()

    def run_precheck(self) -> bool:
        if not self.validate_package_for_target():
            return False
        self.current_spec = self.precheck_spec()
        return self.run_current()

    def run_entry_monitor(self) -> bool:
        target = self.current_ota_target()
        if not target or target.family != "s100_flash" or not target.is_flash:
            QMessageBox.warning(self, "当前设备不支持", "刷写入口观察仅支持 S100 线刷目标。")
            return False
        self.current_spec = self.entry_monitor_spec()
        return self.run_current()

    def run_current(self) -> bool:
        if not self.current_spec:
            return False
        if self.current_spec.dangerous:
            target = self.current_ota_target()
            package_name = Path(self.package.text()).name or "未选择升级包"
            is_flash = bool(target and target.is_flash)
            target_label = target.label if target else "当前设备"
            message = f"目标：{target_label}\n升级包：{package_name}\n"
            if is_flash:
                message += "执行方式：本机 USB DFU/fastboot 线刷\n\n"
            else:
                message += "执行方式：远端升级\n\n"
            if self.current_spec.title in ("执行 OTA 升级", "执行线刷"):
                message += (
                    "该操作会执行刷机命令，成功后设备可能自动重启。\n"
                    "请确认目标和升级包。\n\n"
                    "确认继续？"
                )
            else:
                message += (
                    "该操作会上传并准备远端升级文件，但不会执行刷机命令。\n"
                    "请确认目标和升级包。\n\n"
                    "确认继续？"
                )
            answer = QMessageBox.question(self, self.current_spec.title, message, QMessageBox.Yes | QMessageBox.Cancel, QMessageBox.Cancel)
            if answer != QMessageBox.Yes:
                return False
        task_id = self.runner.run(self.current_spec, self.display_command_for_log())
        if task_id is None:
            QMessageBox.warning(self, "任务未启动", "当前已有任务运行，升级/线刷命令未启动。请等待当前任务结束后重试。")
            return False
        return True
