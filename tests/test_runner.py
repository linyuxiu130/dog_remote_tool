from PyQt5.QtCore import QCoreApplication, QProcess

from dog_remote_tool.core import failure_reasons
from dog_remote_tool.core import runner as runner_module
from dog_remote_tool.core.log_filter import compact_output, compact_technical_output, compact_user_output, failure_summary, redact_sensitive
from dog_remote_tool.core import log_filter
from dog_remote_tool.core.shell import CommandSpec
from dog_remote_tool.core.runner import ProcessRunner, RunningTask


class _FakeFinishedProcess:
    def __init__(self, output: bytes):
        self.output = output
        self.deleted = False

    def state(self):
        return QProcess.NotRunning

    def readAllStandardOutput(self):
        output = self.output
        self.output = b""
        return output

    def waitForReadyRead(self, _timeout):
        return False

    def deleteLater(self):
        self.deleted = True


class _FakeChunkProcess:
    def __init__(self, chunks: list[bytes]):
        self.chunks = chunks

    def state(self):
        return QProcess.Running

    def readAllStandardOutput(self):
        if not self.chunks:
            return b""
        return self.chunks.pop(0)


class _FakeRunningProcess:
    def __init__(self):
        self.terminated = False
        self.killed = False

    def state(self):
        return QProcess.Running

    def terminate(self):
        self.terminated = True

    def waitForFinished(self, _timeout):
        return True

    def kill(self):
        self.killed = True


def _app():
    return QCoreApplication.instance() or QCoreApplication([])


def test_ota_task_title_does_not_lock_stop_before_upgrade_stage():
    _app()
    runner = ProcessRunner()
    task = RunningTask(QProcess(), "执行 OTA 升级")

    runner._update_stop_lock(task, "\n$ 执行 OTA 升级\n[run] 上传升级包\n")

    assert not task.stop_locked
    assert not runner.stop_locked


def test_upgrade_stage_marker_locks_stop_and_emits_status_change():
    _app()
    runner = ProcessRunner()
    changes = []
    runner.task_status_changed.connect(lambda: changes.append(True))
    task = RunningTask(QProcess(), "执行 OTA 升级")
    runner.tasks = {1: task}

    runner._update_stop_lock(task, "[DOG_REMOTE_STAGE] upgrade_locked\n")

    assert task.stop_locked
    assert runner.stop_locked
    assert changes


def test_small_deploy_lock_message_names_small_package_stage():
    _app()
    runner = ProcessRunner()
    messages = []
    runner.output.connect(messages.append)
    task = RunningTask(QProcess(), "执行小包部署")
    runner.tasks = {1: task}

    runner._update_stop_lock(task, "[DOG_REMOTE_STAGE] upgrade_locked\n")

    assert any("小包安装阶段" in message for message in messages)
    assert not any("OTA 刷机阶段" in message for message in messages)


def test_refresh_stop_locked_keeps_existing_locked_task_state():
    _app()
    runner = ProcessRunner()
    process = QProcess()
    process.start("bash", ["-lc", "sleep 2"])
    assert process.waitForStarted(1000)
    try:
        locked = RunningTask(process, "刷机中", concurrency="parallel", stop_locked=True)
        unlocked = RunningTask(QProcess(), "普通任务", concurrency="parallel")
        runner.tasks = {1: locked, 2: unlocked}

        runner._refresh_stop_locked()

        assert runner.stop_locked

        locked.stop_locked = False
        runner._refresh_stop_locked()

        assert not runner.stop_locked
    finally:
        process.kill()
        process.waitForFinished(1000)


def test_task_finished_emits_code_and_title_before_legacy_finished():
    _app()
    runner = ProcessRunner()
    events = []
    runner.task_finished_detail.connect(lambda task_id, code, title: events.append(("detail", task_id, code, title)))
    runner.task_finished.connect(lambda code, title: events.append(("task", code, title)))
    runner.finished.connect(lambda code: events.append(("legacy", code)))
    runner.tasks = {1: RunningTask(QProcess(), "并发任务")}

    runner._finished(1, 7)

    assert events == [("detail", 1, 7, "并发任务"), ("task", 7, "并发任务"), ("legacy", 7)]


