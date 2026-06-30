from __future__ import annotations

import base64
import json
import posixpath

from dog_remote_tool.core.profiles import ProductProfile
from dog_remote_tool.core.shell import CommandSpec, quote, ssh_command
from dog_remote_tool.modules.file_manager.core import child_path, display_path_name, parent_path, validate_delete_path, validate_name
from dog_remote_tool.modules.file_manager.privilege import sudo_exec, sudo_sh


def mkdir_command(profile: ProductProfile, remote_dir: str, name: str) -> CommandSpec:
    safe_name = validate_name(name)
    target = child_path(remote_dir, safe_name)
    target_exists = f"[ -e {quote(target)} ] || [ -L {quote(target)} ]"
    sudo_create = sudo_sh(profile, f"if {target_exists}; then exit 3; else mkdir -p -- {quote(target)}; fi")
    script = (
        f"if {target_exists}; then "
        "echo '[ERROR] 目标已存在，未覆盖。'; exit 3; "
        f"elif mkdir -p -- {quote(target)} 2>/tmp/dog_remote_mkdir.err; then "
        "echo '[INFO] 目录已创建。'; "
        "else "
        "echo '[WARN] 普通权限新建目录失败，尝试 sudo。'; "
        f"{sudo_create} "
        "&& echo '[INFO] 目录已通过 sudo 创建。'; "
        "fi"
    )
    return CommandSpec(
        f"新建目录 {safe_name}",
        ssh_command(profile, script),
        display_command=f"新建远端目录：{display_path_name(target)}",
    )


def touch_command(profile: ProductProfile, remote_dir: str, name: str) -> CommandSpec:
    safe_name = validate_name(name)
    target = child_path(remote_dir, safe_name)
    target_exists = f"[ -e {quote(target)} ] || [ -L {quote(target)} ]"
    sudo_create = sudo_sh(profile, f"if {target_exists}; then exit 3; else : > {quote(target)}; fi")
    script = (
        f"if {target_exists}; then "
        "echo '[ERROR] 目标已存在，未覆盖。'; exit 3; "
        f"elif ( : > {quote(target)} ) 2>/tmp/dog_remote_touch.err; then "
        "echo '[INFO] 文件已创建。'; "
        "else "
        "echo '[WARN] 普通权限新建文件失败，尝试 sudo。'; "
        f"{sudo_create} && echo '[INFO] 文件已通过 sudo 创建。'; "
        "fi"
    )
    return CommandSpec(
        f"新建文件 {safe_name}",
        ssh_command(profile, script),
        display_command=f"新建远端文件：{display_path_name(target)}",
    )


def rename_command(profile: ProductProfile, remote_path: str, new_name: str) -> CommandSpec:
    safe_name = validate_name(new_name)
    target = child_path(parent_path(remote_path), safe_name)
    target_exists = f"[ -e {quote(target)} ] || [ -L {quote(target)} ]"
    source_missing = f"[ ! -e {quote(remote_path)} ] && [ ! -L {quote(remote_path)} ]"
    sudo_move = sudo_sh(
        profile,
        (
            f"if {source_missing}; then "
            "echo '[ERROR] 源文件不存在。'; exit 2; "
            f"elif {target_exists}; then "
            "echo '[ERROR] 目标已存在，未覆盖。'; exit 3; "
            f"else mv -- {quote(remote_path)} {quote(target)}; fi"
        ),
    )
    script = (
        f"if {target_exists}; then "
        "echo '[ERROR] 目标已存在，未覆盖。'; exit 3; "
        f"elif mv -- {quote(remote_path)} {quote(target)} 2>/tmp/dog_remote_mv.err; then "
        "echo '[INFO] 已重命名。'; "
        "else "
        "echo '[WARN] 普通权限重命名失败，尝试 sudo。'; "
        f"{sudo_move} && echo '[INFO] 已通过 sudo 重命名。'; "
        "fi"
    )
    return CommandSpec(
        f"重命名 {posixpath.basename(remote_path)}",
        ssh_command(profile, script),
        display_command=f"重命名远端项目：{display_path_name(remote_path)} -> {display_path_name(target)}",
    )


def delete_command(profile: ProductProfile, remote_paths: list[str]) -> CommandSpec:
    paths = [validate_delete_path(path, profile) for path in remote_paths if path]
    if not paths:
        raise ValueError("未选择可删除的远端文件")
    parts = ["set -e"]
    for path in paths:
        quoted = quote(path)
        parts.append(
            f"rm -rf -- {quoted} 2>/tmp/dog_remote_rm.err || "
            "{ echo '[WARN] 普通权限删除失败，尝试 sudo。'; "
            f"{sudo_sh(profile, 'rm -rf -- ' + quoted)} "
            "&& echo '[INFO] 已通过 sudo 删除。'; "
            "}"
        )
    script = "; ".join(parts)
    return CommandSpec(
        "删除远端文件",
        ssh_command(profile, script),
        dangerous=True,
        display_command=f"删除远端选中项：{len(paths)} 项",
    )


def save_text_command(profile: ProductProfile, remote_path: str, text: str) -> CommandSpec:
    safe_path = posixpath.normpath(remote_path)
    encoded = base64.b64encode(text.encode("utf-8")).decode("ascii")
    code = f"""
import base64
path = {json.dumps(safe_path, ensure_ascii=False)}
data = base64.b64decode({json.dumps(encoded)})
with open(path, "wb") as handle:
    handle.write(data)
"""
    script = (
        f"python3 -c {quote(code)} 2>/tmp/dog_remote_save_text.err || "
        "{ echo '[WARN] 普通权限保存失败，尝试 sudo。'; "
        f"{sudo_exec(profile, 'python3 -c ' + quote(code))} "
        "&& echo '[INFO] 已通过 sudo 保存。'; "
        "}"
    )
    return CommandSpec(
        "保存远端文本",
        ssh_command(profile, script),
        display_command=f"保存远端文本：{display_path_name(safe_path, '文件')}",
    )


def diagnose_command(profile: ProductProfile) -> CommandSpec:
    script = (
        "set +e; "
        "echo '[INFO] SSH 已连接'; "
        "printf '[INFO] 主机: '; hostname; "
        "printf '[INFO] 用户: '; whoami; "
        f"printf '[INFO] Home: {profile.home} '; "
        f"[ -d {quote(profile.home)} ] && echo '存在' || echo '不存在'; "
        f"printf '[INFO] Home权限: '; ls -ld -- {quote(profile.home)} 2>&1; "
        "printf '[INFO] sudo: '; "
        f"{sudo_sh(profile, 'true')} >/dev/null 2>&1 && echo '可用' || echo '不可用或密码错误'"
    )
    return CommandSpec(
        "文件管理连接诊断",
        ssh_command(profile, script),
        display_command="检查文件管理连接",
    )
