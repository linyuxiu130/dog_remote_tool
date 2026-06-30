from __future__ import annotations

import json
import posixpath
from dataclasses import dataclass

from dog_remote_tool.core.markers import extract_marked_payload
from dog_remote_tool.core.profiles import ProductProfile
from dog_remote_tool.core.text import last_nonempty_line
from dog_remote_tool.core.units import format_byte_size


@dataclass(frozen=True)
class RemoteFileItem:
    name: str
    path: str
    kind: str
    size: int
    mtime: float
    mode: str
    owner: str = ""
    group: str = ""


PROTECTED_DELETE_PATHS = {
    "/",
    "/bin",
    "/boot",
    "/dev",
    "/etc",
    "/lib",
    "/lib64",
    "/proc",
    "/run",
    "/sbin",
    "/sys",
    "/usr",
    "/var",
    "/opt/robot",
    "/userdata",
    "/ota",
}
DELETE_ALLOWED_PREFIXES = (
    "/tmp/",
    "/ota/alg_data/",
)


def clean_remote_path(path: str, fallback: str) -> str:
    path = (path or "").strip() or fallback
    if not path.startswith("/"):
        path = posixpath.join(fallback, path)
    return posixpath.normpath(path) or "/"


def parent_path(path: str) -> str:
    path = posixpath.normpath(path or "/")
    parent = posixpath.dirname(path)
    return parent or "/"


def child_path(parent: str, name: str) -> str:
    if parent == "/":
        return "/" + name
    return posixpath.join(parent, name)


def display_path_name(path: str, fallback: str = "当前目录") -> str:
    value = posixpath.normpath(path or "")
    if value in {"", "."}:
        return fallback
    if value == "/":
        return "根目录"
    return posixpath.basename(value.rstrip("/")) or fallback


def validate_name(name: str) -> str:
    value = name.strip()
    if not value:
        raise ValueError("名称不能为空")
    if "/" in value or value in {".", ".."}:
        raise ValueError("名称不能包含 /，也不能是 . 或 ..")
    return value


def validate_delete_path(path: str, profile: ProductProfile | None = None) -> str:
    value = posixpath.normpath(path or "/")
    if value in PROTECTED_DELETE_PATHS:
        raise ValueError(f"禁止删除系统关键路径：{value}")
    if any(value.startswith(prefix) for prefix in DELETE_ALLOWED_PREFIXES):
        return value
    if any(value.startswith(root + "/") for root in PROTECTED_DELETE_PATHS):
        raise ValueError(f"禁止删除系统关键路径：{value}")
    home = posixpath.normpath(profile.home) if profile else ""
    if home and value == home:
        raise ValueError(f"禁止删除账号 Home 根目录：{value}")
    if home and value.startswith(home + "/"):
        return value
    raise ValueError(f"禁止删除未授权路径：{value}。请只在 Home、/tmp、地图数据目录中删除。")


def parse_list_output(text: str) -> tuple[str, list[RemoteFileItem], str]:
    payload_text = extract_marked_payload(text, "DOG_REMOTE_FILE_BEGIN", "DOG_REMOTE_FILE_END")
    if not payload_text:
        return "", [], "未读取到远端目录数据"
    try:
        payload = json.loads(payload_text)
    except json.JSONDecodeError as exc:
        return "", [], f"目录数据解析失败: {exc}"
    items = [
        RemoteFileItem(
            name=str(item.get("name", "")),
            path=str(item.get("path", "")),
            kind=str(item.get("kind", "other")),
            size=int(item.get("size") or 0),
            mtime=float(item.get("mtime") or 0),
            mode=str(item.get("mode", "")),
            owner=str(item.get("owner", "")),
            group=str(item.get("group", "")),
        )
        for item in payload.get("items", [])
        if item.get("name") and item.get("path")
    ]
    return str(payload.get("current") or ""), items, str(payload.get("error") or "")


def parse_preview_output(text: str) -> tuple[dict, str]:
    payload_text = extract_marked_payload(text, "DOG_REMOTE_PREVIEW_BEGIN", "DOG_REMOTE_PREVIEW_END")
    if not payload_text:
        return {}, "未读取到文件预览数据"
    try:
        payload = json.loads(payload_text)
    except json.JSONDecodeError as exc:
        return {}, f"预览数据解析失败: {exc}"
    return payload, str(payload.get("error") or "")


def summarize_list_failure(output: str, exit_code: int, error: str = "") -> str:
    tail = last_nonempty_line(output)
    if "Permission denied" in output:
        return "认证失败，请检查当前设备选择、账号或密码。"
    if "Connection timed out" in output or "No route to host" in output:
        return "连接超时或无路由，请检查 L2 路由、WiFi 和目标 IP。"
    if "Could not resolve hostname" in output:
        return "主机名解析失败，请检查目标地址。"
    if "No such file or directory" in output:
        return "远端目录不存在。"
    if error and tail and error == "未读取到远端目录数据":
        return f"{error}；{tail}"
    if error:
        return error
    if tail:
        return tail
    return f"返回码 {exit_code}"


def format_size(size: int, kind: str = "file") -> str:
    if kind == "dir" and size < 0:
        return "未计算"
    return format_byte_size(max(size, 0))
