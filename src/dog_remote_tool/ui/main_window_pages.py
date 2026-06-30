from __future__ import annotations

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QLabel, QVBoxLayout, QWidget

from .page_registry import PageSpec


class MainWindowPagesMixin:
    def _build_page_specs(self) -> list[PageSpec]:
        return [
            PageSpec("总览", self._create_dashboard_page),
            PageSpec("遥控", self._create_control_page),
            PageSpec("建图", self._create_mapping_page, "mapping"),
            PageSpec("导航", self._create_navigation_page, "navigation"),
            PageSpec("录包", self._create_bag_page),
            PageSpec("文件管理", self._create_file_manager_page),
            PageSpec("远程访问", self._create_remote_access_page),
            PageSpec("OTA", self._create_ota_page),
            PageSpec("诊断", self._create_mobile_diag_page),
        ]

    def _create_dashboard_page(self) -> QWidget:
        from .pages.dashboard.page import DashboardPage

        return DashboardPage(self.app_root, self.runner, self.device_bar)

    def _create_bag_page(self) -> QWidget:
        from .pages.bag.page import BagPage

        return BagPage(self.runner, self.device_bar)

    def _create_control_page(self) -> QWidget:
        from .pages.control.page import ControlPage

        return ControlPage(self.runner, self.device_bar)

    def _create_mapping_page(self) -> QWidget:
        from .pages.mapping.page import MappingPage

        page = MappingPage(self.runner, self.device_bar)
        page.open_page_requested.connect(self.open_page_by_title)
        return page

    def _create_navigation_page(self) -> QWidget:
        from .pages.navigation.page import NavigationPage

        return NavigationPage(self.runner, self.device_bar)

    def _create_route_network_page(self) -> QWidget:
        from .pages.route_network.page import RouteNetworkPage

        return RouteNetworkPage(self.runner, self.device_bar)

    def _create_remote_access_page(self) -> QWidget:
        from .pages.remote_access.page import RemoteAccessPage

        return RemoteAccessPage(self.runner, self.device_bar)

    def _create_ota_page(self) -> QWidget:
        from .pages.ota.page import OtaPage

        return OtaPage(self.runner, self.device_bar)

    def _create_mobile_diag_page(self) -> QWidget:
        from .pages.mobile_diag.page import MobileDiagPage

        return MobileDiagPage(self.runner, self.device_bar)

    def _make_page_placeholder(self, title: str) -> QWidget:
        placeholder = QWidget()
        layout = QVBoxLayout(placeholder)
        layout.setContentsMargins(24, 24, 24, 24)
        label = QLabel(f"正在准备 {title} 页面")
        label.setObjectName("Muted")
        label.setAlignment(Qt.AlignCenter)
        layout.addStretch(1)
        layout.addWidget(label)
        layout.addStretch(1)
        return placeholder

    def _create_file_manager_page(self) -> QWidget:
        from .pages.file_manager.page import FileManagerPage

        page = FileManagerPage(self.runner, self.device_bar)
        self.file_manager_page = page
        return page

    def open_page_by_title(self, title: str) -> bool:
        for row in range(self.nav.count()):
            item = self.nav.item(row)
            if item is not None and item.text() == title:
                self.nav.setCurrentRow(row)
                return True
        return False
