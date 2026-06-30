from __future__ import annotations

import json


def split_control_stream_lines(text: str) -> list[str]:
    lines: list[str] = []
    for raw_line in text.splitlines():
        lines.extend(split_control_stream_line(raw_line))
    return lines


def split_control_stream_line(raw_line: str) -> list[str]:
    line = raw_line.strip()
    if not line:
        return []
    if not line.startswith("{"):
        return [line]
    chunks: list[str] = []
    start = 0
    depth = 0
    in_string = False
    escaped = False
    for index, char in enumerate(line):
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char in "{[":
            depth += 1
        elif char in "}]":
            depth -= 1
            if depth == 0 and index + 1 < len(line) and line[index + 1] == "{":
                chunks.append(line[start:index + 1].strip())
                start = index + 1
    chunks.append(line[start:].strip())
    return [chunk for chunk in chunks if chunk]


def _split_complete_tail_json(text: str) -> tuple[list[str], str]:
    parts = split_control_stream_lines(text)
    if not parts:
        return [], text
    if len(parts) > 1:
        return parts[:-1], parts[-1]
    try:
        json.loads(parts[0])
    except json.JSONDecodeError:
        return [], text
    return parts, ""


def consume_control_json_stream(buffer: str, text: str, keep_partial: bool = False) -> tuple[str, list[tuple[dict | None, str]]]:
    combined = buffer + text
    if keep_partial:
        raw_lines = combined.splitlines(keepends=True)
        if raw_lines and not raw_lines[-1].endswith(("\n", "\r")):
            complete_tail_lines, remaining = _split_complete_tail_json(raw_lines.pop())
        else:
            complete_tail_lines = []
            remaining = ""
        lines = split_control_stream_lines("".join(raw_lines))
        lines.extend(complete_tail_lines)
    else:
        remaining = ""
        lines = split_control_stream_lines(combined)

    events: list[tuple[dict | None, str]] = []
    for line in lines:
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            events.append((None, line))
            continue
        events.append((payload if isinstance(payload, dict) else None, line))
    return remaining, events


def l1_stream_ready_log(payload: dict) -> str:
    return "[L1 遥控] 遥控已连接。\n"


def l1_stream_log_line(payload: dict) -> str:
    kind = payload.get("type")
    if kind == "error":
        return f"[L1 遥控] 错误：{payload.get('message')}\n"
    if kind == "log":
        return f"[L1 遥控] {payload.get('message')}\n"
    if kind == "result":
        cmd = payload.get("cmd")
        action = L1_ACTION_LABELS.get(cmd, cmd)
        return f"[L1 遥控] 动作完成：{action}\n"
    if kind == "move" and payload.get("ret") not in (0, None):
        return "[L1 遥控] 移动指令未成功，请查看详细日志。\n"
    return ""


def l2_stream_log_line(payload: dict) -> str:
    kind = payload.get("type")
    if kind == "ready":
        return "[实时遥控] 键盘遥控已就绪。\n"
    if kind == "error":
        return f"[实时遥控] 遥控连接失败：{payload.get('message')}\n"
    if kind == "state":
        posture = payload.get("posture", "unknown")
        label = {"stand": "站立", "lie": "趴下", "crawl": "匍匐"}.get(str(posture), "已刷新")
        return f"[实时遥控] 机器人状态：{label}\n"
    if kind == "result":
        return f"[实时遥控] 动作完成：{payload.get('cmd')}\n"
    return ""


def l2_stream_result_inplace_mode(payload: dict) -> bool | None:
    if payload.get("type") != "result":
        return None
    command = payload.get("cmd")
    if command == "head":
        return True
    if command in {"stand", "lie", "crawl"}:
        return False
    return None


L1_ACTION_LABELS = {
    "neutral": "停止",
    "stand": "站立",
    "low": "低姿态",
    "lie": "低姿态",
    "passive": "阻尼趴下",
    "crawl": "匍匐",
}
