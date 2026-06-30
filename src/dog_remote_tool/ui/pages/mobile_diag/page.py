from __future__ import annotations

from PyQt5.QtCore import QProcess, QTimer
from PyQt5.QtWidgets import QLabel

from dog_remote_tool.core.shell import CommandSpec
from dog_remote_tool.core.runner import ProcessRunner
from dog_remote_tool.modules import mobile_diag
from dog_remote_tool.ui.components import CommandPage, DeviceBar
from dog_remote_tool.ui.label_status import set_label_text_style
from dog_remote_tool.ui.pages.mobile_diag.layout import MobileDiagLayoutMixin
from dog_remote_tool.ui.process_utils import ProcessSlot
from dog_remote_tool.ui.status_text import task_not_started_text
from dog_remote_tool.ui.widget_roles import set_widget_text_tooltip


NOTICE_PENDING_STYLE = "color:#8a5a00; font-weight:700;"


class MobileDiagPage(MobileDiagLayoutMixin, CommandPage):
    def __init__(self, runner: ProcessRunner, device_bar: DeviceBar) -> None:
        super().__init__("诊断监控", runner, device_bar)
        self.perf_slot = ProcessSlot(self, reserve_runner=False)
        self.perf_values: dict[str, QLabel] = {}
        self.perf_details: dict[str, QLabel] = {}
        self.top_cpu_rows: list[tuple[QLabel, QLabel, QLabel, QLabel]] = []
        self.cpu_module_rows: list[tuple[QLabel, QLabel, QLabel]] = []
        self.top_cpu_hint = QLabel("")
        self.joint_temp_cells: dict[str, QLabel] = {}
        self.joint_temp_status = QLabel("")

        self.body.addWidget(self._build_realtime_panel())
        self.body.addWidget(self._build_performance_record_box())
        self.body.addWidget(self._build_ros_shm_box())
        self.body.addWidget(self._build_mobile_network_box())
        self.set_command(mobile_diag.performance_snapshot_command(self.profile()))
        self.page_active = False
        self.device_bar.profile_changed.connect(self._profile_changed)
        self._update_mobile_actions(self.profile())

    def record_performance_snapshot(self) -> bool:
        started = self.set_command(mobile_diag.performance_snapshot_command(self.profile()))
        if started is False:
            self._mark_performance_record_not_started("性能快照")
        return bool(started)

    def record_performance_sample(self) -> bool:
        started = self.set_command(mobile_diag.performance_sample_command(self.profile()))
        if started is False:
            self._mark_performance_record_not_started("30秒采样")
        return bool(started)

    def recover_mobile_network(self) -> bool:
        started = self.set_command(mobile_diag.recover_and_diag_command(self.profile()))
        if started is False:
            self._mark_mobile_action_not_started("网络恢复")
        return bool(started)

    def reboot_mobile_device(self) -> bool:
        started = self.set_command(mobile_diag.reboot_command(self.profile()))
        if started is False:
            self._mark_mobile_action_not_started("重启设备")
        return bool(started)

    def check_ros_shm(self) -> bool:
        started = self.set_command(mobile_diag.ros_shm_check_command(self.profile()))
        if started is False:
            self._mark_ros_shm_action_not_started("共享内存检查")
        return bool(started)

    def clean_ros_shm(self) -> bool:
        started = self.set_command(mobile_diag.ros_shm_cleanup_command(self.profile()))
        if started is False:
            self._mark_ros_shm_action_not_started("共享内存清理")
        return bool(started)

    def _mark_performance_record_not_started(self, action: str) -> None:
        set_label_text_style(self.perf_record_status, f"{action}：{task_not_started_text()}", NOTICE_PENDING_STYLE)

    def _mark_mobile_action_not_started(self, action: str) -> None:
        set_label_text_style(self.mobile_notice, f"{action}：{task_not_started_text()}", NOTICE_PENDING_STYLE)

    def _mark_ros_shm_action_not_started(self, action: str) -> None:
        set_label_text_style(self.ros_shm_notice, f"{action}：{task_not_started_text()}", NOTICE_PENDING_STYLE)

    def _update_mobile_actions(self, profile) -> None:
        supported = "5g" in profile.capabilities
        self.perf_target.setText(profile.label)
        self.recover_btn.setEnabled(supported)
        self.reboot_btn.setEnabled(supported)
        if supported:
            set_label_text_style(self.mobile_notice, f"当前目标：{profile.label}", "")
            self.recover_btn.setToolTip("启用并重启 quectel-cm 服务，然后执行完整 4G/5G 诊断。")
            self.reboot_btn.setToolTip("服务恢复无效时再重启远端 3588 端。")
        else:
            set_label_text_style(
                self.mobile_notice,
                f"当前目标 {profile.label} 不支持 4G/5G 诊断，但仍可执行性能监控。请切换到小狗一代 3588、小狗二代 3588 或中狗 3588 后再诊断蜂窝网络。",
                "",
            )
            self.recover_btn.setToolTip("当前设备未配置 4G/5G 拨号服务。")
            self.reboot_btn.setToolTip("当前设备不是 4G/5G 诊断目标。")

    def _profile_changed(self, profile) -> None:
        self.perf_slot.stop()
        self._update_mobile_actions(profile)
        if self.page_active:
            self.refresh_performance_status()

    def refresh_performance_status(self) -> bool:
        if not self.page_active:
            return False
        if self.perf_slot.is_running():
            return False
        profile = self.profile()
        process, request_id = self.perf_slot.start_spec(
            CommandSpec(
                "刷新性能探针",
                mobile_diag.performance_probe_command(profile),
                concurrency="parallel",
                locks=("mobile-diag-performance",),
            ),
            login_shell=False,
        )
        if process is None:
            return False
        process.readyReadStandardOutput.connect(lambda: self._read_perf_output(process, request_id))
        process.finished.connect(lambda exit_code, _status: self._perf_finished(process, request_id, profile, exit_code))
        process.start()
        return True

    def _read_perf_output(self, process: QProcess, request_id: int) -> bool:
        return self.perf_slot.read_available_output(process, request_id)

    def _perf_finished(self, process: QProcess, request_id: int, profile, exit_code: int) -> bool:
        output = self.perf_slot.finish(process, request_id)
        if output is None:
            return False
        if exit_code != 0:
            for label in self.perf_values.values():
                label.setText("读取失败")
            for label in self.perf_details.values():
                label.setText("检查 SSH 或目标设备状态")
            for name, pid, cpu, total_cpu in self.top_cpu_rows:
                name.setText("读取失败")
                pid.setText("--")
                cpu.setText("--")
                total_cpu.setText("--")
            for name, cpu, total_cpu in self.cpu_module_rows:
                name.setText("读取失败")
                cpu.setText("--")
                total_cpu.setText("--")
            self.joint_temp_status.setText("读取失败")
            for label in self.joint_temp_cells.values():
                label.setText("--")
            return True
        values = mobile_diag.parse_performance_probe_output(output)
        self.perf_values["load"].setText(values.get("LOAD_1", "--"))
        self.perf_details["load"].setText(f"5m {values.get('LOAD_5', '--')} / 15m {values.get('LOAD_15', '--')}")
        mem_total = mobile_diag.probe_float(values.get("MEM_TOTAL_MB"))
        mem_used = mobile_diag.probe_float(values.get("MEM_USED_MB"))
        mem_avail = mobile_diag.probe_float(values.get("MEM_AVAILABLE_MB"))
        if mem_total:
            mem_percent = mem_used / mem_total * 100 if mem_used is not None else 0
            self.perf_values["mem"].setText(f"{mem_percent:.1f}%")
            self.perf_details["mem"].setText(f"{mem_used:.0f}/{mem_total:.0f} MB  avail {mem_avail or 0:.0f} MB")
        else:
            self.perf_values["mem"].setText("--")
            self.perf_details["mem"].setText("未读取到内存信息")
        swap_total = mobile_diag.probe_float(values.get("SWAP_TOTAL_MB"))
        swap_used = mobile_diag.probe_float(values.get("SWAP_USED_MB"))
        if swap_total and swap_total > 0:
            self.perf_values["swap"].setText(f"{(swap_used or 0) / swap_total * 100:.1f}%")
            self.perf_details["swap"].setText(f"{swap_used or 0:.0f}/{swap_total:.0f} MB")
        else:
            self.perf_values["swap"].setText("0%")
            self.perf_details["swap"].setText("未启用")
        self._update_ros_shm_metric(values)
        cpu_idle = values.get("CPU_IDLE") or values.get("CPU_IDLE_VMSTAT", "--")
        cpu_used = values.get("CPU_USED")
        if cpu_used is None:
            idle_value = mobile_diag.probe_float(cpu_idle)
            cpu_used = f"{100 - idle_value:.1f}" if idle_value is not None else "--"
        cpu_ni = values.get("CPU_NI", "--")
        cpu_cores = values.get("CPU_CORES", "--")
        self.perf_values["cpu_idle"].setText(mobile_diag.format_probe_percent(cpu_idle))
        self.perf_details["cpu_idle"].setText(
            f"使用 {mobile_diag.format_probe_percent(cpu_used)} / ni {mobile_diag.format_probe_percent(cpu_ni)} / {cpu_cores}核"
        )
        self.perf_values["io"].setText(f"{values.get('IO_BI', '--')} / {values.get('IO_BO', '--')}")
        self.perf_details["io"].setText("bi / bo blocks/s")
        temp_source = values.get("CUR_TEMP_SOURCE", profile.label)
        temp_main = values.get("CUR_TEMP_MAIN")
        temp_gpu = values.get("CUR_TEMP_GPU")
        if not temp_main or temp_main == "--":
            temp_source = values.get("BASE_TEMP_SOURCE", temp_source)
            temp_main = values.get("BASE_TEMP_MAIN")
            temp_gpu = values.get("BASE_TEMP_GPU")
        self.perf_values["temp_current"].setText(mobile_diag.format_probe_temp(temp_main))
        self.perf_details["temp_current"].setText(
            f"{temp_source}  GPU {mobile_diag.format_probe_temp(temp_gpu)}"
        )
        self._update_joint_temperatures(values)
        self.perf_values["top_mem"].setText(values.get("TOP_MEM_PROC", "--"))
        self.perf_details["top_mem"].setText(f"{values.get('TOP_MEM_PERCENT', '--')}% MEM")
        self._update_top_cpu_rows(values)
        self._update_cpu_module_rows(values)
        suffix = values.get("TIME", "--")
        for label in [*self.perf_values.values(), *self.perf_details.values()]:
            label.setToolTip(f"最近检测：{suffix}")
        return True

    def _update_ros_shm_metric(self, values: dict[str, str]) -> None:
        shm_total = mobile_diag.probe_float(values.get("SHM_TOTAL_MB"))
        shm_used = mobile_diag.probe_float(values.get("SHM_USED_MB"))
        shm_percent = mobile_diag.probe_float(values.get("SHM_USE_PERCENT"))
        zenoh_count = values.get("SHM_ZENOH_COUNT", "--")
        zenoh_big_count = values.get("SHM_ZENOH_256M_COUNT", "--")
        tool_count = values.get("SHM_DOG_REMOTE_HELPER_COUNT", "--")
        if shm_total and shm_percent is not None:
            self.perf_values["ros_shm"].setText(f"{shm_percent:.1f}%")
            detail = f"{shm_used or 0:.0f}/{shm_total:.0f} MB  通信文件 {zenoh_count} / 256M {zenoh_big_count}"
            if tool_count not in {"", "--", "0"}:
                detail += f"  工具 {tool_count}"
            self.perf_details["ros_shm"].setText(detail)
        else:
            self.perf_values["ros_shm"].setText("--")
            self.perf_details["ros_shm"].setText("未读取到 /dev/shm")

    def _update_top_cpu_rows(self, values: dict[str, str]) -> None:
        cores = values.get("CPU_CORES", "--")
        self.top_cpu_hint.setText(f"前 6 个进程 / {cores}核")
        for index, (name_label, pid_label, cpu_label, total_cpu_label) in enumerate(self.top_cpu_rows, start=1):
            process_name = values.get(f"TOP_CPU_{index}_PROC", "--")
            pid = values.get(f"TOP_CPU_{index}_PID", "--")
            cpu = values.get(f"TOP_CPU_{index}_PERCENT", "--")
            total_cpu = values.get(f"TOP_CPU_{index}_TOTAL_PERCENT", "--")
            mem = values.get(f"TOP_CPU_{index}_MEM", "--")
            cpu_text = mobile_diag.format_probe_percent(cpu)
            total_cpu_text = mobile_diag.format_probe_percent(total_cpu)
            set_widget_text_tooltip(name_label, f"{index}. {process_name}", f"{process_name}  MEM {mem}%")
            set_widget_text_tooltip(pid_label, pid, f"{process_name}  PID {pid}")
            set_widget_text_tooltip(cpu_label, cpu_text, f"{process_name}  top 单核口径 {cpu_text} / MEM {mem}%")
            set_widget_text_tooltip(total_cpu_label, total_cpu_text, f"{process_name}  htop 整机口径 {total_cpu_text}")

    def _update_cpu_module_rows(self, values: dict[str, str]) -> None:
        for index, (name_label, cpu_label, total_cpu_label) in enumerate(self.cpu_module_rows, start=1):
            module_name = values.get(f"CPU_MODULE_{index}_NAME", "--")
            top_cpu = values.get(f"CPU_MODULE_{index}_TOP_PERCENT", "--")
            total_cpu = values.get(f"CPU_MODULE_{index}_TOTAL_PERCENT", "--")
            top_cpu_text = mobile_diag.format_probe_percent(top_cpu)
            total_cpu_text = mobile_diag.format_probe_percent(total_cpu)
            tooltip = f"{module_name}  top 单核口径 {top_cpu_text} / htop 整机口径 {total_cpu_text}"
            set_widget_text_tooltip(name_label, module_name, tooltip)
            set_widget_text_tooltip(cpu_label, top_cpu_text, tooltip)
            set_widget_text_tooltip(total_cpu_label, total_cpu_text, tooltip)

    def _update_joint_temperatures(self, values: dict[str, str]) -> None:
        source = values.get("BASE_TEMP_SOURCE") or values.get("CUR_TEMP_SOURCE") or "3588"
        available = values.get("JOINT_AVAILABLE")
        if available == "1":
            max_temp = values.get("JOINT_MAX_TEMP", "--")
            max_name = values.get("JOINT_MAX_NAME", "--")
            self.perf_values["joint_max"].setText(mobile_diag.format_probe_temp(max_temp))
            self.perf_details["joint_max"].setText(f"{source}  {max_name}")
            self.joint_temp_status.setText(source)
        else:
            error = values.get("JOINT_ERROR", "未读取到关节共享内存")
            self.perf_values["joint_max"].setText("--")
            self.perf_details["joint_max"].setText(error)
            self.joint_temp_status.setText(error)

        for key, label in self.joint_temp_cells.items():
            temp = values.get(f"JOINT_{key}_TEMP", "--")
            over_temp = values.get(f"JOINT_{key}_OVER_TEMP") == "1"
            label.setText(mobile_diag.format_probe_temp(temp, mark=over_temp))

    def activate_page(self) -> None:
        if self.page_active:
            return
        self.page_active = True
        QTimer.singleShot(300, self.refresh_performance_status)

    def deactivate_page(self) -> None:
        self._stop_performance_polling()

    def shutdown_processes(self) -> None:
        self._stop_performance_polling()

    def _stop_performance_polling(self) -> None:
        self.page_active = False
        self.perf_slot.stop()
