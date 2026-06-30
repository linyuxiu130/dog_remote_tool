from __future__ import annotations

import posixpath
import uuid
from pathlib import PurePosixPath

from dog_remote_tool.core.markers import extract_marked_payload
from dog_remote_tool.core.profiles import ProductProfile
from dog_remote_tool.core.shell import (
    CommandSpec,
    quote,
    remote_target_path,
    rsync_command,
    ssh_command,
)
from dog_remote_tool.core.text import last_nonempty_line
from dog_remote_tool.modules.file_manager.core import display_path_name
from dog_remote_tool.modules.file_manager.privilege import sudo_sh


def _rsync_progress_command(profile: ProductProfile, source: str, target: str) -> str:
    return rsync_command(
        profile,
        source,
        target,
        options="-avP --partial --info=progress2",
    )


def upload_command(profile: ProductProfile, local_path: str, remote_dir: str) -> CommandSpec:
    remote_target = remote_target_path(profile, remote_dir.rstrip("/") + "/")
    basename = PurePosixPath(local_path).name
    remote_tmp = f"/tmp/dog_remote_upload_{uuid.uuid4().hex}"
    remote_tmp_target = remote_target_path(profile, remote_tmp + "/")
    local_err = f"/tmp/dog_remote_upload_{uuid.uuid4().hex}.err"
    normal = _rsync_progress_command(profile, local_path, remote_target)
    fallback_upload = _rsync_progress_command(profile, local_path, remote_tmp_target)
    fallback_script = (
        f"{ssh_command(profile, 'mkdir -p -- ' + quote(remote_tmp))} && "
        f"{fallback_upload}"
        " && "
        f"{ssh_command(profile, sudo_sh(profile, 'mkdir -p -- ' + quote(remote_dir) + ' && mv -f -- ' + quote(remote_tmp + '/' + basename) + ' ' + quote(remote_dir.rstrip('/') + '/') + ' && rm -rf -- ' + quote(remote_tmp)))}"
        " && echo '[INFO] 已通过 sudo 中转上传。'"
    )
    command = (
        f"{normal} 2>{quote(local_err)} || "
        "{ echo '[WARN] 普通权限上传失败，尝试 sudo 中转上传。'; "
        f"{fallback_script}; rc=$?; "
        f"if [ \"$rc\" -ne 0 ]; then cat {quote(local_err)} 2>/dev/null; fi; "
        f"rm -f -- {quote(local_err)}; exit $rc; "
        "}"
    )
    return CommandSpec(
        "上传文件",
        command,
        display_command=f"上传文件：{display_path_name(local_path, '本地文件')} -> {display_path_name(remote_dir)}",
        concurrency="parallel",
        locks=(f"host:{profile.host}:files:{posixpath.normpath(remote_dir)}",),
    )


def download_command(profile: ProductProfile, remote_path: str, local_dir: str) -> CommandSpec:
    remote_source = remote_target_path(profile, remote_path)
    basename = PurePosixPath(remote_path).name
    remote_tmp = f"/tmp/dog_remote_download_{uuid.uuid4().hex}"
    remote_tmp_source = remote_target_path(profile, remote_tmp + "/" + basename)
    local_err = f"/tmp/dog_remote_download_{uuid.uuid4().hex}.err"
    normal = _rsync_progress_command(profile, remote_source, local_dir.rstrip("/") + "/")
    prepare = (
        f"rm -rf -- {quote(remote_tmp)} && mkdir -p -- {quote(remote_tmp)} && "
        f"cp -a -- {quote(remote_path)} {quote(remote_tmp + '/')} && "
        f"chmod -R a+rX -- {quote(remote_tmp)}"
    )
    cleanup = f"rm -rf -- {quote(remote_tmp)}"
    fallback_download = _rsync_progress_command(profile, remote_tmp_source, local_dir.rstrip("/") + "/")
    fallback = (
        f"{ssh_command(profile, sudo_sh(profile, prepare))} && "
        f"{fallback_download}; "
        "rc=$?; "
        f"{ssh_command(profile, sudo_sh(profile, cleanup))}; "
        "if [ \"$rc\" -eq 0 ]; then echo '[INFO] 已通过 sudo 中转下载。'; fi; "
        "exit $rc"
    )
    command = (
        f"{normal} 2>{quote(local_err)} || "
        "{ echo '[WARN] 普通权限下载失败，尝试 sudo 中转下载。'; "
        f"{fallback}; rc=$?; "
        f"if [ \"$rc\" -ne 0 ]; then cat {quote(local_err)} 2>/dev/null; fi; "
        f"rm -f -- {quote(local_err)}; exit $rc; "
        "}"
    )
    return CommandSpec(
        "下载文件",
        command,
        display_command=f"下载文件：{display_path_name(remote_path, '远端文件')} -> {display_path_name(local_dir, '本地目录')}",
        concurrency="parallel",
    )


def dir_total_size_command(profile: ProductProfile, remote_paths: list[str]) -> CommandSpec:
    paths = [posixpath.normpath(path) for path in remote_paths if path]
    if not paths:
        raise ValueError("未选择要计算大小的远端目录")
    quoted_paths = " ".join(quote(path) for path in paths)
    calc = f"du -sb -- {quoted_paths} | awk 'BEGIN{{s=0}}{{s+=$1}} END{{print \"DOG_REMOTE_SIZE_BEGIN\"; print s+0; print \"DOG_REMOTE_SIZE_END\"}}'"
    script = (
        f"{calc} 2>/tmp/dog_remote_du.err || "
        "{ echo '[WARN] 普通权限计算大小失败，尝试 sudo。'; "
        f"{sudo_sh(profile, calc)}; "
        "}"
    )
    return CommandSpec(
        "计算目录总大小",
        ssh_command(profile, script),
        display_command=f"计算远端选中项大小：{len(paths)} 项",
        concurrency="parallel",
    )


def parse_total_size_output(text: str) -> tuple[int | None, str]:
    payload = extract_marked_payload(text, "DOG_REMOTE_SIZE_BEGIN", "DOG_REMOTE_SIZE_END").strip()
    if payload.isdigit():
        return int(payload), ""
    return None, last_nonempty_line(text) or "未读取到目录大小"
