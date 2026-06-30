from __future__ import annotations

import re
import time

from PyQt5.QtGui import QColor, QFont, QFontMetricsF, QSyntaxHighlighter, QTextCharFormat
from PyQt5.QtWidgets import QPlainTextEdit

from dog_remote_tool.core.log_filter import normalize_log_boundaries, redact_sensitive
from dog_remote_tool.core.text import ANSI_PATTERN as TEXT_ANSI_PATTERN
from dog_remote_tool.core.text import CONTROL_PATTERN as TEXT_CONTROL_PATTERN
from dog_remote_tool.core.text import strip_ansi, strip_control_chars


LOG_TIMESTAMP_PATTERN = re.compile(r"^\[\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\]\s*")


class LogHighlighter(QSyntaxHighlighter):
    def __init__(self, parent) -> None:
        super().__init__(parent)
        self.command_format = self.make_format("#93c5fd", bold=True)
        self.info_format = self.make_format("#86efac")
        self.success_format = self.make_format("#34d399", bold=True)
        self.warn_format = self.make_format("#fbbf24", bold=True)
        self.error_format = self.make_format("#f87171", bold=True)
        self.meta_format = self.make_format("#67e8f9")

    def make_format(self, color: str, bold: bool = False) -> QTextCharFormat:
        text_format = QTextCharFormat()
        text_format.setForeground(QColor(color))
        if bold:
            text_format.setFontWeight(QFont.Bold)
        return text_format

    @staticmethod
    def classify_line(text: str) -> str:
        visible_text = LOG_TIMESTAMP_PATTERN.sub("", text, count=1)
        lowered = visible_text.lower()
        stripped = visible_text.strip()
        if stripped.startswith("[任务 ") and " 开始：" in stripped:
            return "command"
        if stripped.startswith("[任务 ") and " 完成：" in stripped:
            return "success"
        if stripped.startswith("[任务 ") and " 失败：" in stripped:
            return "error"
        if stripped.startswith("[任务 ") and " [错误] " in stripped:
            return "error"
        if stripped.startswith("[任务 ") and " [警告] " in stripped:
            return "warn"
        if stripped.startswith("[任务 ") and " [信息] " in stripped:
            return "info"
        if visible_text.startswith("$ ") or stripped.startswith("[命令]"):
            return "command"
        if stripped.startswith(("[完成]", "[信息] 完成")) or "success=true" in lowered or "successfully" in lowered:
            return "success"
        if (
            stripped.startswith("[失败]")
            or stripped.startswith("[错误]")
            or stripped.startswith("[error]")
            or stripped.startswith("error:")
            or "traceback" in lowered
            or "exception" in lowered
        ):
            return "error"
        if stripped.startswith("[警告]") or stripped.startswith("[warn]") or stripped.startswith("warning"):
            return "warn"
        if stripped.startswith("requester:") or stripped.startswith("response:"):
            return "meta"
        if stripped.startswith("[信息]") or stripped.startswith("[info]"):
            return "info"
        return ""

    def highlightBlock(self, text: str) -> None:
        formats = {
            "command": self.command_format,
            "success": self.success_format,
            "error": self.error_format,
            "warn": self.warn_format,
            "meta": self.meta_format,
            "info": self.info_format,
        }
        text_format = formats.get(self.classify_line(text))
        if text_format is not None:
            self.setFormat(0, len(text), text_format)


