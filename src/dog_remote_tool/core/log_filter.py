from __future__ import annotations

import re
from collections import deque

from dog_remote_tool.core.failure_reasons import failure_reason


MAX_FAILURE_CONTEXT_LINES = 240

LOG_PREFIX_BOUNDARY_PATTERN = re.compile(
    r"([^\n ])"
    r"((?:\[任务 \d+\]\s*)?"
    r"(?:\[(?:INFO|WARN(?:ING)?|ERROR|信息|警告|错误|完成|失败|失败原因|命令|flash|run|SDK|L1 SDK|L1 遥控|实时遥控)\]|\$\s))",
    re.IGNORECASE,
)

NOISE_PATTERNS = (
    re.compile(r"^requester:\s", re.IGNORECASE),
    re.compile(r"^waiting for service to become available", re.IGNORECASE),
    re.compile(r"^response:$", re.IGNORECASE),
    re.compile(r"^[A-Za-z0-9_./]+\.srv\.[A-Za-z0-9_]+_(Request|Response)\("),
    re.compile(r"^success[=:]\s*True", re.IGNORECASE),
    re.compile(r"^message[=:].*(success|successfully|ok)", re.IGNORECASE),
    re.compile(r"^receiving file list", re.IGNORECASE),
    re.compile(r"^sent [0-9,]+ bytes\s+received [0-9,]+ bytes", re.IGNORECASE),
    re.compile(r"^total size is [0-9,]+", re.IGNORECASE),
    re.compile(r"^\s*[0-9,]+\s+[0-9]+%\s+\S+/?s\s+[0-9:]+(?:\s+\(xfr#[0-9]+,.*\))?$", re.IGNORECASE),
    re.compile(r"^\s*0\s+0%\s+0\.00kB/s", re.IGNORECASE),
    re.compile(r"^(?:map/|map\.static/|map\.(?:pcd|pgm|yaml|txt)$|metadata\.yaml$|key_frame_id\.txt$|static_map\.txt$)"),
    re.compile(r"^bash: -c: line \d+: [`'].{240,}"),
    re.compile(r"^---$"),
)

IMPORTANT_PATTERNS = (
    re.compile(r"^\[(INFO|WARN|ERROR|完成|失败)\]", re.IGNORECASE),
    re.compile(r"^\$\s"),
    re.compile(r"^(state|error_code|error_msg|STATUS|TEXT|SLAM_)[=:]"),
    re.compile(r"^success[=:]\s*False", re.IGNORECASE),
    re.compile(
        r"(permission denied|failed|error|exception|traceback|aborted|not found|missing|"
        r"connection timed out|no route to host|could not resolve hostname|host key verification failed|"
        r"no such file or directory|command not found|no space left on device|connection refused|"
        r"syntax error near unexpected token)",
        re.IGNORECASE,
    ),
)

SENSITIVE_PATTERNS = (
    (
        re.compile(r"(sshpass\s+-p\s+)(?:'[^']*'|\"[^\"]*\"|\S+)", re.IGNORECASE),
        r"\1<已隐藏>",
    ),
    (
        re.compile(
            r"\b((?:DOG_REMOTE_)?(?:SUDO_)?(?:S100_)?(?:GATEWAY_)?(?:REMOTE_)?(?:WIFI_)?PASS(?:WORD)?=)"
            r"(?:'[^']*'|\"[^\"]*\"|[^;\s]+)",
            re.IGNORECASE,
        ),
        r"\1<已隐藏>",
    ),
    (
        re.compile(r"(--password\s+)(?:'[^']*'|\"[^\"]*\"|\S+)", re.IGNORECASE),
        r"\1<已隐藏>",
    ),
)

USER_HIDDEN_PATTERNS = (
    re.compile(r"^(?:\[任务 \d+\]\s*)?(?:\$|\[命令\])\s"),
    re.compile(r"^(?:\[任务 \d+\]\s*)?[A-Z][A-Z0-9_]{2,}="),
    re.compile(r"^(?:\[任务 \d+\]\s*)?(?:Traceback \(most recent call last\)|File \".+\", line \d+)", re.IGNORECASE),
    re.compile(r"\bsshpass\s+-[fp]\b", re.IGNORECASE),
)


def normalize_log_boundaries(text: str) -> str:
    """Insert a line break when two log records were appended without one."""
    previous = None
    while previous != text:
        previous = text
        text = LOG_PREFIX_BOUNDARY_PATTERN.sub(r"\1\n\2", text)
    return text


def compact_output(text: str) -> str:
    text = normalize_log_boundaries(text)
    kept: list[str] = []
    previous = ""
    ends_with_newline = text.endswith("\n")
    for raw in text.splitlines():
        line = raw.rstrip()
        stripped = line.strip()
        if not stripped:
            if kept and kept[-1] != "":
                kept.append("")
            previous = ""
            continue
        if stripped == previous:
            continue
        previous = stripped
        if _is_noise(stripped) and not _is_important(stripped):
            continue
        kept.append(line)
    if not kept:
        return ""
    result = "\n".join(kept)
    if ends_with_newline:
        result += "\n"
    return result


def compact_user_output(text: str) -> str:
    text = compact_output(redact_sensitive(text))
    kept: list[str] = []
    previous = ""
    ends_with_newline = text.endswith("\n")
    for raw in text.splitlines():
        line = raw.rstrip()
        stripped = line.strip()
        if not stripped:
            if kept and kept[-1] != "":
                kept.append("")
            previous = ""
            continue
        if stripped == previous:
            continue
        previous = stripped
        if _is_user_hidden(stripped):
            continue
        kept.append(line)
    if not kept:
        return ""
    result = "\n".join(kept)
    if ends_with_newline:
        result += "\n"
    return result


def compact_technical_output(text: str) -> str:
    text = normalize_log_boundaries(redact_sensitive(text))
    kept: list[str] = []
    previous = ""
    ends_with_newline = text.endswith("\n")
    for raw in text.splitlines():
        line = raw.rstrip()
        stripped = line.strip()
        if not stripped:
            if kept and kept[-1] != "":
                kept.append("")
            previous = ""
            continue
        if stripped == previous:
            continue
        previous = stripped
        kept.append(line)
    if not kept:
        return ""
    result = "\n".join(kept)
    if ends_with_newline:
        result += "\n"
    return result


def redact_sensitive(text: str) -> str:
    for pattern, replacement in SENSITIVE_PATTERNS:
        text = pattern.sub(replacement, text)
    return text


def update_tail(buffer: deque[str], text: str, limit: int = MAX_FAILURE_CONTEXT_LINES) -> None:
    for line in text.splitlines():
        stripped = line.strip()
        if stripped:
            buffer.append(stripped)
    while len(buffer) > limit:
        buffer.popleft()


def failure_summary(title: str, code: int, lines: list[str]) -> str:
    return f"[失败原因] {failure_reason(code, lines, _is_important)}\n"


def _is_noise(line: str) -> bool:
    return any(pattern.search(line) for pattern in NOISE_PATTERNS)


def _is_important(line: str) -> bool:
    return any(pattern.search(line) for pattern in IMPORTANT_PATTERNS)


def _is_user_hidden(line: str) -> bool:
    return any(pattern.search(line) for pattern in USER_HIDDEN_PATTERNS)
