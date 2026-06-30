from __future__ import annotations


LEVEL_LABELS = {
    "info": "信息",
    "warn": "警告",
    "error": "错误",
    "success": "完成",
    "failure": "失败",
}


def log_line(level: str, message: str, *, scope: str = "") -> str:
    label = LEVEL_LABELS.get(level.lower(), level)
    prefix = f"[{label}]"
    if scope:
        prefix = f"{prefix} {scope}"
    return f"{prefix} {message.rstrip()}\n"


def task_start(task_id: int, title: str) -> str:
    return f"\n[任务 {task_id}] 开始：{title}\n"


def task_success(task_id: int, title: str) -> str:
    return f"\n[任务 {task_id}] 完成：{title}\n"


def task_failure(task_id: int, title: str, code: int) -> str:
    return f"\n[任务 {task_id}] 失败：{title}，返回码 {code}\n"


def task_failure_user(task_id: int, title: str) -> str:
    return f"\n[任务 {task_id}] 失败：{title}\n"


def prefix_task_output(task_id: int, text: str) -> str:
    if not text:
        return ""
    prefix = f"[任务 {task_id}] "
    lines = text.splitlines(keepends=True)
    return "".join(_prefix_output_line(prefix, line) for line in lines)


def _prefix_output_line(prefix: str, line: str) -> str:
    if line in ("\n", "\r\n") or not line.strip():
        return line
    return prefix + line