class LogPanel(QPlainTextEdit):
    MAX_LOG_LINE_CHARS = 4096
    ANSI_PATTERN = TEXT_ANSI_PATTERN
    CONTROL_PATTERN = TEXT_CONTROL_PATTERN
    LEVEL_ALIASES = (
        (re.compile(r"^((?:\[任务 \d+\]\s*)?)\[INFO\]\s*", re.IGNORECASE), r"\1[信息] "),
        (re.compile(r"^((?:\[任务 \d+\]\s*)?)\[WARN(?:ING)?\]\s*", re.IGNORECASE), r"\1[警告] "),
        (re.compile(r"^((?:\[任务 \d+\]\s*)?)\[ERROR\]\s*", re.IGNORECASE), r"\1[错误] "),
        (re.compile(r"^((?:\[任务 \d+\]\s*)?)\$\s*"), r"\1[命令] "),
    )
    DIAGNOSTIC_LINE_PREFIXES = (
        "ALG_MAPPING_STATUS=",
        "ALG_MAPPING_SOURCE=",
        "SLAM_ERROR_CODE=",
        "SLAM_ERROR_MSG=",
    )
    DIAGNOSTIC_ASSIGNMENT_PATTERN = re.compile(r"^(?:\[任务 \d+\]\s*)?[A-Z][A-Z0-9_]{2,}=")
    DIAGNOSTIC_APP_RESPONSE_OK_PATTERN = re.compile(
        r"^(?:\[任务 \d+\]\s*)?(?:\[(?:INFO|信息)\]\s*)?响应[:：]\s*func=\w+\s+status=ok\b",
        re.IGNORECASE,
    )
    DIAGNOSTIC_MAPPING_APP_COMMAND_PATTERN = re.compile(
        r"^(?:\[任务 \d+\]\s*)?(?:\[(?:INFO|信息)\]\s*)?已发送(?:开始|结束保存|取消)?建图[:：]\s*"
        r"(?:start_mapping|stop_mapping|cancel_mapping)\b",
        re.IGNORECASE,
    )
    MAPPING_STATUS_RAW_PATTERN = re.compile(r"(建图状态[:：][^\n（(]+)[（(][A-Za-z0-9_]+[）)]")
    RTSP_URL_PATTERN = re.compile(r"rtsp://[^\s，。；,;]+", re.IGNORECASE)
    LOCAL_TOOL_PATH_PATTERN = re.compile(r"/home/user/测试工具/dog_remote_tool[^\s，。；,;]*")
    PRIVATE_ADDRESS_PATTERN = re.compile(r"\b(?:127\.0\.0\.1|192\.168\.\d{1,3}\.\d{1,3})(?::\d+)?\b")
    SSH_TARGET_PATTERN = re.compile(r"\b[A-Za-z_][A-Za-z0-9_.-]*@(?:127\.0\.0\.1|192\.168\.\d{1,3}\.\d{1,3})\b")
    USER_DROP_PATTERNS = (
        re.compile(r"^(?:\[任务 \d+\]\s*)?\[RTSP\]\s*准备远端媒体服务\b", re.IGNORECASE),
        re.compile(r"^(?:\[任务 \d+\]\s*)?\[RTSP\]\s*远端 .+已响应", re.IGNORECASE),
        re.compile(r"^(?:\[任务 \d+\]\s*)?\[RTSP\]\s*远端路径\b", re.IGNORECASE),
        re.compile(r"^(?:\[任务 \d+\]\s*)?\[RTSP\]\s*本地将直连播放\b", re.IGNORECASE),
        re.compile(r"^(?:\[任务 \d+\]\s*)?sdk_root\s*=", re.IGNORECASE),
        re.compile(r"^(?:\[任务 \d+\]\s*)?lib_path\s*=", re.IGNORECASE),
        re.compile(r"^(?:\[任务 \d+\]\s*)?python_import\s*=", re.IGNORECASE),
        re.compile(r"^(?:\[任务 \d+\]\s*)?init\s*=", re.IGNORECASE),
    )
    USER_REWRITE_PATTERNS = (
        (
            re.compile(r"^(.*)RTSP\s+已连接(?:\([^)]*\))?:\s*rtsp://.*$", re.IGNORECASE),
            r"\1视频已连接。",
        ),
        (
            re.compile(r"^(.*)RTSP\s+第\s+\d+\s+次连接成功:\s*rtsp://.*$", re.IGNORECASE),
            r"\1视频已连接。",
        ),
        (
            re.compile(r"^(.*)RTSP\s+等待视频服务就绪:\s*rtsp://.*$", re.IGNORECASE),
            r"\1正在等待视频服务。",
        ),
        (
            re.compile(r"^(.*)RTSP\s+打开失败:\s*rtsp://.*$", re.IGNORECASE),
            r"\1视频打开失败，请检查视频服务或网络。",
        ),
        (
            re.compile(r"^(.*)RTSP\s+读取失败\(\d+\):\s*rtsp://.*$", re.IGNORECASE),
            r"\1视频读取失败，请检查视频服务或网络。",
        ),
        (
            re.compile(r"^(.*)RTSP\s+打开失败.*$", re.IGNORECASE),
            r"\1视频打开失败，请检查视频服务或网络。",
        ),
        (
            re.compile(r"^(.*)RTSP\s+读取失败.*$", re.IGNORECASE),
            r"\1视频读取失败，请检查视频服务或网络。",
        ),
        (
            re.compile(r"^(.*)RTSP\s+已连接.*$", re.IGNORECASE),
            r"\1视频已连接。",
        ),
        (
            re.compile(r"^(\[任务 \d+\]\s*)开始：准备 RTSP 视频:.*$", re.IGNORECASE),
            r"\1开始：准备视频",
        ),
        (
            re.compile(r"^(\[任务 \d+\]\s*)完成：准备 RTSP 视频:.*$", re.IGNORECASE),
            r"\1完成：准备视频",
        ),
        (
            re.compile(r"^(.*)已连接\s+robot_remote\s+websocket:\s*.+$", re.IGNORECASE),
            r"\1遥控连接已建立。",
        ),
        (
            re.compile(r"^(.*)\bERROR:\s*(.+)$", re.IGNORECASE),
            r"\1错误：\2",
        ),
        (
            re.compile(r"^(.*)\[目标\]\s*公网 SSH:.*$", re.IGNORECASE),
            r"\1[目标] 正在测试公网连接。",
        ),
        (
            re.compile(r"^(.*)公网地址:\s*\S+@\S+.*$", re.IGNORECASE),
            r"\1公网连接信息已生成。",
        ),
        (
            re.compile(r"^(.*)(?:连接命令|交互命令):\s*ssh\b.*$", re.IGNORECASE),
            r"\1连接信息已生成。",
        ),
        (
            re.compile(r"^(.*)\bcode=\d+\b.*$", re.IGNORECASE),
            r"\1执行失败，请查看详细日志。",
        ),
        (
            re.compile(r"^(.*)返回码\s+\d+.*$"),
            r"\1执行失败，请查看详细日志。",
        ),
    )

    def __init__(self, parent=None, *, mode: str = "user") -> None:
        super().__init__(parent)
        self.mode = mode
        self._timestamp_next_line = True
        self.setObjectName("Log")
        self.setReadOnly(True)
        log_font = QFont("DejaVu Sans Mono")
        log_font.setPointSize(10)
        self.setFont(log_font)
        self.document().setDocumentMargin(12)
        self.setTabStopDistance(QFontMetricsF(log_font).horizontalAdvance(" ") * 4)
        self.setLineWrapMode(QPlainTextEdit.WidgetWidth)
        self.setMaximumBlockCount(5000)
        self.highlighter = LogHighlighter(self.document())

    def append_text(self, text: str) -> None:
        text = self.clean_text(text, mode=self.mode)
        text = self.add_timestamps(text)
        self.moveCursor(self.textCursor().End)
        self.insertPlainText(text)
        self.moveCursor(self.textCursor().End)

    def clear(self) -> None:
        self._timestamp_next_line = True
        super().clear()

    @classmethod
    def clean_text(cls, text: str, *, mode: str = "user") -> str:
        text = strip_ansi(text)
        text = text.replace("\r\n", "\n").replace("\r", "\n")
        text = strip_control_chars(text)
        text = normalize_log_boundaries(text)
        text = redact_sensitive(text)
        text = cls.normalize_visible_lines(text, mode=mode)
        return cls.wrap_long_lines(text)

    @staticmethod
    def current_timestamp() -> str:
        return time.strftime("%Y-%m-%d %H:%M:%S")

    @classmethod
    def timestamp_line(cls, line: str, timestamp: str | None = None) -> str:
        if not line.strip() or LOG_TIMESTAMP_PATTERN.match(line):
            return line
        return f"[{timestamp or cls.current_timestamp()}] {line}"

    def add_timestamps(self, text: str) -> str:
        timestamp = self.current_timestamp()
        stamped_text, next_line = self.timestamp_text(text, timestamp, self._timestamp_next_line)
        self._timestamp_next_line = next_line
        return stamped_text

    @classmethod
    def timestamp_text(cls, text: str, timestamp: str, timestamp_next_line: bool = True) -> tuple[str, bool]:
        stamped: list[str] = []
        for segment in text.splitlines(keepends=True):
            line = segment[:-1] if segment.endswith("\n") else segment
            newline = "\n" if segment.endswith("\n") else ""
            if timestamp_next_line:
                line = cls.timestamp_line(line, timestamp)
            stamped.append(line + newline)
            if line.strip():
                timestamp_next_line = bool(newline)
            elif newline:
                timestamp_next_line = True
        return "".join(stamped), timestamp_next_line

    @classmethod
    def normalize_visible_lines(cls, text: str, *, mode: str = "user") -> str:
        normalized: list[str] = []
        technical = mode == "technical"
        for segment in text.splitlines(keepends=True):
            line = segment[:-1] if segment.endswith("\n") else segment
            newline = "\n" if segment.endswith("\n") else ""
            stripped = line.strip()
            if not technical and (
                stripped.startswith(cls.DIAGNOSTIC_LINE_PREFIXES)
                or cls.DIAGNOSTIC_ASSIGNMENT_PATTERN.match(stripped)
                or cls.DIAGNOSTIC_APP_RESPONSE_OK_PATTERN.match(stripped)
                or cls.DIAGNOSTIC_MAPPING_APP_COMMAND_PATTERN.match(stripped)
            ):
                continue
            if not technical and any(pattern.search(stripped) for pattern in cls.USER_DROP_PATTERNS):
                continue
            for pattern, replacement in cls.LEVEL_ALIASES:
                line = pattern.sub(replacement, line, count=1)
            if not technical:
                for pattern, replacement in cls.USER_REWRITE_PATTERNS:
                    line = pattern.sub(replacement, line, count=1)
                line = cls.RTSP_URL_PATTERN.sub("视频地址", line)
                line = cls.LOCAL_TOOL_PATH_PATTERN.sub("工具目录", line)
                line = cls.SSH_TARGET_PATTERN.sub("设备账号", line)
                line = cls.PRIVATE_ADDRESS_PATTERN.sub("设备地址", line)
            line = cls.MAPPING_STATUS_RAW_PATTERN.sub(r"\1", line)
            normalized.append(line + newline)
        return "".join(normalized)

    @classmethod
    def wrap_long_lines(cls, text: str, max_chars: int | None = None) -> str:
        limit = max_chars or cls.MAX_LOG_LINE_CHARS
        if limit <= 0:
            return text
        wrapped: list[str] = []
        for segment in text.splitlines(keepends=True):
            line = segment[:-1] if segment.endswith("\n") else segment
            newline = "\n" if segment.endswith("\n") else ""
            while len(line) > limit:
                wrapped.append(line[:limit] + "\n")
                line = line[limit:]
            wrapped.append(line + newline)
        return "".join(wrapped)
