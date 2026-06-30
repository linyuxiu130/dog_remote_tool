from __future__ import annotations

from datetime import datetime

from .. import __version__
from ..core.paths import version_file


def source_runtime_detail() -> str:
    try:
        version = version_file().read_text(encoding="utf-8").strip()
    except OSError:
        version = __version__
    started_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    return f"版本 {version or __version__} | 启动时间 {started_at}"
