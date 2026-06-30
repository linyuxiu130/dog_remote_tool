from __future__ import annotations

from pathlib import Path

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QFrame, QGridLayout, QLabel, QSizePolicy, QVBoxLayout

from dog_remote_tool.modules import ota


_LARGE_ARCHIVE_UI_PARSE_LIMIT = 512 * 1024 * 1024


class OtaDeviceInfoMixin:
    def update_device_info(self, output: str, *, update_summary: bool = True) -> None:
        self.device_info_raw = output
        info = self.parse_device_info(output)
        summary_rows: list[tuple[str, str, str]] = []
        system = info["system"]
        space = info["space"]
        if system.get("设备版本"):
            summary_rows.append(("设备版本", system["设备版本"], system["设备版本"]))
        if space.get("升级空间"):
            summary_rows.append(("升级空间", space["升级空间"], space["升级空间"]))
        for key in ("业务版本", "用户版本", "L4T版本"):
            if system.get(key):
                summary_rows.append((key, system[key], system[key]))
        if update_summary:
            self._set_summary_rows(summary_rows or [("设备信息", "无可用信息", output)])
        current_by_slot: dict[str, list[str]] = {}
        for name, state, detail in info["current_mcu"]:
            state_text = {"ok": "已读取", "bad": "读取失败", "skip": "已跳过"}.get(state, state)
            value = f"{state_text}: {detail}" if detail else state_text
            slot = ota.mcu_slot_for_name(name)
            current_by_slot.setdefault(slot, []).append(f"{name}: {value}")
        if current_by_slot or self.mcu_reading:
            self.current_mcu_values = current_by_slot
            self.mcu_reading = False
            self.update_mcu_table("未返回 MCU 信息" if not current_by_slot else "")

    def parse_device_info(self, output: str) -> dict[str, object]:
        system: dict[str, str] = {}
        space: dict[str, str] = {}
        current_mcu: list[tuple[str, str, str]] = []
        target_mcu = ""
        mcu_mode = ""
        for raw in output.splitlines():
            line = raw.strip()
            if not line or ": " not in line:
                continue
            key, value = line.split(": ", 1)
            if key == "发布日期":
                system["业务版本"] = f"{system.get('业务版本', '未读取')} / {value}" if "业务版本" in system else value
            elif key in ("业务版本", "用户版本", "L4T版本", "设备版本"):
                system[key] = value
            elif key == "升级空间":
                space["升级空间"] = value
            elif key == "远程目录可用空间":
                space.setdefault("升级空间", f"remote {value}")
            elif key == "根分区可用空间":
                pass
            elif key == "/ota 可用空间":
                space.setdefault("升级空间", f"/ota {value}")
            elif key == "/userdata/update 可用空间":
                space["升级空间"] = f"/userdata/update {value}"
            elif key == "MCU读取模式":
                mcu_mode = value
            elif key == "目标MCU":
                target_mcu = value
            elif key == "当前MCU":
                current_mcu.append(self._parse_mcu_line(value))
        return {
            "system": system,
            "space": space,
            "target_mcu": target_mcu,
            "mcu_mode": mcu_mode,
            "current_mcu": current_mcu,
        }

    def _parse_mcu_line(self, value: str) -> tuple[str, str, str]:
        if ": " in value:
            name, detail = value.split(": ", 1)
        else:
            name, detail = "当前MCU", value
        if name == "普通读取":
            return name, "skip", detail
        state = "bad" if "读取失败" in detail else "ok"
        detail = detail.replace("读取失败: ", "", 1)
        return name, state, detail

    def _set_device_info_message(self, message: str) -> None:
        self.device_info_raw = message
        self._set_info_sections([("设备信息", message, message)], [])

    def _set_summary_message(self, message: str) -> None:
        self.device_info_raw = message
        self._set_summary_rows([("设备信息", message, message)])

    def _set_summary_rows(self, rows: list[tuple[str, str, str]]) -> None:
        if self.summary_info_grid is None:
            return
        self._set_rows(self.summary_info_grid, rows)

    def update_package_detail(self) -> None:
        if self.package_info_grid is None:
            return
        package = self.package.text().strip()
        if not package:
            self._set_rows(
                self.package_info_grid,
                [("包状态", "未选择；选包后显示包设备版本、系统镜像和目标固件", "")],
            )
            return
        rows = [(title, value, value) for title, value in ota.package_selection_detail_rows(package)]
        self._set_rows(self.package_info_grid, rows or [("包状态", "未解析到可展示的包内容", "")])

    def _set_info_sections(self, summary_rows: list[tuple[str, str, str]], mcu_rows: list[tuple[str, str, str]]) -> None:
        if self.package_info_grid is None or self.summary_info_grid is None or self.mcu_info_grid is None:
            return
        self.update_package_detail()
        self._set_rows(self.summary_info_grid, summary_rows)
        self.update_mcu_table()

    def update_mcu_table(self, status_message: str = "") -> None:
        if self.mcu_info_grid is None:
            return
        target = self.current_ota_target()
        target_key = target.key if target else ""
        slots = ota.mcu_display_slots(target_key)
        target_versions = {}
        package_path = self.package.text().strip()
        defer_target_versions = self._defer_package_target_versions(package_path)
        if target and target.family == "rk3588" and not defer_target_versions:
            target_versions = ota.package_mcu_target_versions(self.package.text().strip(), target_key)
        elif target and target.key == "zgnx" and self._nx_mcu_option_visible(target) and not defer_target_versions:
            target_versions = ota.package_mcu_target_versions(self.package.text().strip(), target_key)
        seen = {slot for slot, _label in slots}
        for slot in sorted(set(self.current_mcu_values) | set(target_versions)):
            if slot not in seen:
                slots.append((slot, slot))
                seen.add(slot)
        rows: list[tuple[str, str, str, str]] = []
        package_selected = bool(self.package.text().strip())
        for slot, label in slots:
            if self.mcu_reading:
                current = "读取中..."
            elif self.current_mcu_values.get(slot):
                current = "\n".join(self.current_mcu_values[slot])
            else:
                current = status_message or "未读取"
            if package_selected:
                target_value = "预检时校验" if defer_target_versions else target_versions.get(slot) or "包内未包含"
            else:
                target_value = "未选择升级包"
            rows.append((label, current, target_value, slot))
        if not rows:
            rows = [("MCU", status_message or "当前目标无 MCU 版本读取配置", "未选择升级包", "")]
        self._set_mcu_rows(rows)

    def _defer_package_target_versions(self, package_path: str) -> bool:
        if not package_path:
            return False
        package = Path(package_path).expanduser()
        if not package.is_file() or package.stat().st_size <= _LARGE_ARCHIVE_UI_PARSE_LIMIT:
            return False
        suffixes = [suffix.lower() for suffix in package.suffixes]
        return package.suffix.lower() == ".zip" or suffixes[-2:] == [".tar", ".gz"]

    def _set_mcu_rows(self, rows: list[tuple[str, str, str, str]]) -> None:
        if self.mcu_info_grid is None:
            return
        while self.mcu_info_grid.count():
            item = self.mcu_info_grid.takeAt(0)
            widget = item.widget()
            if widget:
                widget.setParent(None)
                widget.deleteLater()
        headers = ("模块", "当前", "目标")
        for column, text in enumerate(headers):
            label = QLabel(text)
            label.setObjectName("OtaInfoKey")
            if column == 0:
                label.setMinimumWidth(150)
                label.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Preferred)
            self.mcu_info_grid.addWidget(label, 0, column)
        for index, (module, current, target, tooltip) in enumerate(rows, start=1):
            module_label = QLabel(module)
            module_label.setObjectName("OtaMcuModuleLabel")
            module_label.setWordWrap(False)
            module_label.setMinimumWidth(150)
            module_label.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Preferred)
            current_box, current_label = self._mcu_value_box(current)
            target_box, target_label = self._mcu_value_box(target)
            current_label.setToolTip(current)
            target_label.setToolTip(target)
            module_label.setToolTip(tooltip or module)
            self.mcu_info_grid.addWidget(module_label, index, 0)
            self.mcu_info_grid.addWidget(current_box, index, 1)
            self.mcu_info_grid.addWidget(target_box, index, 2)
        self.mcu_info_grid.setHorizontalSpacing(8)
        self.mcu_info_grid.setColumnMinimumWidth(0, 150)
        self.mcu_info_grid.setColumnStretch(0, 0)
        self.mcu_info_grid.setColumnStretch(1, 1)
        self.mcu_info_grid.setColumnStretch(2, 1)

    def _mcu_value_box(self, text: str) -> tuple[QFrame, QLabel]:
        box = QFrame()
        box.setObjectName("OtaInfoRow")
        layout = QVBoxLayout(box)
        layout.setContentsMargins(10, 7, 10, 7)
        label = QLabel(text)
        label.setObjectName("OtaInfoValue")
        label.setWordWrap(True)
        label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        label.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        layout.addWidget(label)
        return box, label

    def _set_rows(self, grid: QGridLayout, rows: list[tuple[str, str, str]]) -> None:
        while grid.count():
            item = grid.takeAt(0)
            widget = item.widget()
            if widget:
                widget.setParent(None)
                widget.deleteLater()
        for index, (title, value, tooltip) in enumerate(rows):
            row, value_label = self._info_row(title, value)
            value_label.setToolTip(tooltip)
            row.setToolTip(tooltip)
            grid.addWidget(row, index // 2, index % 2)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)