def test_run_returns_none_when_conflict_blocks_task():
    _app()
    runner = ProcessRunner()
    process = QProcess()
    process.start("bash", ["-lc", "sleep 2"])
    assert process.waitForStarted(1000)
    try:
        runner.tasks = {1: RunningTask(process, "已有任务")}

        assert runner.run("true", "新任务") is None
    finally:
        process.kill()
        process.waitForFinished(1000)


def test_stop_terminates_process_tree_before_qprocess(monkeypatch):
    _app()
    runner = ProcessRunner()
    process = _FakeRunningProcess()
    calls = []
    runner.tasks = {1: RunningTask(process, "上传 OTA")}

    monkeypatch.setattr(runner_module, "terminate_process_tree", lambda item: calls.append(item))

    runner.stop()

    assert calls == [process]
    assert process.terminated
    assert runner.tasks[1].stopped_by_user


def test_pending_task_blocks_exclusive_task_before_qprocess_enters_running():
    _app()
    runner = ProcessRunner()
    runner.tasks = {1: RunningTask(QProcess(), "停止导航")}

    assert runner.conflict_reason(concurrency="exclusive") == "当前已有任务运行：停止导航，请先停止或等待结束。"
    assert runner.run("true", "重复停止") is None


def test_parallel_task_with_lock_is_not_blocked_by_unlocked_parallel_task():
    _app()
    runner = ProcessRunner()
    process = QProcess()
    process.start("bash", ["-lc", "sleep 2"])
    assert process.waitForStarted(1000)
    try:
        runner.tasks = {1: RunningTask(process, "遥控/视频任务", concurrency="parallel")}

        assert runner.conflict_reason(concurrency="parallel", locks=("mapping",)) == ""
    finally:
        process.kill()
        process.waitForFinished(1000)


def test_parallel_task_with_lock_is_blocked_by_same_lock():
    _app()
    runner = ProcessRunner()
    process = QProcess()
    process.start("bash", ["-lc", "sleep 2"])
    assert process.waitForStarted(1000)
    try:
        runner.tasks = {1: RunningTask(process, "结束并保存建图", concurrency="parallel", locks=("mapping",))}

        assert runner.conflict_reason(concurrency="parallel", locks=("mapping",)) == "当前任务与正在运行的任务冲突：结束并保存建图"
    finally:
        process.kill()
        process.waitForFinished(1000)


def test_slot_reservation_participates_in_runner_conflict_checks():
    runner = ProcessRunner()
    spec = CommandSpec(
        "导航位姿流",
        "stream",
        concurrency="parallel",
        locks=("navigation-pose-stream",),
    )

    assert runner.reserve_slot("slot:pose", spec) == ""
    assert runner.conflict_reason(concurrency="exclusive") == "当前已有任务运行：导航位姿流，请先停止或等待结束。"
    assert (
        runner.conflict_reason(concurrency="parallel", locks=("navigation-pose-stream",))
        == "当前任务与正在运行的任务冲突：导航位姿流"
    )
    assert runner.conflict_reason(concurrency="parallel", locks=("navigation-plan-stream",)) == ""

    runner.release_slot("slot:pose")

    assert runner.conflict_reason(concurrency="exclusive") == ""


def test_run_emits_task_started_signal():
    _app()
    runner = ProcessRunner()
    events = []
    runner.task_started.connect(lambda task_id, title: events.append((task_id, title)))

    task_id = runner.run("true", "读取状态")

    assert task_id == 1
    assert events == [(1, "读取状态")]
    runner.shutdown()


def test_run_long_bash_command_uses_stdin_script():
    app = _app()
    runner = ProcessRunner()
    output = []
    runner.output.connect(output.append)
    command = "#" + ("x" * 70000) + "\nprintf ok"

    task_id = runner.run(command, "长命令")

    assert task_id == 1
    process = runner.tasks[task_id].process
    assert process.arguments() == ["-l", "-s"]
    assert process.waitForFinished(2000)
    app.processEvents()
    assert any("ok" in text for text in output)


