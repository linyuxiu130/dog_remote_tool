from __future__ import annotations

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QCheckBox,
    QLabel,
    QLineEdit,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)


class OtaLayoutMixin:
    def _build_ota_workbench(self) -> QFrame:
        box = QFrame()
        box.setObjectName("OtaWorkbench")
        box_layout = QVBoxLayout(box)
        box_layout.setContentsMargins(10, 10, 10, 10)
        box_layout.setSpacing(10)

        self.target_status = QLabel()
        self.target_status.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.target_status.setWordWrap(True)
        self.target_status.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        self.target_status.setObjectName("OtaTargetTitle")

        self.target_meta = QLabel()
        self.target_meta.setObjectName("Muted")
        self.target_meta.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.target_meta.setWordWrap(True)
        self.target_meta.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)

        self.package = QLineEdit()
        self.package.textChanged.connect(self._package_changed)
        self.package.setPlaceholderText("选择 tar.gz/zip 升级包/线刷包，或 deploy 小包目录")
        self.info_label = QLabel()
        self.info_label.setObjectName("Muted")
        self.info_label.setWordWrap(True)
        self.info_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.info_label.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        self.device_info_raw = ""
        self.package_info_grid: QGridLayout | None = None
        self.summary_info_grid: QGridLayout | None = None
        self.mcu_info_grid: QGridLayout | None = None
        self.current_mcu_values: dict[str, list[str]] = {}
        self.current_mcu_target_key = ""
        self.mcu_reading = False
        self.device_info_is_mcu_read = False
        self.device_info_cards: list[QWidget] = []
        self.mcu_section: QFrame | None = None
        self.device_info_hint: QLabel | None = None
        self.package.setMinimumWidth(0)

        browse_pkg = QPushButton("选包")
        browse_pkg.setMinimumWidth(72)
        browse_pkg.clicked.connect(self.choose_package)
        self.browse_pkg = browse_pkg
        browse_dir = QPushButton("选目录")
        browse_dir.setMinimumWidth(82)
        browse_dir.clicked.connect(self.choose_deploy_dir)
        self.browse_dir = browse_dir

        self.upgrade_btn = QPushButton("升级/线刷")
        self.upgrade_btn.setObjectName("Danger")
        self.upgrade_btn.setMinimumWidth(96)
        self.upgrade_btn.clicked.connect(self.run_upgrade)
        self.precheck_btn = QPushButton("预检")
        self.precheck_btn.setObjectName("SoftPrimary")
        self.precheck_btn.setMinimumWidth(88)
        self.precheck_btn.clicked.connect(self.run_precheck)
        self.entry_btn = QPushButton("刷写入口")
        self.entry_btn.setObjectName("SoftPrimary")
        self.entry_btn.setMinimumWidth(96)
        self.entry_btn.clicked.connect(self.run_entry_monitor)
        self.stop_task_btn = QPushButton("停止任务")
        self.stop_task_btn.setObjectName("Danger")
        self.stop_task_btn.setMinimumWidth(96)
        self.stop_task_btn.clicked.connect(self.runner.stop)
        self.refresh_btn = QPushButton("刷新设备信息")
        self.refresh_btn.setObjectName("SoftPrimary")
        self.refresh_btn.setMinimumWidth(112)
        self.refresh_btn.clicked.connect(lambda _checked=False: self.refresh_device_info())
        self.mcu_read_btn = QPushButton("读取 MCU 版本")
        self.mcu_read_btn.setObjectName("SoftPrimary")
        self.mcu_read_btn.setMinimumWidth(128)
        self.mcu_read_btn.clicked.connect(self.run_mcu_maintenance_read)
        self.nx_mcu_check = QCheckBox("")
        self.nx_mcu_check.setChecked(True)
        self.nx_mcu_check.setToolTip("")

        target_panel = self._build_target_panel()
        package_panel = self._build_package_panel(browse_pkg, browse_dir)

        top_grid = QGridLayout()
        top_grid.setContentsMargins(0, 0, 0, 0)
        top_grid.setHorizontalSpacing(10)
        top_grid.setVerticalSpacing(10)
        top_grid.addWidget(target_panel, 0, 0)
        top_grid.addWidget(package_panel, 0, 1)
        top_grid.setColumnStretch(0, 1)
        top_grid.setColumnStretch(1, 2)

        box_layout.addLayout(top_grid)
        box_layout.addLayout(self._build_action_row())
        box_layout.addWidget(self._build_device_info_panel())
        return box

    def _build_target_panel(self) -> QFrame:
        target_panel = QFrame()
        target_panel.setObjectName("OtaTargetPanel")
        target_panel.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        target_layout = QVBoxLayout(target_panel)
        target_layout.setContentsMargins(14, 12, 14, 12)
        target_layout.setSpacing(6)
        target_label = QLabel("目标")
        target_label.setObjectName("FieldLabel")
        target_layout.addWidget(target_label)
        target_layout.addWidget(self.target_status)
        target_layout.addWidget(self.target_meta)
        return target_panel

    def _build_package_panel(self, browse_pkg: QPushButton, browse_dir: QPushButton) -> QFrame:
        package_panel = QFrame()
        package_panel.setObjectName("OtaPackagePanel")
        package_layout = QGridLayout(package_panel)
        package_layout.setContentsMargins(14, 12, 14, 12)
        package_layout.setHorizontalSpacing(8)
        package_layout.setVerticalSpacing(7)
        package_label = QLabel("升级包 / 线刷包")
        package_label.setObjectName("FieldLabel")
        package_layout.addWidget(package_label, 0, 0, 1, 2)
        package_layout.addWidget(self.package, 1, 0)
        package_layout.addWidget(browse_pkg, 1, 1)
        package_layout.addWidget(browse_dir, 1, 2)
        package_layout.addWidget(self.info_label, 2, 0, 1, 3)
        package_layout.setColumnStretch(0, 1)
        return package_panel

    def _build_action_row(self) -> QHBoxLayout:
        action_panel = QFrame()
        action_panel.setObjectName("OtaActionPanel")
        action_layout = QHBoxLayout(action_panel)
        action_layout.setContentsMargins(14, 12, 14, 12)
        action_layout.setSpacing(12)

        action_text = QVBoxLayout()
        action_text.setContentsMargins(0, 0, 0, 0)
        action_text.setSpacing(3)
        action_title = QLabel("操作")
        action_title.setObjectName("OtaActionTitle")
        action_hint = QLabel("3588/NX OTA 走远端升级；S100/Orin 线刷包走本机 USB 线刷。正式刷写前请确认目标和包。")
        action_hint.setObjectName("Muted")
        action_hint.setWordWrap(True)
        action_text.addWidget(action_title)
        action_text.addWidget(action_hint)

        secondary_actions = QHBoxLayout()
        secondary_actions.setContentsMargins(0, 0, 0, 0)
        secondary_actions.setSpacing(8)
        secondary_actions.addWidget(self.refresh_btn)
        secondary_actions.addWidget(self.mcu_read_btn)
        secondary_actions.addWidget(self.entry_btn)
        secondary_actions.addWidget(self.nx_mcu_check)

        secondary_content = QWidget()
        secondary_content.setLayout(secondary_actions)
        secondary_content.hide()
        secondary_box = QFrame()
        secondary_box.setObjectName("AdvancedDetails")
        secondary_box_layout = QVBoxLayout(secondary_box)
        secondary_box_layout.setContentsMargins(0, 0, 0, 0)
        secondary_box_layout.setSpacing(8)
        secondary_toggle = QPushButton("更多操作")
        secondary_toggle.setObjectName("AdvancedDetailsToggle")
        secondary_toggle.setCheckable(True)
        secondary_toggle.toggled.connect(secondary_content.setVisible)
        secondary_toggle.toggled.connect(lambda checked: secondary_toggle.setText("收起更多操作" if checked else "更多操作"))
        secondary_box_layout.addWidget(secondary_toggle)
        secondary_box_layout.addWidget(secondary_content)

        primary_actions = QHBoxLayout()
        primary_actions.setContentsMargins(0, 0, 0, 0)
        primary_actions.setSpacing(8)
        primary_actions.addWidget(self.precheck_btn)
        primary_actions.addWidget(self.upgrade_btn)
        primary_actions.addWidget(self.stop_task_btn)

        action_layout.addLayout(action_text, 1)
        action_layout.addLayout(primary_actions)
        action_layout.addWidget(secondary_box)

        action_row = QHBoxLayout()
        action_row.setContentsMargins(0, 0, 0, 0)
        action_row.setSpacing(8)
        action_row.addWidget(action_panel)
        return action_row

    def _build_device_info_panel(self) -> QFrame:
        box = QFrame()
        box.setObjectName("AdvancedDetails")
        box_layout = QVBoxLayout(box)
        box_layout.setContentsMargins(0, 0, 0, 0)
        box_layout.setSpacing(8)
        self.device_info_toggle = QPushButton("设备详情")
        self.device_info_toggle.setObjectName("AdvancedDetailsToggle")
        self.device_info_toggle.setCheckable(True)
        box_layout.addWidget(self.device_info_toggle)

        panel = QFrame()
        panel.setObjectName("OtaDevicePanel")
        panel_layout = QVBoxLayout(panel)
        panel_layout.setContentsMargins(14, 14, 14, 14)
        panel_layout.setSpacing(10)

        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        header.setSpacing(8)
        title = QLabel("设备信息")
        title.setObjectName("DiagSectionTitle")
        hint = QLabel("打开页面会自动刷新一次设备版本和升级空间；MCU 当前版本需要手动读取。")
        hint.setObjectName("Muted")
        hint.setWordWrap(True)
        self.device_info_hint = hint
        header.addWidget(title)
        header.addWidget(hint, 1)
        panel_layout.addLayout(header)

        content_grid = QGridLayout()
        content_grid.setContentsMargins(0, 0, 0, 0)
        content_grid.setHorizontalSpacing(10)
        content_grid.setVerticalSpacing(10)

        package_section, package_grid = self._section_panel("升级包内容")
        self.package_info_grid = package_grid
        content_grid.addWidget(package_section, 0, 0)

        summary_section, summary_grid = self._section_panel("版本与空间")
        self.summary_info_grid = summary_grid
        content_grid.addWidget(summary_section, 0, 1)
        content_grid.setColumnStretch(0, 1)
        content_grid.setColumnStretch(1, 1)
        panel_layout.addLayout(content_grid)

        mcu_section, mcu_grid = self._section_panel("MCU 版本对比")
        self.mcu_section = mcu_section
        self.mcu_info_grid = mcu_grid
        panel_layout.addWidget(mcu_section)

        self._set_device_info_message("未读取")
        panel.hide()
        self.device_info_toggle.toggled.connect(panel.setVisible)
        self.device_info_toggle.toggled.connect(
            lambda checked: self.device_info_toggle.setText("收起设备详情" if checked else "设备详情")
        )
        box_layout.addWidget(panel)
        return box

    def _section_panel(self, title: str) -> tuple[QFrame, QGridLayout]:
        section = QFrame()
        section.setObjectName("OtaSectionPanel")
        layout = QVBoxLayout(section)
        layout.setContentsMargins(12, 11, 12, 12)
        layout.setSpacing(8)
        title_label = QLabel(title)
        title_label.setObjectName("DiagSectionTitle")
        layout.addWidget(title_label)
        grid = QGridLayout()
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(8)
        grid.setVerticalSpacing(6)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)
        layout.addLayout(grid)
        return section, grid

    def _info_row(self, title: str, value_text: str) -> tuple[QFrame, QLabel]:
        row = QFrame()
        row.setObjectName("OtaInfoRow")
        layout = QVBoxLayout(row)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(4)
        title_label = QLabel(title)
        title_label.setObjectName("OtaInfoKey")
        title_label.setWordWrap(True)
        title_label.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        value = QLabel(value_text)
        value.setObjectName("OtaInfoValue")
        value.setWordWrap(True)
        value.setTextInteractionFlags(Qt.TextSelectableByMouse)
        value.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        layout.addWidget(title_label)
        layout.addWidget(value)
        return row, value
