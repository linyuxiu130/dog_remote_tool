from __future__ import annotations

import posixpath
from pathlib import PurePosixPath

from dog_remote_tool.core.profiles import ProductProfile
from dog_remote_tool.core.shell import CommandSpec, echo_message, quote, ssh_command
from dog_remote_tool.modules.file_manager.core import child_path, clean_remote_path, display_path_name, parent_path, validate_delete_path
from dog_remote_tool.modules.file_manager.privilege import sudo_sh


def paste_command(profile: ProductProfile, remote_paths: list[str], target_dir: str, move: bool = False) -> CommandSpec:
    paths = [clean_remote_path(path, profile.home) for path in remote_paths if path]
    target_dir = clean_remote_path(target_dir, profile.home)
    if not paths:
        raise ValueError("未选择可粘贴的远端文件")
    operation = "剪切" if move else "复制"
    shell_command = "mv" if move else "cp -a"
    parts = [
        "set -e",
        f"if [ ! -d {quote(target_dir)} ]; then echo '[ERROR] 粘贴目标不是目录。'; exit 2; fi",
    ]
    for source in paths:
        if move:
            source = validate_delete_path(source, profile)
        basename = PurePosixPath(source).name
        if not basename:
            raise ValueError(f"远端路径不可粘贴：{source}")
        if move and parent_path(source) == target_dir:
            parts.append(echo_message(f"[INFO] 剪切源和目标相同，无需操作：{source}"))
            continue
        target = child_path(target_dir, basename)
        source_arg = quote(source)
        target_arg = quote(target)
        source_missing = f"[ ! -e {source_arg} ] && [ ! -L {source_arg} ]"
        if "." in basename.lstrip("."):
            stem, extension = posixpath.splitext(basename)
        else:
            stem, extension = basename, ""
        prepare_target = f"dest={target_arg}; "
        if move:
            prepare_target += (
                f"if [ -e \"$dest\" ] || [ -L \"$dest\" ]; then "
                f"{echo_message(f'[ERROR] 目标已存在，未覆盖：{target}')}; exit 3; fi; "
            )
        else:
            parent_arg = quote(target_dir.rstrip("/") or "/")
            stem_arg = quote(stem)
            extension_arg = quote(extension)
            prepare_target += (
                "if [ -e \"$dest\" ] || [ -L \"$dest\" ]; then "
                f"parent={parent_arg}; stem={stem_arg}; ext={extension_arg}; "
                "n=1; "
                "while :; do "
                "if [ \"$n\" -eq 1 ]; then dest=\"$parent/${stem}_copy${ext}\"; "
                "else dest=\"$parent/${stem}_copy${n}${ext}\"; fi; "
                "[ ! -e \"$dest\" ] && [ ! -L \"$dest\" ] && break; "
                "n=$((n + 1)); "
                "done; "
                "fi; "
            )
        normal = f"{prepare_target}{shell_command} -- {source_arg} \"$dest\""
        sudo = sudo_sh(
            profile,
            (
                f"if {source_missing}; then {echo_message(f'[ERROR] 源文件不存在：{source}')}; exit 2; "
                f"else {normal}; fi"
            ),
        )
        parts.append(
            f"if {source_missing}; then {echo_message(f'[ERROR] 源文件不存在：{source}')}; exit 2; "
            f"elif {normal} 2>/tmp/dog_remote_paste.err; then "
            f"printf '%s%s\\n' {quote(f'[INFO] 已{operation}: {source} -> ')} \"$dest\"; "
            "else "
            f"{echo_message(f'[WARN] 普通权限{operation}失败，尝试 sudo。')}; "
            f"{sudo} && {echo_message(f'[INFO] 已通过 sudo {operation}: {source} -> {target_dir}')}; "
            "fi"
        )
    return CommandSpec(
        f"{operation}到远端目录",
        ssh_command(profile, "; ".join(parts)),
        display_command=f"{operation}远端选中项到：{display_path_name(target_dir)}",
    )
