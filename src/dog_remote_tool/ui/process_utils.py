from __future__ import annotations

import os
import signal
import subprocess
import time

from PyQt5.QtCore import QObject, QProcess, QTimer

from dog_remote_tool.core.qprocess_bash import configure_bash_process

DEFAULT_OUTPUT_LIMIT = 128 * 1024


def safe_delete_process(process: QProcess | None) -> None:
    if process is None:
        return
    try:
        process.deleteLater()
    except RuntimeError:
        pass


def _qprocess_pid(process: QProcess | None) -> int | None:
    if process is None:
        return None
    try:
        pid = int(process.processId())
    except (AttributeError, RuntimeError, TypeError, ValueError):
        return None
    return pid if pid > 0 else None


def _descendant_pids(root_pid: int) -> list[int]:
    try:
        output = subprocess.check_output(
            ["ps", "-eo", "pid=,ppid="],
            text=True,
            stderr=subprocess.DEVNULL,
            timeout=0.5,
        )
    except Exception:
        return []
    children_by_parent: dict[int, list[int]] = {}
    for line in output.splitlines():
        parts = line.split()
        if len(parts) != 2:
            continue
        try:
            pid, ppid = int(parts[0]), int(parts[1])
        except ValueError:
            continue
        children_by_parent.setdefault(ppid, []).append(pid)
    descendants: list[int] = []
    stack = list(children_by_parent.get(root_pid, ()))
    while stack:
        pid = stack.pop()
        descendants.append(pid)
        stack.extend(children_by_parent.get(pid, ()))
    return descendants


def signal_process_tree(process: QProcess | None, sig: int) -> None:
    root_pid = _qprocess_pid(process)
    if root_pid is None:
        return
    for pid in [*_descendant_pids(root_pid), root_pid]:
        try:
            os.kill(pid, sig)
        except (ProcessLookupError, PermissionError, OSError):
            pass


def terminate_process_tree(process: QProcess | None) -> None:
    signal_process_tree(process, signal.SIGTERM)


def kill_process_tree(process: QProcess | None) -> None:
    signal_process_tree(process, signal.SIGKILL)


def stop_process_safely(process: QProcess | None, timeout_ms: int = 1000) -> None:
    if process is None:
        return
    try:
        process.finished.disconnect()
    except (TypeError, RuntimeError):
        pass
    try:
        if process.state() != QProcess.NotRunning:
            terminate_process_tree(process)
            process.terminate()
            if not process.waitForFinished(timeout_ms):
                kill_process_tree(process)
                process.kill()
                process.waitForFinished(timeout_ms)
    except RuntimeError:
        return
    safe_delete_process(process)


def _kill_process_if_running(process: QProcess | None) -> None:
    if process is None:
        return
    try:
        if process.state() != QProcess.NotRunning:
            kill_process_tree(process)
            process.kill()
    except RuntimeError:
        return


def _delete_process_if_stopped(process: QProcess | None) -> None:
    if process is None:
        return
    try:
        if process.state() == QProcess.NotRunning:
            safe_delete_process(process)
    except RuntimeError:
        return


def stop_process_async(process: QProcess | None, timeout_ms: int = 1000) -> None:
    if process is None:
        return
    try:
        process.finished.disconnect()
    except (TypeError, RuntimeError):
        pass
    try:
        if process.state() == QProcess.NotRunning:
            safe_delete_process(process)
            return
        terminate_process_tree(process)
        process.terminate()
    except RuntimeError:
        return
    QTimer.singleShot(max(100, timeout_ms), lambda p=process: _kill_process_if_running(p))
    QTimer.singleShot(max(300, timeout_ms + 300), lambda p=process: _delete_process_if_stopped(p))


def append_limited_output(chunks: list[str], text: str, limit: int = DEFAULT_OUTPUT_LIMIT) -> None:
    if not text:
        return
    chunks.append(text)
    total = sum(len(chunk) for chunk in chunks)
    if total <= limit:
        return
    keep_from = max(0, total - limit)
    kept: list[str] = []
    skipped = 0
    for chunk in chunks:
        next_skipped = skipped + len(chunk)
        if next_skipped <= keep_from:
            skipped = next_skipped
            continue
        if skipped < keep_from:
            kept.append(chunk[keep_from - skipped :])
        else:
            kept.append(chunk)
        skipped = next_skipped
    chunks[:] = kept