def test_log_filter_compacts_ros_service_noise_but_keeps_key_result():
    text = "\n".join(
        [
            "requester: making request: robots_dog_msgs.srv.MapState_Request(mapping_type=0, data=3)",
            "waiting for service to become available...",
            "response:",
            "robots_dog_msgs.srv.MapState_Response(success=True, message='OK')",
            "success=True",
            "message='APP Set ACTIVE State Successfully'",
            "[INFO] 建图服务已发送",
        ]
    )

    compacted = compact_output(text)

    assert "requester:" not in compacted
    assert "waiting for service" not in compacted
    assert "已省略" not in compacted
    assert "success=True" not in compacted
    assert "message='APP Set ACTIVE State Successfully'" not in compacted
    assert "[INFO] 建图服务已发送" in compacted


def test_log_filter_splits_adjacent_log_records_without_newline():
    compacted = compact_output("[INFO] 读取状态[ERROR] SSH 认证失败")

    assert compacted == "[INFO] 读取状态\n[ERROR] SSH 认证失败"


def test_user_log_filter_hides_commands_machine_values_and_secrets():
    text = "\n".join(
        [
            "$ sshpass -p secret ssh robot@192.168.1.2",
            "NAV_STATE=2",
            "[INFO] 导航状态已刷新",
            "S100_REMOTE_PASSWORD=wireless-secret",
            "[WARN] 地图未初始化",
        ]
    )

    compacted = compact_user_output(text)

    assert "sshpass" not in compacted
    assert "NAV_STATE" not in compacted
    assert "secret" not in compacted
    assert "wireless-secret" not in compacted
    assert "[INFO] 导航状态已刷新" in compacted
    assert "[WARN] 地图未初始化" in compacted


def test_technical_log_filter_keeps_context_but_redacts_secrets():
    text = "\n".join(
        [
            "$ sshpass -p secret ssh robot@192.168.1.2",
            "NAV_STATE=2",
            "S100_REMOTE_PASSWORD=wireless-secret",
            "[ERROR] 读取失败",
        ]
    )

    compacted = compact_technical_output(text)

    assert "sshpass -p <已隐藏>" in compacted
    assert "NAV_STATE=2" in compacted
    assert "S100_REMOTE_PASSWORD=<已隐藏>" in compacted
    assert "secret" not in compacted
    assert "wireless-secret" not in compacted
    assert "[ERROR] 读取失败" in compacted


def test_redact_sensitive_masks_password_arguments_and_env_values():
    text = "sshpass -p secret ssh host --password hunter2 SUDO_PASSWORD=wireless-secret"

    redacted = redact_sensitive(text)

    assert "secret" not in redacted
    assert "hunter2" not in redacted
    assert "wireless-secret" not in redacted
    assert "sshpass -p <已隐藏>" in redacted
    assert "--password <已隐藏>" in redacted
    assert "SUDO_PASSWORD=<已隐藏>" in redacted


def test_failure_summary_reports_known_mapping_permission_reason():
    summary = failure_summary(
        "开始建图",
        4,
        [
            "terminate called after throwing an instance of std::filesystem_error",
            "filesystem error: cannot create directories: Permission denied [/home/robot/.robot/param]",
        ],
    )

    assert summary.startswith("[失败原因]")
    assert "/home/robot/.robot/param 权限不足" in summary
    assert "chown -R robot:robot /home/robot/.robot" in summary


def test_failure_summary_reports_nx_ota_size_check_before_progress_tail():
    summary = failure_summary(
        "执行 OTA 升级",
        1,
        [
            "[远程NX] 错误: /ota 文件大小校验失败",
            "[INFO] [upload] 上传进度: 100% 23.46MB/s",
        ],
    )

    assert "/ota 文件大小校验失败" in summary
    assert "上传进度" not in summary


def test_failure_summary_reports_missing_ota_package_before_progress_tail():
    summary = failure_summary(
        "执行 OTA 升级",
        1,
        [
            "[远程NX] 错误: 升级包不存在: /home/robot/ota/905003065CDA.tar.gz",
            "[INFO] [upload] 上传进度: 0% 0.00kB/s",
        ],
    )

    assert "远端升级包不存在" in summary
    assert "905003065CDA.tar.gz" in summary
    assert "上传进度" not in summary


