from __future__ import annotations

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QGridLayout

from dog_remote_tool.ui.pages.dashboard.status import _dashboard_page_module


class DashboardRowsMixin:
    def _clear_layout(self, layout: QGridLayout) -> bool:
        changed = False
        while layout.count():
            changed = True
            item = layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.setParent(None)
                widget.deleteLater()
        return changed

    def _package_rows_state(self) -> list[tuple[str, str, str]]:
        dashboard_page = _dashboard_page_module()
        if not callable(getattr(self.package_rows, "itemAtPosition", None)):
            return []
        row_count = self.package_rows.rowCount() if callable(getattr(self.package_rows, "rowCount", None)) else 0
        current: list[tuple[str, str, str]] = []
        for row in range(row_count):
            values = []
            for col in range(3):
                item = self.package_rows.itemAtPosition(row, col)
                widget = item.widget() if item is not None and callable(getattr(item, "widget", None)) else None
                if widget is None:
                    values.append("")
                    continue
                text = dashboard_page.widget_text(widget)
                tooltip = dashboard_page.widget_tooltip(widget)
                values.append(tooltip if col == 2 and tooltip else text)
            if row == 0 and values[0] == "暂无版本数据":
                return []
            if any(values):
                current.append((values[0], values[1], values[2]))
        return current

    def _set_package_rows(self, rows: list[tuple[str, str, str]]) -> bool:
        dashboard_page = _dashboard_page_module()
        changed = self._package_rows_state() != list(rows)
        self._clear_layout(self.package_rows)
        if not rows:
            muted = dashboard_page.QLabel("暂无版本数据")
            muted.setObjectName("Muted")
            self.package_rows.addWidget(muted, 0, 0, 1, 3)
            return changed
        for row, (label, name, version) in enumerate(rows):
            label_widget = dashboard_page.QLabel(label)
            label_widget.setObjectName("FieldLabel")
            label_widget.setMinimumWidth(112)
            label_widget.setAlignment(Qt.AlignTop | Qt.AlignLeft)
            name_widget = dashboard_page.QLabel(name)
            name_widget.setObjectName("StatusText")
            name_widget.setWordWrap(False)
            name_widget.setMinimumWidth(290)
            name_widget.setTextInteractionFlags(Qt.TextSelectableByMouse)
            version_widget = dashboard_page.QLabel(version)
            version_widget.setObjectName("StatusStrong")
            if len(version) > 34:
                version_widget.setText(version[:31] + "...")
                version_widget.setToolTip(version)
            version_widget.setMinimumWidth(200)
            version_widget.setWordWrap(False)
            version_widget.setTextInteractionFlags(Qt.TextSelectableByMouse)
            if version == "未发现":
                version_widget.setObjectName("Muted")
            self.package_rows.addWidget(label_widget, row, 0)
            self.package_rows.addWidget(name_widget, row, 1)
            self.package_rows.addWidget(version_widget, row, 2)
        self.package_rows.setColumnStretch(0, 0)
        self.package_rows.setColumnStretch(1, 0)
        self.package_rows.setColumnStretch(2, 1)
        self.package_rows.setColumnMinimumWidth(0, 112)
        self.package_rows.setColumnMinimumWidth(1, 290)
        self.package_rows.setColumnMinimumWidth(2, 200)
        return changed

    def _launch_status_text(self, status: str) -> str:
        return "运行" if status == "running" else "停止" if status == "stopped" else status

    def _launch_rows_state(self) -> list[tuple[str, str, str, str, str]]:
        dashboard_page = _dashboard_page_module()
        if not callable(getattr(self.launch_rows, "itemAtPosition", None)):
            return []
        row_count = self.launch_rows.rowCount() if callable(getattr(self.launch_rows, "rowCount", None)) else 0
        current: list[tuple[str, str, str, str, str]] = []
        for row in range(row_count):
            values = []
            for col in range(5):
                item = self.launch_rows.itemAtPosition(row, col)
                widget = item.widget() if item is not None and callable(getattr(item, "widget", None)) else None
                if widget is None:
                    values.append("")
                    continue
                values.append(dashboard_page.widget_text(widget))
            if row == 0 and values[0] == "暂无运行状态":
                return []
            if any(values):
                current.append((values[0], values[1], values[2], values[3], values[4]))
        return current

    def _set_launch_rows(self, rows: list) -> bool:
        dashboard_page = _dashboard_page_module()
        device_status = dashboard_page.device_status
        expected = [
            (item.index, item.name, device_status.launch_note_label(item.name), self._launch_status_text(item.status), item.uptime or "-")
            for item in rows
        ]
        changed = self._launch_rows_state() != expected
        self._clear_layout(self.launch_rows)
        if not rows:
            muted = dashboard_page.QLabel("暂无运行状态")
            muted.setObjectName("Muted")
            self.launch_rows.addWidget(muted, 0, 0, 1, 6)
            return changed
        for row, item in enumerate(rows):
            index_widget = dashboard_page.QLabel(item.index)
            index_widget.setObjectName("FieldLabel")
            index_widget.setAlignment(Qt.AlignCenter)
            index_widget.setMinimumWidth(22)
            name_widget = dashboard_page.QLabel(item.name)
            name_widget.setObjectName("StatusText")
            name_widget.setWordWrap(True)
            name_widget.setMinimumWidth(320)
            name_widget.setTextInteractionFlags(Qt.TextSelectableByMouse)
            note_widget = dashboard_page.QLabel(device_status.launch_note_label(item.name))
            note_widget.setObjectName("LaunchNote")
            note_widget.setAlignment(Qt.AlignCenter)
            note_widget.setMinimumWidth(104)
            note_widget.setMaximumWidth(116)
            note_widget.setToolTip(device_status.launch_note_detail(item.name))
            state_widget = dashboard_page.QLabel(self._launch_status_text(item.status))
            state_widget.setAlignment(Qt.AlignCenter)
            state_widget.setMinimumWidth(54)
            if item.status == "running":
                state_widget.setStyleSheet("background:#dcfce7;color:#166534;border-radius:5px;padding:2px 6px;font-weight:700;")
            elif item.status == "stopped":
                state_widget.setStyleSheet("background:#f1f5f9;color:#64748b;border-radius:5px;padding:2px 6px;font-weight:700;")
            else:
                state_widget.setStyleSheet("background:#fee2e2;color:#991b1b;border-radius:5px;padding:2px 6px;font-weight:700;")
            uptime_widget = dashboard_page.QLabel(item.uptime or "-")
            uptime_widget.setObjectName("Muted")
            uptime_widget.setAlignment(Qt.AlignCenter)
            uptime_widget.setMinimumWidth(46)
            actions = dashboard_page.QWidget()
            actions_layout = dashboard_page.QHBoxLayout(actions)
            actions_layout.setContentsMargins(0, 0, 0, 0)
            actions_layout.setSpacing(6)
            start_btn = dashboard_page.QPushButton("开启")
            start_btn.setObjectName("DashboardPrimary")
            start_btn.setEnabled(item.status != "running")
            stop_btn = dashboard_page.QPushButton("关闭")
            stop_btn.setObjectName("DashboardDanger")
            stop_btn.setEnabled(item.status != "stopped")
            restart_btn = dashboard_page.QPushButton("重启")
            restart_btn.setObjectName("DashboardAction")
            for button in (start_btn, stop_btn, restart_btn):
                button.setFixedWidth(54)
                actions_layout.addWidget(button)
            actions.setMinimumWidth(188)
            start_btn.clicked.connect(lambda _checked=False, name=item.name: self.run_launch_action(name, "start"))
            stop_btn.clicked.connect(lambda _checked=False, name=item.name: self.run_launch_action(name, "stop"))
            restart_btn.clicked.connect(lambda _checked=False, name=item.name: self.run_launch_action(name, "restart"))
            self.launch_rows.addWidget(index_widget, row, 0)
            self.launch_rows.addWidget(name_widget, row, 1)
            self.launch_rows.addWidget(note_widget, row, 2)
            self.launch_rows.addWidget(state_widget, row, 3)
            self.launch_rows.addWidget(uptime_widget, row, 4)
            self.launch_rows.addWidget(actions, row, 5)
        self.launch_rows.setColumnStretch(0, 0)
        self.launch_rows.setColumnStretch(1, 1)
        self.launch_rows.setColumnStretch(2, 0)
        self.launch_rows.setColumnStretch(3, 0)
        self.launch_rows.setColumnStretch(4, 0)
        self.launch_rows.setColumnStretch(5, 0)
        self.launch_rows.setColumnMinimumWidth(1, 320)
        self.launch_rows.setColumnMinimumWidth(2, 104)
        self.launch_rows.setColumnMinimumWidth(3, 54)
        self.launch_rows.setColumnMinimumWidth(4, 46)
        self.launch_rows.setColumnMinimumWidth(5, 188)
        return changed