class ProcessSlot:
    """Owns one page-local QProcess and its request-scoped output buffer."""

    def __init__(
        self,
        owner: QObject | None = None,
        *,
        output_limit: int = DEFAULT_OUTPUT_LIMIT,
        stop_timeout_ms: int = 1000,
        reserve_runner: bool = True,
    ) -> None:
        self.owner = owner
        self.output_limit = output_limit
        self.stop_timeout_ms = stop_timeout_ms
        self.reserve_runner = reserve_runner
        self.process: QProcess | None = None
        self.request_id = 0
        self.output_chunks: list[str] = []
        self._runner_reservation_id = f"slot:{id(self)}"
        self._reserved_runner = None
        self._metric_started_at: float | None = None
        self._metric_title = ""
        self._metric_ssh_control = False
        self._metric_ssh_control_count = 0
        self._metric_ssh_proxy = False
        self._metric_first_output_logged = False

    def is_running(self) -> bool:
        try:
            return self.process is not None and self.process.state() != QProcess.NotRunning
        except RuntimeError:
            self.process = None
            return False

    def invalidate(self) -> int:
        self.request_id += 1
        self.output_chunks = []
        return self.request_id

    def stop(self) -> bool:
        was_running = self.is_running()
        process = self.process
        self.process = None
        self._emit_metric("stopped")
        self._release_runner_reservation()
        self._clear_metric()
        self.invalidate()
        stop_process_safely(process, self.stop_timeout_ms)
        return was_running

    def stop_async(self) -> bool:
        was_running = self.is_running()
        process = self.process
        self.process = None
        self._emit_metric("stopped")
        self._release_runner_reservation()
        self._clear_metric()
        self.invalidate()
        stop_process_async(process, self.stop_timeout_ms)
        return was_running

    def start_spec(self, spec, *, login_shell: bool = True, quiet_conflict: bool = False) -> tuple[QProcess | None, int]:
        runner = getattr(self.owner, "runner", None) if self.reserve_runner else None
        if self.is_running():
            self.stop()
        else:
            self._release_runner_reservation()
        reserve_slot = getattr(runner, "reserve_slot", None)
        if callable(reserve_slot):
            conflict = reserve_slot(self._runner_reservation_id, spec)
            if conflict:
                output = getattr(runner, "output", None)
                emit = getattr(output, "emit", None)
                if callable(emit) and not quiet_conflict:
                    emit(f"[WARN] {conflict}\n")
                return None, 0
            self._reserved_runner = runner
        else:
            conflict_reason = getattr(runner, "conflict_reason", None)
            if callable(conflict_reason):
                conflict = conflict_reason(spec)
                if conflict:
                    output = getattr(runner, "output", None)
                    emit = getattr(output, "emit", None)
                    if callable(emit) and not quiet_conflict:
                        emit(f"[WARN] {conflict}\n")
                    return None, 0
        process, request_id = self.start_bash(spec.command, login_shell=login_shell)
        self._begin_metric(spec)
        return process, request_id

    def _release_runner_reservation(self) -> None:
        runner = self._reserved_runner
        self._reserved_runner = None
        release_slot = getattr(runner, "release_slot", None)
        if callable(release_slot):
            release_slot(self._runner_reservation_id)

    def start_bash(self, command: str, *, login_shell: bool = True) -> tuple[QProcess, int]:
        if self.is_running():
            self.stop()
        elif self.process is not None:
            safe_delete_process(self.process)
            self.process = None
        self._clear_metric()
        request_id = self.invalidate()
        process = QProcess(self.owner if isinstance(self.owner, QObject) else None)
        self.process = process
        configure_bash_process(process, command, login_shell=login_shell)
        process.setProcessChannelMode(QProcess.MergedChannels)
        return process, request_id

    def _begin_metric(self, spec) -> None:
        self._metric_started_at = time.monotonic()
        self._metric_title = getattr(spec, "display_command", "") or getattr(spec, "title", "") or "ProcessSlot"
        command = getattr(spec, "command", "") or ""
        self._metric_ssh_control_count = command.count("ControlMaster=auto")
        self._metric_ssh_control = self._metric_ssh_control_count > 0
        self._metric_ssh_proxy = "ProxyCommand=" in command
        self._metric_first_output_logged = False

    def _clear_metric(self) -> None:
        self._metric_started_at = None
        self._metric_title = ""
        self._metric_ssh_control = False
        self._metric_ssh_control_count = 0
        self._metric_ssh_proxy = False
        self._metric_first_output_logged = False

    def _emit_metric(self, event: str) -> None:
        if self._metric_started_at is None:
            return
        runner = getattr(self.owner, "runner", None)
        technical_output = getattr(runner, "technical_output", None)
        emit = getattr(technical_output, "emit", None)
        if not callable(emit):
            return
        elapsed_ms = int((time.monotonic() - self._metric_started_at) * 1000)
        ssh_control = "on" if self._metric_ssh_control else "off"
        ssh_proxy = "on" if self._metric_ssh_proxy else "off"
        emit(
            f"[METRIC] {self._metric_title} {event} elapsed_ms={elapsed_ms} "
            f"ssh_control={ssh_control} ssh_control_count={self._metric_ssh_control_count} ssh_proxy={ssh_proxy}\n"
        )

    def accepts(self, process: QProcess, request_id: int) -> bool:
        return process is self.process and request_id == self.request_id

    def read_available_text(self, process: QProcess, request_id: int) -> str:
        if not self.accepts(process, request_id):
            return ""
        try:
            data = bytes(process.readAllStandardOutput()).decode("utf-8", errors="replace")
        except RuntimeError:
            return ""
        append_limited_output(self.output_chunks, data, self.output_limit)
        if data and not self._metric_first_output_logged:
            self._metric_first_output_logged = True
            self._emit_metric("first_output")
        return data

    def read_available_output(self, process: QProcess, request_id: int) -> bool:
        return bool(self.read_available_text(process, request_id))

    def finish(self, process: QProcess, request_id: int) -> str | None:
        if not self.accepts(process, request_id):
            if process is self.process:
                self.process = None
                self.output_chunks = []
                self._release_runner_reservation()
                self._clear_metric()
            safe_delete_process(process)
            return None
        self.read_available_output(process, request_id)
        output = "".join(self.output_chunks)
        self.output_chunks = []
        self.process = None
        self._emit_metric("finished")
        self._release_runner_reservation()
        self._clear_metric()
        safe_delete_process(process)
        return output