def test_failure_summary_reports_robot_slam_external_yaml_error():
    summary = failure_summary(
        "开始建图",
        3,
        [
            "[ERROR] slam_state_service 未就绪，请查看日志",
            "[2026-06-02 11:17:35.540] [error] [SystemConfig]: External parameters yaml file isn't exist.",
        ],
    )

    assert "robot_slam 外部参数 YAML 缺失" in summary
    assert "远端实际报错" in summary
    assert "External parameters yaml file isn't exist" in summary


def test_runner_failure_emits_reason_from_recent_output_tail():
    _app()
    runner = ProcessRunner()
    outputs = []
    runner.output.connect(outputs.append)
    task = RunningTask(QProcess(), "开始建图")
    task.output_tail.extend(
        [
            "[ERROR] 未确认 state=2 READY，取消开始建图请求，避免重复触发 ACTIVE",
            "Sensors data(lidar or imu) lost for at least 2 second",
        ]
    )
    runner.tasks = {1: task}

    runner._finished(1, 4)

    joined = "".join(outputs)
    assert "[任务 1] 失败：开始建图" in joined
    assert "返回码 4" not in joined
    assert "[失败原因]" in joined
    assert "传感器数据中断" in joined


def test_runner_reports_user_stopped_task_without_failure_summary():
    _app()
    runner = ProcessRunner()
    outputs = []
    runner.output.connect(outputs.append)
    runner.tasks = {1: RunningTask(QProcess(), "执行 OTA 升级", stopped_by_user=True)}

    runner._finished(1, 15)

    joined = "".join(outputs)
    assert "任务已停止：执行 OTA 升级" in joined
    assert "失败：执行 OTA 升级" not in joined
    assert "[失败原因]" not in joined


def test_runner_treats_mapping_save_termination_after_save_begin_as_completion():
    _app()
    runner = ProcessRunner()
    outputs = []
    details = []
    runner.output.connect(outputs.append)
    runner.task_finished_detail.connect(lambda task_id, code, title: details.append((task_id, code, title)))
    task = RunningTask(QProcess(), "结束并保存建图")
    task.output_tail.extend(
        [
            "[信息] 建图状态：保存中",
            "Terminated",
        ]
    )
    runner.tasks = {3: task}

    runner._finished(3, 143)

    joined = "".join(outputs)
    assert "远端已进入建图保存流程" in joined
    assert "[任务 3] 完成：结束并保存建图" in joined
    assert "失败：结束并保存建图" not in joined
    assert "[失败原因]" not in joined
    assert details == [(3, 143, "结束并保存建图")]


def test_runner_keeps_mapping_save_termination_without_save_marker_as_failure():
    _app()
    runner = ProcessRunner()
    outputs = []
    runner.output.connect(outputs.append)
    task = RunningTask(QProcess(), "结束并保存建图")
    task.output_tail.extend(["Terminated"])
    runner.tasks = {3: task}

    runner._finished(3, 143)

    joined = "".join(outputs)
    assert "[任务 3] 失败：结束并保存建图" in joined
    assert "[失败原因]" in joined


def test_runner_formats_task_boundaries_for_user_log():
    _app()
    runner = ProcessRunner()
    outputs = []
    runner.output.connect(outputs.append)
    runner.tasks = {3: RunningTask(QProcess(), "读取状态")}

    runner.output.emit("\n[任务 3] 开始：读取状态\n")
    runner._finished(3, 0)

    joined = "".join(outputs)
    assert "[任务 3] 开始：读取状态" in joined
    assert "[任务 3] 完成：读取状态" in joined


def test_runner_prefixes_parallel_task_output():
    _app()
    runner = ProcessRunner()
    outputs = []
    runner.output.connect(outputs.append)
    process = QProcess()
    task = RunningTask(process, "并行任务", concurrency="parallel")
    runner.tasks = {5: task}

    assert runner._should_prefix_task_output(5) is True


def test_runner_emits_raw_task_output_with_task_id():
    _app()
    runner = ProcessRunner()
    raw = []
    runner.task_output.connect(lambda task_id, text: raw.append((task_id, text)))
    process = _FakeChunkProcess([b"APP_NAV_STATUS=Active\n"])
    runner.tasks = {6: RunningTask(process, "导航")}

    runner._read_output(6)

    assert raw == [(6, "APP_NAV_STATUS=Active\n")]


