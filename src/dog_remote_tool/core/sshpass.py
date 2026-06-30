from __future__ import annotations

import os
import secrets
import tempfile
from pathlib import Path

from .quoting import quote


_SSHPASS_CREATE_ATTEMPTS = 16
_SSHPASS_FILES: dict[str, str] = {}


def sshpass_file(password: str) -> str:
    root = Path(os.environ.get("XDG_RUNTIME_DIR") or tempfile.gettempdir()) / f"dog_remote_tool_sshpass_{os.getuid()}"
    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    try:
        os.chmod(root, 0o700)
    except OSError:
        pass
    cached = _SSHPASS_FILES.get(password)
    if cached:
        path = Path(cached)
    else:
        path = _create_sshpass_file(root)
        _SSHPASS_FILES[password] = str(path)
    flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC
    fd = os.open(path, flags, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        handle.write(password)
        handle.write("\n")
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass
    return str(path)


def sshpass_command(password: str) -> str:
    return f"sshpass -f {quote(sshpass_file(password))}"


def sshpass_argv(password: str) -> list[str]:
    return ["sshpass", "-f", sshpass_file(password)]


def _create_sshpass_file(root: Path) -> Path:
    for _ in range(_SSHPASS_CREATE_ATTEMPTS):
        candidate = root / f"sshpass_{secrets.token_hex(12)}.pass"
        try:
            fd = os.open(candidate, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            os.close(fd)
            return candidate
        except FileExistsError:
            continue
    raise RuntimeError("无法创建 sshpass 临时密码文件，随机文件名连续冲突")
