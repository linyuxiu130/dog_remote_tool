from __future__ import annotations

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QFrame, QGridLayout, QGroupBox, QHBoxLayout, QLabel, QPushButton, QSizePolicy, QVBoxLayout


class MobileDiagLayoutMixin:
    def _build_realtime_panel(self) -> QFrame:
        realtime_panel = QFrame()
        realtime_panel.setObjectName("Panel")
        realtime_layout = QVBoxLayout(realtime_panel)
        realtime_layout.setContentsMargins(12, 10, 12, 12)
        realtime_layout.setSpacing(10)

        header_row = QHBoxLayout()
        title = QLabel("实时性能")
        title.setObjectName("DiagSectionTitle")
        self.perf_target = QLabel("")
        self.perf_target.setObjectName("DiagTargetLabel")
        refresh_perf = QPushButton("立即刷新")
        refresh_perf.clicked.connect(self.refresh_performance_status)
        header_row.addWidget(title)
        header_row.addWidget(self.perf_target, 1)
        header_row.addWidget(refresh_perf)
        realtime_layout.addLayout(header_row)

        perf_content = QHBoxLayout()
        perf_content.setSpacing(10)
        perf_grid = QGridLayout()
        perf_grid.setHorizontalSpacing(10)
        perf_grid.setVerticalSpacing(10)
        for index, (key, label, detail) in enumerate(
            [
                ("load", "Load", "1 / 5 / 15 min"),
                ("mem", "Memory", "used / total / available"),
                ("swap", "Swap", "used / total"),
                ("ros_shm", "共享内存", "/dev/shm"),
                ("cpu_idle", "CPU 剩余", "used / ni / cores"),
                ("io", "IO", "bi / bo blocks/s"),
                ("temp_current", "系统温度", "main / GPU"),
                ("joint_max", "关节最高", "3588 shared memory"),
                ("top_mem", "Top Memory", "process / %MEM"),
            ]
        ):
            row = index // 3
            col = index % 3
            perf_grid.addWidget(self._metric_card(key, label, detail), row, col)
        perf_content.addLayout(perf_grid, 3)
        perf_content.addWidget(self._top_cpu_panel(), 2)
        realtime_layout.addLayout(perf_content)
        realtime_layout.addWidget(self._joint_temp_panel())
        return realtime_panel

    def _build_performance_record_box(self) -> QGroupBox:
        perf_box = QGroupBox("性能记录")
        perf_layout = QVBoxLayout(perf_box)
        perf_notice = QLabel("将当前性能快照或连续采样写入执行日志，用于复现和记录内存、Swap、Load、IO 异常。")
        perf_notice.setObjectName("Muted")
        perf_notice.setWordWrap(True)
        perf_layout.addWidget(perf_notice)
        self.perf_record_status = QLabel("")
        self.perf_record_status.setObjectName("Muted")
        perf_layout.addWidget(self.perf_record_status)
        perf_row = QHBoxLayout()
        snapshot_btn = QPushButton("性能快照")
        snapshot_btn.setObjectName("Primary")
        snapshot_btn.clicked.connect(self.record_performance_snapshot)
        sample_btn = QPushButton("30秒采样")
        sample_btn.clicked.connect(self.record_performance_sample)
        perf_row.addWidget(snapshot_btn)
        perf_row.addWidget(sample_btn)
        perf_row.addStretch(1)
        perf_layout.addLayout(perf_row)
        return perf_box

    def _build_ros_shm_box(self) -> QGroupBox:
        shm_box = QGroupBox("ROS 共享内存")
        shm_layout = QVBoxLayout(shm_box)
        shm_notice = QLabel("检查 /dev/shm 是否被 ROS 2 通信数据占满。清理只处理本工具创建的临时资源、当前用户 ROS 2 后台服务和未被进程占用的通信文件。")
        shm_notice.setObjectName("Muted")
        shm_notice.setWordWrap(True)
        shm_layout.addWidget(shm_notice)
        self.ros_shm_notice = QLabel("")
        self.ros_shm_notice.setObjectName("Muted")
        self.ros_shm_notice.setWordWrap(True)
        shm_layout.addWidget(self.ros_shm_notice)
        shm_row = QHBoxLayout()
        check_shm_btn = QPushButton("检查共享内存")
        check_shm_btn.setObjectName("Primary")
        check_shm_btn.clicked.connect(self.check_ros_shm)
        clean_shm_btn = QPushButton("清理临时资源")
        clean_shm_btn.setObjectName("Danger")
        clean_shm_btn.clicked.connect(self.clean_ros_shm)
        shm_row.addWidget(check_shm_btn)
        shm_row.addWidget(clean_shm_btn)
        shm_row.addStretch(1)
        shm_layout.addLayout(shm_row)
        return shm_box

    def _build_mobile_network_box(self) -> QGroupBox:
        box = QGroupBox("蜂窝网络模块（4G/5G）")
        box_layout = QVBoxLayout(box)
        self.mobile_notice = QLabel("")
        self.mobile_notice.setObjectName("Muted")
        self.mobile_notice.setWordWrap(True)
        box_layout.addWidget(self.mobile_notice)
        row = QHBoxLayout()
        self.recover_btn = QPushButton("检测并恢复网络服务")
        self.recover_btn.setObjectName("Primary")
        self.recover_btn.clicked.connect(self.recover_mobile_network)
        row.addWidget(self.recover_btn)
        self.reboot_btn = QPushButton("重启设备")
        self.reboot_btn.setObjectName("Danger")
        self.reboot_btn.clicked.connect(self.reboot_mobile_device)
        row.addWidget(self.reboot_btn)
        row.addStretch(1)
        box_layout.addLayout(row)
        return box

    def _metric_card(self, key: str, title: str, default_detail: str) -> QFrame:
        card = QFrame()
        card.setObjectName("PerfMetricCard")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(5)
        title_label = QLabel(title)
        title_label.setObjectName("PerfMetricTitle")
        value_label = QLabel("--")
        value_label.setObjectName("PerfMetricValue")
        value_label.setWordWrap(True)
        value_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        detail_label = QLabel(default_detail)
        detail_label.setObjectName("PerfMetricDetail")
        detail_label.setWordWrap(True)
        detail_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.perf_values[key] = value_label
        self.perf_details[key] = detail_label
        layout.addWidget(title_label)
        layout.addWidget(value_label, 1)
        layout.addWidget(detail_label)
        return card

    def _top_cpu_panel(self) -> QFrame:
        card = QFrame()
        card.setObjectName("TopCpuCard")
        card.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(7)

        header = QHBoxLayout()
        title = QLabel("Top CPU")
        title.setObjectName("PerfMetricTitle")
        self.top_cpu_hint = QLabel("前 6 个进程")
        self.top_cpu_hint.setObjectName("PerfMetricDetail")
        header.addWidget(title)
        header.addStretch(1)
        header.addWidget(self.top_cpu_hint)
        layout.addLayout(header)

        column_header = QHBoxLayout()
        for label, stretch in (("进程", 4), ("PID", 1), ("单核", 1), ("整机", 1)):
            text = QLabel(label)
            text.setObjectName("TopCpuHeader")
            column_header.addWidget(text, stretch)
        layout.addLayout(column_header)

        for rank in range(1, 7):
            row = QFrame()
            row.setObjectName("TopCpuRow")
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(8, 5, 8, 5)
            row_layout.setSpacing(8)
            name = QLabel(f"{rank}. --")
            name.setObjectName("TopCpuName")
            name.setTextInteractionFlags(Qt.TextSelectableByMouse)
            pid = QLabel("--")
            pid.setObjectName("PerfMetricDetail")
            pid.setAlignment(Qt.AlignCenter)
            cpu = QLabel("--")
            cpu.setObjectName("TopCpuValue")
            cpu.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            total_cpu = QLabel("--")
            total_cpu.setObjectName("TopCpuTotalValue")
            total_cpu.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            row_layout.addWidget(name, 4)
            row_layout.addWidget(pid, 1)
            row_layout.addWidget(cpu, 1)
            row_layout.addWidget(total_cpu, 1)
            layout.addWidget(row)
            self.top_cpu_rows.append((name, pid, cpu, total_cpu))

        module_title = QHBoxLayout()
        module_label = QLabel("模块占比")
        module_label.setObjectName("PerfMetricTitle")
        module_hint = QLabel("按进程名聚合")
        module_hint.setObjectName("PerfMetricDetail")
        module_title.addWidget(module_label)
        module_title.addStretch(1)
        module_title.addWidget(module_hint)
        layout.addLayout(module_title)

        module_header = QHBoxLayout()
        for label, stretch in (("模块", 3), ("单核", 1), ("整机", 1)):
            text = QLabel(label)
            text.setObjectName("TopCpuHeader")
            module_header.addWidget(text, stretch)
        layout.addLayout(module_header)

        for _rank in range(1, 7):
            row = QFrame()
            row.setObjectName("TopCpuRow")
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(8, 5, 8, 5)
            row_layout.setSpacing(8)
            name = QLabel("--")
            name.setObjectName("TopCpuName")
            top_cpu = QLabel("--")
            top_cpu.setObjectName("TopCpuValue")
            top_cpu.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            total_cpu = QLabel("--")
            total_cpu.setObjectName("TopCpuTotalValue")
            total_cpu.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            row_layout.addWidget(name, 3)
            row_layout.addWidget(top_cpu, 1)
            row_layout.addWidget(total_cpu, 1)
            layout.addWidget(row)
            self.cpu_module_rows.append((name, top_cpu, total_cpu))
        return card

    def _joint_temp_panel(self) -> QFrame:
        card = QFrame()
        card.setObjectName("JointTempCard")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(7)

        header = QHBoxLayout()
        title = QLabel("关节温度")
        title.setObjectName("PerfMetricTitle")
        self.joint_temp_status = QLabel("等待读取")
        self.joint_temp_status.setObjectName("PerfMetricDetail")
        header.addWidget(title)
        header.addStretch(1)
        header.addWidget(self.joint_temp_status)
        layout.addLayout(header)

        grid = QGridLayout()
        grid.setHorizontalSpacing(8)
        grid.setVerticalSpacing(6)
        headers = ["腿位", "侧摆", "髋", "膝"]
        for col, text in enumerate(headers):
            label = QLabel(text)
            label.setObjectName("TopCpuHeader")
            label.setAlignment(Qt.AlignCenter)
            grid.addWidget(label, 0, col)

        legs = [("RF", "右前"), ("LF", "左前"), ("RR", "右后"), ("LR", "左后")]
        joints = [("ABAD", "侧摆"), ("HIP", "髋"), ("KNEE", "膝")]
        for row, (leg_key, leg_name) in enumerate(legs, start=1):
            leg_label = QLabel(leg_name)
            leg_label.setObjectName("TopCpuName")
            grid.addWidget(leg_label, row, 0)
            for col, (joint_key, _joint_name) in enumerate(joints, start=1):
                value = QLabel("--")
                value.setObjectName("JointTempValue")
                value.setAlignment(Qt.AlignCenter)
                value.setTextInteractionFlags(Qt.TextSelectableByMouse)
                self.joint_temp_cells[f"{leg_key}_{joint_key}"] = value
                grid.addWidget(value, row, col)
        layout.addLayout(grid)
        return card
