from __future__ import annotations


TASK_BUSY_MESSAGE = "当前有任务运行，请稍后再试。"


def task_not_started_text(action: str = "") -> str:
    action = action.strip()
    if action:
        return f"{action}未启动，{TASK_BUSY_MESSAGE}"
    return f"任务未启动，{TASK_BUSY_MESSAGE}"
