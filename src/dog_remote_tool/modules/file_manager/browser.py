from __future__ import annotations

import posixpath

from dog_remote_tool.core.profiles import ProductProfile
from dog_remote_tool.core.shell import CommandSpec, echo_message, quote, ssh_command
from dog_remote_tool.modules.file_manager.core import clean_remote_path, display_path_name
from dog_remote_tool.modules.file_manager.privilege import sudo_exec
from dog_remote_tool.modules.file_manager.scripts import list_directory_script, preview_file_script, search_directory_script


def _python_script_with_sudo_fallback(profile: ProductProfile, readable_check: str, code: str, warn_text: str) -> str:
    run_python = "python3 -c " + quote(code)
    return (
        f"if {readable_check}; then "
        f"{run_python}; "
        "else "
        f"{echo_message(f'[WARN] {warn_text}')}; "
        f"{sudo_exec(profile, run_python)}; "
        "fi"
    )


def list_command(profile: ProductProfile, remote_path: str) -> CommandSpec:
    safe_path = clean_remote_path(remote_path, profile.home)
    code = list_directory_script(safe_path)
    script = _python_script_with_sudo_fallback(
        profile,
        f"[ -r {quote(safe_path)} ] && [ -x {quote(safe_path)} ]",
        code,
        "普通权限读取目录失败，尝试 sudo。",
    )
    return CommandSpec(
        "读取远端目录",
        ssh_command(profile, script),
        display_command=f"读取远端目录：{display_path_name(safe_path)}",
    )


def search_command(profile: ProductProfile, remote_path: str, keyword: str, recursive: bool = False) -> CommandSpec:
    safe_path = clean_remote_path(remote_path, profile.home)
    safe_keyword = keyword.strip()
    code = search_directory_script(safe_path, safe_keyword, recursive)
    script = _python_script_with_sudo_fallback(
        profile,
        f"[ -r {quote(safe_path)} ] && [ -x {quote(safe_path)} ]",
        code,
        "普通权限搜索目录失败，尝试 sudo。",
    )
    return CommandSpec(
        "搜索远端文件",
        ssh_command(profile, script),
        display_command=f"搜索远端文件：{display_path_name(safe_path)} / {safe_keyword}",
    )


def preview_command(profile: ProductProfile, remote_path: str, max_bytes: int = 131_072) -> CommandSpec:
    safe_path = posixpath.normpath(remote_path)
    code = preview_file_script(safe_path, max_bytes)
    script = _python_script_with_sudo_fallback(
        profile,
        f"[ -r {quote(safe_path)} ] && [ -f {quote(safe_path)} ]",
        code,
        "普通权限预览失败，尝试 sudo。",
    )
    return CommandSpec(
        "预览远端文件",
        ssh_command(profile, script),
        display_command=f"预览远端文件：{display_path_name(safe_path, '文件')}",
        concurrency="parallel",
    )