def test_runner_buffers_incomplete_output_lines_until_newline():
    _app()
    runner = ProcessRunner()
    outputs = []
    runner.output.connect(outputs.append)
    process = _FakeChunkProcess([b"[INFO] partial", b" line\n"])
    runner.tasks = {6: RunningTask(process, "分块输出")}

    runner._read_output(6)
    assert outputs == []

    runner._read_output(6)
    assert outputs == ["[INFO] partial line\n"]


def test_runner_flushes_final_partial_line_before_task_summary():
    _app()
    runner = ProcessRunner()
    outputs = []
    technical_outputs = []
    runner.output.connect(outputs.append)
    runner.technical_output.connect(technical_outputs.append)
    process = _FakeFinishedProcess(b"[ERROR] SSH authentication failed")
    runner.tasks = {7: RunningTask(process, "读取远端目录")}

    runner._finished(7, 255)

    joined = "".join(outputs)
    technical_joined = "".join(technical_outputs)
    assert "[ERROR] SSH authentication failed\n\n[任务 7] 失败" in joined
    assert "返回码 255" not in joined
    assert "[ERROR] SSH authentication failed\n\n[任务 7] 失败：读取远端目录，返回码 255" in technical_joined


def test_failure_summary_reports_mapping_sensor_lost_reason():
    summary = failure_summary("开始建图", 7, ["error_msg='Mapping sensors data is lost.'"])

    assert "建图传感器数据丢失" in summary
    assert "lidar/imu" in summary


def test_failure_summary_reports_localization_relocalization_failed_reason():
    summary = failure_summary(
        "测试定位",
        6,
        [
            "[ERROR] 定位状态失败: topic=/robot_slam/localization_state state=8 desc=Fail: relocalization failed, please reload map or reset.",
            "failed to check service availability: rcl node's context is invalid",
        ],
    )

    assert "定位重定位失败" in summary
    assert "rcl node" not in summary


def test_failure_summary_reports_arc_dock_not_ready_before_cleanup_tail():
    summary = failure_summary(
        "执行：ARC 回充",
        7,
        [
            '[ERROR] ARC 错误通知: {"items": [{"code": 13697, "description": "DOCK_NOT_READY", "severity": "error"}]}',
            '[ERROR] ARC 错误通知: {"items": [{"code": 13702, "description": "FINE_FAILURE", "severity": "error"}]}',
            "[ERROR] ARC 回充失败终态: alg=UnDockReset dock=Passive。",
            "[INFO] ARC 诊断日志: 2026-06-12 02:31:29.192 [INFO] mod.rs:2297: 移除控制权",
            "[INFO] 未发现遗留控制权发布器",
            "[INFO] 已清理 ARC/遥控控制权保持并发送释放提示: /control_right/test=false",
        ],
    )

    assert "充电桩未就绪" in summary
    assert "DOCK_NOT_READY" in summary
    assert "FINE_FAILURE" in summary
    assert "释放控制权" not in summary


def test_failure_summary_reports_mapping_recovery_failed_reason():
    summary = failure_summary(
        "开始建图",
        7,
        [
            "[WARN] 已有 robot_slam 进程，但 slam_state_service 未就绪；进入建图专用恢复流程。",
            "[ERROR] 已停止 robot-alg-manager 但仍无法清理旧 robot_slam，未启动新建图进程。",
        ],
    )

    assert "建图专用恢复失败" in summary
    assert "旧 robot_slam 未退出" in summary


def test_failure_summary_explains_state_6_as_save_complete():
    summary = failure_summary(
        "开始建图",
        7,
        [
            "[ERROR] 远端 robot_slam 存在，但当前状态不是 READY/ACTIVE，state=6，未发送开始请求。",
        ],
    )

    assert "当前状态不是可开始状态" in summary
    assert "旧版 state=6 通常表示保存完成" in summary


