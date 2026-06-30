from __future__ import annotations

from PyQt5.QtWidgets import (
    QComboBox,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from dog_remote_tool.modules import remote_access
from dog_remote_tool.modules.remote_access import frp


STATUS_INFO = "color:#607085; font-weight:700;"
STATUS_PENDING = "color:#8a5a00; font-weight:700;"
STATUS_ACTIVE = "color:#1f6fc9; font-weight:700;"
STATUS_OK = "color:#167c3f; font-weight:700;"
STATUS_ERROR = "color:#c84444; font-weight:700;"


class RemoteAccessLayoutMixin:
    def _build_wifi_box(self) -> QGroupBox:
        wifi_box = QGroupBox("1. 联网准备")
        wifi_layout = QVBoxLayout(wifi_box)
        wifi_layout.setSpacing(8)

        wifi_row = QHBoxLayout()
        self.wifi_combo = QComboBox()
        self.wifi_combo.setMinimumWidth(220)
        self.wifi_combo.setEditable(False)
        self.wifi_scan_btn = QPushButton("刷新 WiFi")
        self.wifi_scan_btn.clicked.connect(self.scan_wifi_networks)
        self.wifi_connect_btn = QPushButton("连接")
        self.wifi_connect_btn.setObjectName("Primary")
        self.wifi_connect_btn.clicked.connect(self.connect_selected_wifi)
        self.wifi_status = QLabel("WiFi状态：未检测")
        self.wifi_status.setMinimumWidth(320)
        self.wifi_status.setStyleSheet(STATUS_INFO)
        wifi_row.addWidget(self.wifi_scan_btn)
        wifi_row.addWidget(QLabel("SSID"))
        wifi_row.addWidget(self.wifi_combo)
        wifi_row.addWidget(self.wifi_connect_btn)
        wifi_row.addWidget(self.wifi_status)
        wifi_row.addStretch(1)

        prep_row = QHBoxLayout()
        internet_btn = QPushButton("检查外网")
        internet_btn.setObjectName("SoftPrimary")
        internet_btn.clicked.connect(lambda: self.run_remote_access_command(remote_access.internet_check_command(self.profile())))
        prep_row.addWidget(internet_btn)
        prep_row.addStretch(1)

        wifi_more = QFrame()
        wifi_more.setObjectName("AdvancedDetails")
        wifi_more_layout = QVBoxLayout(wifi_more)
        wifi_more_layout.setContentsMargins(0, 0, 0, 0)
        wifi_more_layout.setSpacing(8)
        wifi_more_toggle = QPushButton("联网详情")
        wifi_more_toggle.setObjectName("AdvancedDetailsToggle")
        wifi_more_toggle.setCheckable(True)
        wifi_more_content = QWidget()
        wifi_more_content_layout = QHBoxLayout(wifi_more_content)
        wifi_more_content_layout.setContentsMargins(0, 0, 0, 0)
        status_btn = QPushButton("查看进程")
        status_btn.clicked.connect(lambda: self.run_remote_access_command(remote_access.status_command(self.profile())))
        wifi_more_content_layout.addWidget(status_btn)
        wifi_more_content_layout.addStretch(1)
        wifi_more_content.hide()
        wifi_more_toggle.toggled.connect(wifi_more_content.setVisible)
        wifi_more_toggle.toggled.connect(lambda checked: wifi_more_toggle.setText("收起联网详情" if checked else "联网详情"))
        wifi_more_layout.addWidget(wifi_more_toggle)
        wifi_more_layout.addWidget(wifi_more_content)

        self.remote_command_status = QLabel("")
        self.remote_command_status.setObjectName("Muted")
        self.remote_command_status.setWordWrap(True)
        wifi_layout.addLayout(wifi_row)
        wifi_layout.addLayout(prep_row)
        wifi_layout.addWidget(wifi_more)
        wifi_layout.addWidget(self.remote_command_status)
        return wifi_box

    def _build_public_access_box(self) -> QGroupBox:
        public_box = QGroupBox("2. 启动远程访问")
        public_grid = QGridLayout(public_box)
        public_grid.setHorizontalSpacing(8)
        public_grid.setVerticalSpacing(8)

        self.public_ssid = QLineEdit(remote_access.DEFAULT_PUBLIC_SSID)
        self.public_ssid.setMinimumWidth(180)
        self.public_ssid.setPlaceholderText("3588 自身热点名")
        self.public_status = QLabel("公网状态：检测中")
        self.public_status.setMinimumWidth(300)
        detect_ssid = QPushButton("读取3588热点名")
        detect_ssid.clicked.connect(self.refresh_public_ssid)
        sync_files = QPushButton("同步脚本和程序")
        sync_files.setObjectName("SoftPrimary")
        sync_files.clicked.connect(
            lambda: self.run_remote_access_command(remote_access.sync_remote_access_files_command(self.profile()))
        )
        self.public_button = QPushButton("打开公网连接")
        self.public_button.setObjectName("Primary")
        self.public_button.clicked.connect(self.run_public_access_action)
        verify_public = QPushButton("公网SSH测试")
        verify_public.setObjectName("SoftPrimary")
        verify_public.clicked.connect(lambda: self.run_remote_access_command(frp.external_ssh_command(self.profile())))

        public_grid.addWidget(QLabel("3588热点SSID"), 0, 0)
        public_grid.addWidget(self.public_ssid, 0, 1)
        public_grid.addWidget(self.public_status, 0, 2, 1, 2)
        public_grid.addWidget(self.public_button, 1, 0, 1, 2)
        public_more = QFrame()
        public_more.setObjectName("AdvancedDetails")
        public_more_layout = QVBoxLayout(public_more)
        public_more_layout.setContentsMargins(0, 0, 0, 0)
        public_more_layout.setSpacing(8)
        public_more_toggle = QPushButton("远程访问详情")
        public_more_toggle.setObjectName("AdvancedDetailsToggle")
        public_more_toggle.setCheckable(True)
        public_more_content = QWidget()
        public_more_content_layout = QHBoxLayout(public_more_content)
        public_more_content_layout.setContentsMargins(0, 0, 0, 0)
        public_more_content_layout.setSpacing(8)
        public_more_content_layout.addWidget(detect_ssid)
        public_more_content_layout.addWidget(sync_files)
        public_more_content_layout.addWidget(verify_public)
        public_more_content_layout.addStretch(1)
        public_more_content.hide()
        public_more_toggle.toggled.connect(public_more_content.setVisible)
        public_more_toggle.toggled.connect(
            lambda checked: public_more_toggle.setText("收起远程访问详情" if checked else "远程访问详情")
        )
        public_more_layout.addWidget(public_more_toggle)
        public_more_layout.addWidget(public_more_content)
        public_grid.addWidget(public_more, 2, 0, 1, 4)
        public_grid.setColumnStretch(4, 1)
        return public_box

    def _build_maintenance_box(self) -> QFrame:
        box = QFrame()
        box.setObjectName("AdvancedDetails")
        layout = QVBoxLayout(box)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        toggle = QPushButton("维护操作")
        toggle.setObjectName("AdvancedDetailsToggle")
        toggle.setCheckable(True)
        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(10)
        content_layout.addWidget(self._build_frp_box())
        content_layout.addWidget(self._build_nx_access_box())
        content.hide()
        toggle.toggled.connect(content.setVisible)
        toggle.toggled.connect(lambda checked: toggle.setText("收起维护操作" if checked else "维护操作"))
        layout.addWidget(toggle)
        layout.addWidget(content)
        return box

    def _build_frp_box(self) -> QGroupBox:
        frp_box = QGroupBox("3. FRP 5G 公网映射")
        grid = QGridLayout(frp_box)
        grid.setHorizontalSpacing(8)
        grid.setVerticalSpacing(8)

        self.zip_path = QLineEdit(frp.LOCAL_FRP_ZIP)
        browse = QPushButton("选择 FRP 包")
        browse.clicked.connect(self.choose_zip)
        deploy = QPushButton("部署")
        deploy.clicked.connect(lambda: self.run_remote_access_command(frp.deploy_command(self.profile(), self.zip_path.text())))
        gen = QPushButton("申请端口")
        gen.clicked.connect(lambda: self.run_remote_access_command(frp.generate_config_command(self.profile())))
        start_bg = QPushButton("后台启动 frpc")
        start_bg.clicked.connect(lambda: self.run_remote_access_command(frp.start_frpc_background_command(self.profile())))
        auto = QPushButton("一键部署并启动")
        auto.setObjectName("Danger")
        auto.clicked.connect(
            lambda: self.run_remote_access_command(frp.auto_deploy_start_command(self.profile(), self.zip_path.text()))
        )
        frp_status = QPushButton("FRP 状态")
        frp_status.clicked.connect(lambda: self.run_remote_access_command(frp.frpc_status_command(self.profile())))

        grid.addWidget(QLabel("FRP 包"), 0, 0)
        grid.addWidget(self.zip_path, 0, 1, 1, 3)
        grid.addWidget(browse, 0, 4)
        grid.addWidget(auto, 1, 0)
        grid.addWidget(deploy, 1, 1)
        grid.addWidget(gen, 1, 2)
        grid.addWidget(start_bg, 1, 3)
        grid.addWidget(frp_status, 1, 4)
        grid.setColumnStretch(1, 1)
        return frp_box

    def _build_nx_access_box(self) -> QGroupBox:
        nx_box = QGroupBox("4. NX 联网远程控制")
        nx_grid = QGridLayout(nx_box)
        nx_grid.setHorizontalSpacing(8)
        nx_grid.setVerticalSpacing(8)

        self.community_deb_path = QLineEdit(remote_access.NX_COMMUNITY_NODE_DEB)
        deb_browse = QPushButton("选择 deb")
        deb_browse.clicked.connect(self.choose_community_deb)
        install_node = QPushButton("安装 community-node")
        install_node.setObjectName("SoftPrimary")
        install_node.clicked.connect(
            lambda: self.run_remote_access_command(
                remote_access.install_community_node_command(self.profile(), self.community_deb_path.text())
            )
        )
        nx_status = QPushButton("查看 NX 状态")
        nx_status.clicked.connect(
            lambda: self.run_remote_access_command(remote_access.nx_robot_launch_status_command(self.profile()))
        )

        nx_grid.addWidget(QLabel("安装包"), 0, 0)
        nx_grid.addWidget(self.community_deb_path, 0, 1, 1, 3)
        nx_grid.addWidget(deb_browse, 0, 4)
        nx_grid.addWidget(install_node, 1, 0, 1, 2)
        nx_grid.addWidget(nx_status, 1, 2, 1, 2)
        return nx_box
