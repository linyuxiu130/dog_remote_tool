from __future__ import annotations

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QTableWidget,
    QHeaderView,
    QVBoxLayout,
    QWidget,
)

from dog_remote_tool.modules import bag
from dog_remote_tool.ui.pages.bag.layout_sections import BagLayoutSectionsMixin


class BagLayoutMixin(BagLayoutSectionsMixin):
    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(12)

        root.addWidget(self._build_page_header())

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        content = QWidget()
        content.setMinimumWidth(0)
        scroll.setWidget(content)
        body = QVBoxLayout(content)
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(12)
        root.addWidget(scroll, 1)

        config_box = self._build_record_config_box()
        remote_box = self._build_remote_bag_box()
        body.addWidget(config_box)
        body.addWidget(self._build_record_status_box())
        body.addWidget(self._build_topic_panel(), 1)
        body.addWidget(remote_box, 1)

    def _build_record_config_box(self) -> QFrame:
        config_box = QFrame()
        config_box.setObjectName("AdvancedDetails")
        config_layout = QVBoxLayout(config_box)
        config_layout.setContentsMargins(0, 0, 0, 0)
        config_layout.setSpacing(8)
        self.record_config_toggle = QPushButton("录制设置")
        self.record_config_toggle.setObjectName("AdvancedDetailsToggle")
        self.record_config_toggle.setCheckable(True)
        config_layout.addWidget(self.record_config_toggle)
        config_content = QWidget()
        config_grid = QGridLayout(config_content)
        config_grid.setHorizontalSpacing(10)
        config_grid.setVerticalSpacing(7)
        config_grid.setColumnStretch(0, 3)
        config_grid.setColumnStretch(1, 3)
        config_grid.setColumnStretch(2, 1)
        config_grid.setColumnStretch(3, 1)
        config_grid.setColumnStretch(4, 1)
        self.remote_path = QLineEdit()
        self.remote_path.setMinimumWidth(0)
        self.storage_combo = QComboBox()
        self.storage_combo.addItems(["mcap", "sqlite3"])
        self.cache_spin = QSpinBox()
        self.cache_spin.setRange(1, 10)
        self.cache_spin.setValue(5)
        self.local_dir = QLineEdit(bag.DEFAULT_LOCAL_BAG_DIR)
        self.local_dir.setMinimumWidth(0)
        choose_local = QPushButton("选择目录")
        choose_local.clicked.connect(self.choose_local_dir)
        local_row = QHBoxLayout()
        local_row.setContentsMargins(0, 0, 0, 0)
        local_row.addWidget(self.local_dir, 1)
        local_row.addWidget(choose_local)
        self.auto_pull_after_record = QPushButton("自动回传")
        self.auto_pull_after_record.setObjectName("AutoTransferToggle")
        self.auto_pull_after_record.setCheckable(True)
        self.auto_pull_after_record.setToolTip("停止录制并收尾成功后自动回传当前 Bag，不再弹窗询问")
        self.auto_pull_after_record.setChecked(
            self.settings.value(self.AUTO_PULL_AFTER_RECORD_KEY, False, type=bool)
        )
        self._update_auto_pull_after_record_text(self.auto_pull_after_record.isChecked())
        self.auto_pull_after_record.toggled.connect(self._save_auto_pull_after_record)
        self.auto_pull_after_record.setMinimumWidth(116)
        remote_label = QLabel("远端保存路径")
        remote_label.setObjectName("FieldLabel")
        local_label = QLabel("本地回传目录")
        local_label.setObjectName("FieldLabel")
        finish_label = QLabel("录制结束")
        finish_label.setObjectName("FieldLabel")
        format_label = QLabel("格式")
        format_label.setObjectName("FieldLabel")
        cache_label = QLabel("缓存(GB)")
        cache_label.setObjectName("FieldLabel")
        config_grid.addWidget(remote_label, 0, 0)
        config_grid.addWidget(local_label, 0, 1)
        config_grid.addWidget(finish_label, 0, 2)
        config_grid.addWidget(format_label, 0, 3)
        config_grid.addWidget(cache_label, 0, 4)
        config_grid.addWidget(self.remote_path, 1, 0)
        config_grid.addLayout(local_row, 1, 1)
        config_grid.addWidget(self.auto_pull_after_record, 1, 2)
        config_grid.addWidget(self.storage_combo, 1, 3)
        config_grid.addWidget(self.cache_spin, 1, 4)
        config_content.hide()
        config_layout.addWidget(config_content)
        self.record_config_toggle.toggled.connect(config_content.setVisible)
        self.record_config_toggle.toggled.connect(
            lambda checked: self.record_config_toggle.setText("收起录制设置" if checked else "录制设置")
        )
        return config_box

    def _build_remote_bag_box(self) -> QGroupBox:
        remote_box = QGroupBox("远端 Bag 管理")
        remote_layout = QVBoxLayout(remote_box)
        remote_header = QHBoxLayout()
        self.remote_space_label = QLabel("可用空间: 未知")
        self.remote_space_label.setObjectName("FieldLabel")
        self.remote_status_label = QLabel("未刷新")
        self.remote_status_label.setObjectName("FieldLabel")
        refresh = QPushButton("刷新")
        refresh.setMinimumWidth(72)
        refresh.clicked.connect(lambda: self.refresh_remote_bags(auto=False))
        remote_header.addWidget(self.remote_space_label)
        remote_header.addStretch(1)
        remote_header.addWidget(self.remote_status_label)
        remote_header.addWidget(refresh)
        remote_layout.addLayout(remote_header)
        self.remote_table = QTableWidget(0, 5)
        self.remote_table.setHorizontalHeaderLabels(["状态", "时间", "大小", "名称", "路径"])
        self.remote_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.remote_table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.remote_table.setAlternatingRowColors(True)
        self.remote_table.verticalHeader().setVisible(False)
        self.remote_table.verticalHeader().setDefaultSectionSize(32)
        self.remote_table.horizontalHeader().setStretchLastSection(True)
        remote_header_view = self.remote_table.horizontalHeader()
        remote_header_view.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        remote_header_view.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        remote_header_view.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        remote_header_view.setSectionResizeMode(3, QHeaderView.Stretch)
        remote_header_view.setSectionResizeMode(4, QHeaderView.Stretch)
        self.remote_table.setMinimumHeight(220)
        self.remote_table.itemSelectionChanged.connect(self._update_resume_button)
        remote_layout.addWidget(self.remote_table, 1)
        remote_buttons = QHBoxLayout()
        remote_buttons.setContentsMargins(0, 10, 0, 0)
        remote_buttons.setSpacing(12)
        self.pull_selected_btn = QPushButton("回传 Bag")
        self.pull_selected_btn.setObjectName("SoftPrimary")
        self.pull_selected_btn.clicked.connect(self.pull_selected_remote_bags)
        self.pull_runtime_log_btn = QPushButton("运行 Log")
        self.pull_runtime_log_btn.setObjectName("SoftPrimary")
        self.pull_runtime_log_btn.clicked.connect(self.pull_runtime_log_only)
        self.pull_ros_log_btn = QPushButton("ROS Log")
        self.pull_ros_log_btn.setObjectName("SoftPrimary")
        self.pull_ros_log_btn.clicked.connect(self.pull_ros_log_only)
        self.delete_selected_btn = QPushButton("删除选中")
        self.delete_selected_btn.setObjectName("SoftDanger")
        self.delete_selected_btn.clicked.connect(self.delete_selected_remote_bags)
        for button in (self.pull_selected_btn, self.pull_runtime_log_btn, self.pull_ros_log_btn, self.delete_selected_btn):
            button.setMinimumWidth(132)
            button.setMinimumHeight(44)
            button.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        remote_buttons.addStretch(1)
        remote_buttons.addWidget(self.pull_selected_btn)
        remote_buttons.addWidget(self.pull_runtime_log_btn)
        remote_buttons.addWidget(self.pull_ros_log_btn)
        remote_buttons.addWidget(self.delete_selected_btn)
        remote_layout.addLayout(remote_buttons)
        return remote_box