def test_failure_summary_explains_success_needs_reset_before_active():
    summary = failure_summary(
        "开始建图",
        6,
        [
            "robots_dog_msgs.srv.MapState_Response(success=False, message='APP Set ACTIVE State Failed, Current state is SUCCESS')",
            "[ERROR] 复用远端 robot_slam 开始建图失败",
        ],
    )

    assert "不能直接切 ACTIVE" in summary
    assert "robot-slam 版本" in summary
    assert "复位或重启" in summary


def test_failure_summary_prefers_invalid_topic_over_foreign_slam_guard():
    summary = failure_summary(
        "开始建图",
        7,
        [
            "[WARN] 检测到已有 robot_slam，但不是本工具启动；进入服务接管检查，不会停止远端 robot_slam。",
            "[ERROR] 远端 robot_slam 存在，但当前状态不是 READY/ACTIVE，state=1，未发送开始请求。",
            "[warning] [GnssProcess]: save_map_path: [] not exist.",
            "terminate called after throwing an instance of 'rclcpp::exceptions::InvalidTopicNameError'",
            "[ros2run]: Aborted",
        ],
    )

    assert "InvalidTopicNameError" in summary
    assert "save_map_path" in summary
    assert "非本工具启动" not in summary


def test_failure_summary_reports_common_ssh_network_reason():
    summary = failure_summary("读取状态", 255, ["ssh: connect to host 192.168.1.2 port 22: No route to host"])

    assert "SSH 网络不可达" in summary
    assert "目标 IP" in summary


def test_failure_summary_reports_ssh_auth_reason():
    summary = failure_summary("读取状态", 255, ["robot@192.168.1.2: Permission denied (publickey,password)."])

    assert "SSH 认证失败" in summary
    assert "账号、密码" in summary


def test_failure_summary_reports_missing_command_reason():
    summary = failure_summary("检查服务", 127, ["bash: robot-launch: command not found"])

    assert "远端缺少命令" in summary
    assert "robot-launch" in summary


def test_failure_summary_reports_missing_path_reason():
    summary = failure_summary("读取文件", 2, ["cat: /home/robot/map.yaml: No such file or directory"])

    assert "目标文件或目录不存在" in summary
    assert "/home/robot/map.yaml" in summary


def test_failure_summary_reports_disk_space_reason():
    summary = failure_summary("回传地图", 1, ["rsync: write failed on map.pcd: No space left on device"])

    assert "磁盘空间不足" in summary
    assert "更换保存目录" in summary


def test_failure_summary_reports_service_unavailable_reason():
    summary = failure_summary("加载地图", 3, ["Failed to call service /load_map_service: service not available"])

    assert "ROS 服务不可用" in summary
    assert "ROS_DOMAIN_ID" in summary


def test_runner_failure_emits_common_reason_from_recent_output_tail():
    _app()
    runner = ProcessRunner()
    outputs = []
    runner.output.connect(outputs.append)
    task = RunningTask(QProcess(), "读取远端目录")
    task.output_tail.extend(["ssh: connect to host 192.168.1.2 port 22: Connection timed out"])
    runner.tasks = {2: task}

    runner._finished(2, 255)

    joined = "".join(outputs)
    assert "[任务 2] 失败：读取远端目录" in joined
    assert "返回码 255" not in joined
    assert "[失败原因] SSH 网络不可达" in joined


def test_runner_finished_drains_remaining_output_before_failure_summary():
    _app()
    runner = ProcessRunner()
    outputs = []
    runner.output.connect(outputs.append)
    process = _FakeFinishedProcess(b"ssh: connect to host 192.168.1.2 port 22: No route to host\n")
    runner.tasks = {3: RunningTask(process, "读取远端目录")}

    runner._finished(3, 255)

    joined = "".join(outputs)
    assert "No route to host" in joined
    assert "[失败原因] SSH 网络不可达" in joined
    assert process.deleted is True


def test_log_filter_hides_expanded_bash_command_after_syntax_error():
    compacted = compact_output(
        "bash: -c: line 1: syntax error near unexpected token `;'\n"
        "bash: -c: line 1: `IFS= read -r DOG_REMOTE_SUDO_PASS; "
        + "x" * 500
        + "'\n"
    )

    assert "syntax error near unexpected token" in compacted
    assert "IFS= read -r DOG_REMOTE_SUDO_PASS" not in compacted
    assert "已省略" not in compacted
