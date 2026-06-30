from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field

from PyQt5.QtCore import QObject, QProcess, pyqtSignal

from .log_filter import compact_technical_output, compact_user_output, failure_summary, update_tail
from .log_format import log_line, prefix_task_output, task_failure, task_failure_user, task_start, task_success
from .qprocess_bash import configure_bash_process
from .task_outcomes import mapping_save_continues_after_local_stop
from dog_remote_tool.ui.process_utils import kill_process_tree, terminate_process_tree


@dataclass
class RunningTask:
    process: QProcess
    title: str
    concurrency: str = "exclusive"
    locks: tuple[str, ...] = field(default_factory=tuple)
    stop_locked: bool = False
    stopped_by_user: bool = False
    output_tail: deque[str] = field(default_factory=deque)
    output_buffer: str = ""


@dataclass
class RunningReservation:
    title: str
    concurrency: str = "exclusive"
    locks: tuple[str, ...] = field(default_factory=tuple)


class ProcessRunner(QObject):
    output = pyqtSignal(str)
    technical_output = pyqtSignal(str)
    state_changed = pyqtSignal(bool)
    task_status_changed = pyqtSignal()
    finished = pyqtSignal(int)
    task_started = pyqtSignal(int, str)
    task_finished = pyqtSignal(int, str)
    task_finished_detail = pyqtSignal(int, int, str)
    task_output = pyqtSignal(int, str)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.process: QProcess | None = None
        self.tasks: dict[int, RunningTask] = {}
        self.reservations: dict[str, RunningReservation] = {}
        self.next_task_id = 1
        self.stop_locked = False

    def is_running(self) -> bool:
        return bool(self.tasks)

    def run(
        self,
        command,
        display_command: str | None = None,
        *,
        concurrency: str = "exclusive",
        locks: tuple[str, ...] = (),
    ) -> int | None:
        if not isinstance(command, str) and hasattr(command, "command"):
            spec = command
            command = spec.command
            display_command = display_command or getattr(spec, "display_command", "") or getattr(spec, "title", "")
            concurrency = getattr(spec, "concurrency", "exclusive") or "exclusive"
            locks = tuple(getattr(spec, "locks", ()) or ())
        title = display_command or command
        conflict = self._conflict_reason(concurrency, locks)
        if conflict:
            self._emit_log(log_line("warn", conflict))
            return None
        was_idle = not self.is_running()
        process = QProcess(self)
        task_id = self.next_task_id
        self.next_task_id += 1
        self.tasks[task_id] = RunningTask(process, title, concurrency, locks)
        self.process = process
        self._refresh_stop_locked()
        configure_bash_process(process, command)
        process.setProcessChannelMode(QProcess.MergedChannels)
        process.readyReadStandardOutput.connect(lambda task_id=task_id: self._read_output(task_id))
        process.finished.connect(lambda code, _status, task_id=task_id: self._finished(task_id, code))
        self._emit_log(task_start(task_id, title))
        self.task_started.emit(task_id, title)
        if was_idle:
            self.state_changed.emit(True)
        self.task_status_changed.emit()
        process.start()
        return task_id

    def conflict_reason(self, command=None, *, concurrency: str = "exclusive", locks: tuple[str, ...] = ()) -> str:
        if command is not None and not isinstance(command, str) and hasattr(command, "command"):
            concurrency = getattr(command, "concurrency", "exclusive") or "exclusive"
            locks = tuple(getattr(command, "locks", ()) or ())
        return self._conflict_reason(concurrency, locks)

    def reserve_slot(self, reservation_id: str, spec) -> str:
        title = getattr(spec, "display_command", "") or getattr(spec, "title", "") or getattr(spec, "command", "")
        concurrency = getattr(spec, "concurrency", "exclusive") or "exclusive"
        locks = tuple(getattr(spec, "locks", ()) or ())
        conflict = self._conflict_reason(concurrency, locks, exclude_reservation_id=reservation_id)
        if conflict:
            return conflict
        self.reservations[reservation_id] = RunningReservation(title, concurrency, locks)
        self.task_status_changed.emit()
        return ""

    def release_slot(self, reservation_id: str) -> None:
        if self.reservations.pop(reservation_id, None) is not None:
            self.task_status_changed.emit()

    def _conflict_reason(
        self,
        concurrency: str,
        locks: tuple[str, ...],
        *,
        exclude_reservation_id: str | None = None,
    ) -> str:
        reservations = [
            reservation
            for reservation_id, reservation in self.reservations.items()
            if reservation_id != exclude_reservation_id
        ]
        active = [*self.tasks.values(), *reservations]
        if not active:
            return ""
        if concurrency == "exclusive":
            return f"当前已有任务运行：{active[0].title}，请先停止或等待结束。"
        exclusive = next((task for task in active if task.concurrency == "exclusive"), None)
        if exclusive:
            return f"当前独占任务正在运行：{exclusive.title}"
        requested_locks = set(locks)
        if not requested_locks:
            return ""
        for task in active:
            overlap = requested_locks.intersection(task.locks)
            if overlap:
                return f"当前任务与正在运行的任务冲突：{task.title}"
        return ""

    def stop(self) -> None:
        if not self.tasks:
            return
        stopped = 0
        locked = 0
        locked_message = "OTA 已进入刷机阶段，本地停止按钮已锁定；请等待远端升级完成。"
        for task in list(self.tasks.values()):
            if task.process.state() == QProcess.NotRunning:
                continue
            if task.stop_locked:
                locked += 1
                if "小包" in task.title:
                    locked_message = "小包安装已进入关键阶段，本地停止按钮已锁定；请等待远端安装完成。"
                continue
            task.stopped_by_user = True
            stopped += 1
            terminate_process_tree(task.process)
            task.process.terminate()
        if stopped:
            self._emit_log(log_line("info", f"正在停止 {stopped} 个任务..."))
        if locked:
            self._emit_log(log_line("warn", locked_message))
        if stopped or locked:
            self.task_status_changed.emit()
        for task in list(self.tasks.values()):
            if task.stop_locked or task.process.state() == QProcess.NotRunning:
                continue
            if not task.process.waitForFinished(2500):
                kill_process_tree(task.process)
                task.process.kill()
        self.task_status_changed.emit()

    def shutdown(self) -> None:
        tasks = list(self.tasks.values())
        self.tasks.clear()
        self.process = None
        self._refresh_stop_locked()
        self.task_status_changed.emit()
        if not tasks:
            return
        for task in tasks:
            process = task.process
            try:
                process.finished.disconnect()
            except (TypeError, RuntimeError):
                pass
            try:
                if process.state() != QProcess.NotRunning:
                    process.terminate()
                    if not process.waitForFinished(1000):
                        process.kill()
                        process.waitForFinished(1000)
                process.deleteLater()
            except RuntimeError:
                pass

    def _read_output(self, task_id: int, *, flush: bool = False) -> None:
        task = self.tasks.get(task_id)
        if not task:
            return
        data = bytes(task.process.readAllStandardOutput()).decode("utf-8", errors="replace")
        if data:
            update_tail(task.output_tail, data)
            self._update_stop_lock(task, data)
            self._emit_task_output(task_id, task, self._complete_output(task, data))
        if flush and task.output_buffer:
            pending = task.output_buffer
            task.output_buffer = ""
            self._emit_task_output(task_id, task, pending)

    def _finished(self, task_id: int, code: int) -> None:
        task = self.tasks.get(task_id)
        if task is not None:
            try:
                task.process.waitForReadyRead(50)
            except RuntimeError:
                pass
        self._read_output(task_id, flush=True)
        task = self.tasks.pop(task_id, None)
        process = task.process if task else None
        if process is self.process:
            self.process = next((item.process for item in self.tasks.values()), None)
        title = task.title if task else ""
        if task and task.stopped_by_user and code != 0:
            self._emit_log(log_line("info", f"任务已停止：{title}"))
        elif code == 0:
            self._emit_log(task_success(task_id, title))
        elif task and mapping_save_continues_after_local_stop(title, code, list(task.output_tail)):
            self._emit_log(log_line("info", "远端已进入建图保存流程，本地等待进程已结束；工具将刷新建图状态确认最新地图。"))
            self._emit_log(task_success(task_id, title))
        else:
            self.output.emit(task_failure_user(task_id, title))
            self.technical_output.emit(task_failure(task_id, title, code))
            if task:
                self._emit_log(failure_summary(title, code, list(task.output_tail)))
        self._refresh_stop_locked()
        if not self.is_running():
            self.state_changed.emit(False)
        self.task_finished_detail.emit(task_id, code, title)
        self.task_finished.emit(code, title)
        self.finished.emit(code)
        self.task_status_changed.emit()
        if process is not None:
            try:
                process.deleteLater()
            except RuntimeError:
                pass

    def _update_stop_lock(self, task: RunningTask, text: str) -> None:
        if task.stop_locked:
            return
        lock_needles = (
            "[DOG_REMOTE_STAGE] upgrade_locked",
        )
        if any(needle in text for needle in lock_needles):
            task.stop_locked = True
            self._refresh_stop_locked()
            if "小包" in task.title:
                message = "已进入小包安装阶段，停止按钮锁定。"
            else:
                message = "已进入 OTA 刷机阶段，停止按钮锁定。"
            self._emit_log(log_line("warn", message))
            self.task_status_changed.emit()

    def _refresh_stop_locked(self) -> None:
        self.stop_locked = any(item.stop_locked for item in self.tasks.values())

    def _should_prefix_task_output(self, task_id: int) -> bool:
        active = list(self.tasks)
        if len(active) > 1:
            return True
        task = self.tasks.get(task_id)
        return bool(task and task.concurrency != "exclusive")

    def _complete_output(self, task: RunningTask, data: str) -> str:
        task.output_buffer += data
        last_newline = max(task.output_buffer.rfind("\n"), task.output_buffer.rfind("\r"))
        if last_newline < 0:
            return ""
        complete = task.output_buffer[: last_newline + 1]
        task.output_buffer = task.output_buffer[last_newline + 1 :]
        return complete

    def _emit_task_output(self, task_id: int, task: RunningTask, text: str) -> None:
        if text:
            self.task_output.emit(task_id, text)
        user_display = compact_user_output(text)
        technical_display = compact_technical_output(text)
        should_prefix = self._should_prefix_task_output(task_id)
        if user_display:
            if not user_display.endswith("\n"):
                user_display += "\n"
            if should_prefix:
                user_display = prefix_task_output(task_id, user_display)
            self.output.emit(user_display)
        if technical_display:
            if not technical_display.endswith("\n"):
                technical_display += "\n"
            if should_prefix:
                technical_display = prefix_task_output(task_id, technical_display)
            self.technical_output.emit(technical_display)

    def _emit_log(self, text: str) -> None:
        self.output.emit(text)
        self.technical_output.emit(text)
