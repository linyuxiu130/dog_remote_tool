from __future__ import annotations

import shlex


class FakeSignal:
    def __init__(self):
        self.callbacks = []

    def connect(self, callback):
        self.callbacks.append(callback)

    def disconnect(self):
        self.callbacks.clear()

    def emit(self, *args, **kwargs):
        for callback in list(self.callbacks):
            callback(*args, **kwargs)


class FakeRunner:
    def __init__(self, task_id=None, conflict="", running=False, tasks=None):
        self.task_id = task_id
        self.conflict = conflict
        self.running = running
        self.tasks = tasks or {}
        self.run_calls = []
        self.output_lines = []
        self.output = self
        self.task_output = FakeSignal()

    def conflict_reason(self, *args, **kwargs):
        return self.conflict

    def is_running(self):
        return self.running

    def run(self, *args, **kwargs):
        self.run_calls.append((args, kwargs))
        return self.task_id

    def emit(self, text):
        self.output_lines.append(text)


class FakeOutput:
    def __init__(self):
        self.lines = []

    def emit(self, text):
        self.lines.append(text)


def remote_command(spec, target: str) -> str:
    args = shlex.split(spec.command)
    return args[args.index(target) + 1]


def remote_bash_script(spec, target: str) -> str:
    args = shlex.split(remote_command(spec, target))
    return args[args.index("-c") + 1]
