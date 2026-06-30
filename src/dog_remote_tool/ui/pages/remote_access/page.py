from __future__ import annotations

from PyQt5 import QtWidgets
from PyQt5.QtCore import QTimer

from dog_remote_tool.core.runner import ProcessRunner
from dog_remote_tool.modules import remote_access
from dog_remote_tool.ui.components import CommandPage, DeviceBar
from dog_remote_tool.ui.pages.remote_access.actions import RemoteAccessActionsMixin
from dog_remote_tool.ui.pages.remote_access.dialogs import RemoteAccessDialogMixin
from dog_remote_tool.ui.pages.remote_access.layout import RemoteAccessLayoutMixin
from dog_remote_tool.ui.pages.remote_access.lifecycle import RemoteAccessLifecycleMixin
from dog_remote_tool.ui.pages.remote_access.public_status import RemoteAccessPublicStatusMixin
from dog_remote_tool.ui.pages.remote_access.wifi_status import RemoteAccessWifiStatusMixin
from dog_remote_tool.ui.process_utils import ProcessSlot

QFileDialog = QtWidgets.QFileDialog
QInputDialog = QtWidgets.QInputDialog
QLineEdit = QtWidgets.QLineEdit


class RemoteAccessPage(
    RemoteAccessDialogMixin,
    RemoteAccessLifecycleMixin,
    RemoteAccessPublicStatusMixin,
    RemoteAccessWifiStatusMixin,
    RemoteAccessActionsMixin,
    RemoteAccessLayoutMixin,
    CommandPage,
):
    def __init__(self, runner: ProcessRunner, device_bar: DeviceBar) -> None:
        super().__init__("远程访问与公网映射", runner, device_bar)
        self.public_state = "unknown"
        self.public_status_slot = ProcessSlot(self, reserve_runner=False)
        self.public_ssid_slot = ProcessSlot(self, reserve_runner=False)
        self.wifi_status_slot = ProcessSlot(self, reserve_runner=False)
        self.wifi_scan_slot = ProcessSlot(self, reserve_runner=False)
        self.wifi_connect_slot = ProcessSlot(self)
        self.public_status_shutdown = False

        self.body.addWidget(self._build_wifi_box())
        self.body.addWidget(self._build_public_access_box())
        self.body.addWidget(self._build_maintenance_box())

        self.set_command(remote_access.status_command(self.profile()))
        self.page_active = False
        self.runner.finished.connect(lambda _code: self.schedule_public_status_refresh(800))
        self.device_bar.profile_changed.connect(self._profile_changed)
        self._refresh_wifi_controls()
