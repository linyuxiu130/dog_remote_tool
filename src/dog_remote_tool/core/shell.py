from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass
from pathlib import Path

from .network_routes import with_route_repair
from .profiles import ProductProfile
from .quoting import quote
from .sshpass import sshpass_argv as _sshpass_argv
from .sshpass import sshpass_command, sshpass_file


SSH_OPTIONS = (
    "-o StrictHostKeyChecking=no",
    "-o UserKnownHostsFile=/dev/null",
    "-o GlobalKnownHostsFile=/dev/null",
    "-o LogLevel=ERROR",
    "-o ConnectTimeout=6",
)

sshpass_argv = _sshpass_argv

@dataclass(frozen=True)
class CommandSpec:
    title: str
    command: str
    dangerous: bool = False
    description: str = ""
    display_command: str = ""
    concurrency: str = "exclusive"
    locks: tuple[str, ...] = ()


def echo_message(text: str) -> str:
    return f"printf '%s\\n' {quote(text)}"


def sudo_run_shell(*, fallback_without_sudo: bool = True, probe_sudo: bool = False) -> str:
    if probe_sudo and fallback_without_sudo:
        return (
            "sudo_ok=0; "
            "if command -v sudo >/dev/null 2>&1 && printf '%s\\n' \"$DOG_REMOTE_SUDO_PASS\" | sudo -S -p '' true >/dev/null 2>&1; then sudo_ok=1; fi; "
            "sudo_run() { "
            "if [ \"$sudo_ok\" = 1 ]; then printf '%s\\n' \"$DOG_REMOTE_SUDO_PASS\" | sudo -S -p '' \"$@\"; "
            "else \"$@\"; fi; "
            "}; "
        )
    if fallback_without_sudo:
        return (
            "sudo_run() { "
            "if command -v sudo >/dev/null 2>&1; then printf '%s\\n' \"$DOG_REMOTE_SUDO_PASS\" | sudo -S -p '' \"$@\"; "
            "else \"$@\"; fi; "
            "}; "
        )
    return "sudo_run() { printf '%s\\n' \"$DOG_REMOTE_SUDO_PASS\" | sudo -S -p '' \"$@\"; }; "


def _ssh_option_strings(
    connect_timeout: int | None = None,
    *,
    include_connect_timeout: bool = True,
    server_alive_interval: int | None = None,
    server_alive_count_max: int | None = None,
) -> list[str]:
    options = []
    for option in SSH_OPTIONS:
        if connect_timeout is not None and option.startswith("-o ConnectTimeout="):
            options.append(f"-o ConnectTimeout={connect_timeout}")
        elif not include_connect_timeout and option.startswith("-o ConnectTimeout="):
            continue
        else:
            options.append(option)
    if server_alive_interval is not None:
        options.append(f"-o ServerAliveInterval={server_alive_interval}")
    if server_alive_count_max is not None:
        options.append(f"-o ServerAliveCountMax={server_alive_count_max}")
    return options


def _ssh_control_enabled() -> bool:
    return os.environ.get("DOG_REMOTE_TOOL_SSH_CONTROL", "").strip().lower() not in {"0", "false", "no", "off"}


def _ssh_jump_control_enabled() -> bool:
    return os.environ.get("DOG_REMOTE_TOOL_SSH_CONTROL_JUMP", "").strip().lower() in {"1", "true", "yes", "on"}


def _ssh_control_path_for(*parts: str) -> str:
    identity = "|".join(parts)
    digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:20]
    return str(_ssh_control_dir() / f"{digest}.sock")


def _ssh_control_path(profile: ProductProfile) -> str:
    return _ssh_control_path_for(
        str(getattr(profile, "user", "")),
        str(getattr(profile, "host", "")),
        str(getattr(profile, "jump_user", "")),
        str(getattr(profile, "jump_host", "")),
    )


def _ssh_control_dir() -> Path:
    root = os.environ.get("XDG_RUNTIME_DIR")
    temp_root = os.environ.get("TMPDIR") or "/tmp"
    directory = Path(root) / "dog_remote_tool_ssh_control" if root else Path(temp_root) / f"dog_remote_tool_ssh_control_{os.getuid()}"
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    try:
        directory.chmod(0o700)
    except OSError:
        pass
    return directory


def _ssh_control_options(profile: ProductProfile) -> list[str]:
    if not _ssh_control_enabled():
        return []
    if _has_jump_host(profile) and not _ssh_jump_control_enabled():
        return []
    return [
        "-o ControlMaster=auto",
        "-o ControlPersist=10m",
        f"-o ControlPath={_ssh_control_path(profile)}",
    ]


def _ssh_jump_control_options(profile: ProductProfile) -> list[str]:
    if not _ssh_control_enabled() or not _ssh_jump_control_enabled() or not _has_jump_host(profile):
        return []
    return [
        "-o ControlMaster=auto",
        "-o ControlPersist=10m",
        f"-o ControlPath={_ssh_control_path_for(str(profile.jump_user), str(profile.jump_host))}",
    ]


def ssh_options(connect_timeout: int | None = None) -> str:
    options = _ssh_option_strings(connect_timeout)
    return " ".join(options)


def ssh_options_argv(
    connect_timeout: int | None = None,
    *,
    include_connect_timeout: bool = True,
    server_alive_interval: int | None = None,
    server_alive_count_max: int | None = None,
) -> list[str]:
    args: list[str] = []
    for option in _ssh_option_strings(
        connect_timeout,
        include_connect_timeout=include_connect_timeout,
        server_alive_interval=server_alive_interval,
        server_alive_count_max=server_alive_count_max,
    ):
        prefix = "-o "
        if option.startswith(prefix):
            args.extend(["-o", option[len(prefix):]])
        else:
            args.append(option)
    return args


def _ssh_option_argv_items(options: list[str]) -> list[str]:
    args: list[str] = []
    for option in options:
        prefix = "-o "
        if option.startswith(prefix):
            args.extend(["-o", option[len(prefix):]])
        else:
            args.append(option)
    return args


def ssh_options_argv_for_profile(
    profile: ProductProfile,
    connect_timeout: int | None = None,
    *,
    include_connect_timeout: bool = True,
    server_alive_interval: int | None = None,
    server_alive_count_max: int | None = None,
) -> list[str]:
    args = ssh_options_argv(
        connect_timeout,
        include_connect_timeout=include_connect_timeout,
        server_alive_interval=server_alive_interval,
        server_alive_count_max=server_alive_count_max,
    )
    args.extend(_ssh_option_argv_items(_ssh_control_options(profile)))
    proxy = _proxy_command(profile, connect_timeout)
    if proxy:
        args.extend(["-o", f"ProxyCommand={proxy}"])
    return args


def _has_jump_host(profile: ProductProfile) -> bool:
    return bool(
        getattr(profile, "jump_host", "")
        and getattr(profile, "jump_user", "")
        and getattr(profile, "jump_password", "")
    )


def _proxy_command(profile: ProductProfile, connect_timeout: int | None = None) -> str:
    if not _has_jump_host(profile):
        return ""
    jump_target = f"{profile.jump_user}@{profile.jump_host}"
    options = " ".join([ssh_options(connect_timeout), *_ssh_jump_control_options(profile)]).strip()
    return (
        f"{sshpass_command(profile.jump_password)} ssh "
        f"{options} -W %h:%p {quote(jump_target)}"
    )


def _ssh_options_for_profile(profile: ProductProfile, connect_timeout: int | None = None) -> str:
    options = " ".join([ssh_options(connect_timeout), *_ssh_control_options(profile)]).strip()
    proxy = _proxy_command(profile, connect_timeout)
    if proxy:
        options = f"{options} -o ProxyCommand={quote(proxy)}"
    return options


def _with_transport_setup(profile: ProductProfile, command: str) -> str:
    if _has_jump_host(profile):
        return command
    return with_route_repair(profile, command)


def _rsync_ssh_command(profile: ProductProfile, connect_timeout: int | None = None) -> str:
    return "ssh " + _ssh_options_for_profile(profile, connect_timeout)


def ssh_prefix_command(profile: ProductProfile, connect_timeout: int | None = None, *, tty: bool = False) -> str:
    ssh = "ssh -tt" if tty else "ssh"
    return f"{sshpass_command(profile.password)} {ssh} {_ssh_options_for_profile(profile, connect_timeout)} {quote(profile.target)}"


def remote_target_path(profile: ProductProfile, remote_path: str) -> str:
    return f"{profile.target}:{remote_path}"


def _scp_command(profile: ProductProfile, source: str, target: str, *, connect_timeout: int) -> str:
    command = (
        f"{sshpass_command(profile.password)} scp {_ssh_options_for_profile(profile, connect_timeout)} "
        f"{quote(source)} {quote(target)}"
    )
    return _with_transport_setup(profile, command)


def scp_pull_command(profile: ProductProfile, remote_path: str, local_path: str, *, connect_timeout: int = 20) -> str:
    return _scp_command(
        profile,
        remote_target_path(profile, remote_path),
        local_path,
        connect_timeout=connect_timeout,
    )


def scp_push_command(profile: ProductProfile, local_path: str, remote_path: str, *, connect_timeout: int = 20) -> str:
    return _scp_command(
        profile,
        local_path,
        remote_target_path(profile, remote_path),
        connect_timeout=connect_timeout,
    )


def remote_env(profile: ProductProfile) -> str:
    return (
        "if [ -f /opt/runtime/env.bash ]; then source /opt/runtime/env.bash >/dev/null 2>&1; "
        "else source /opt/ros/humble/setup.bash >/dev/null 2>&1 || true; fi; "
        f"export ROS_DOMAIN_ID={quote(profile.ros_domain_id)}; "
        f"export RMW_IMPLEMENTATION={quote(profile.rmw)}; "
        "export ROS_LOCALHOST_ONLY=0; "
        "export ZENOH_CONFIG_OVERRIDE='transport/shared_memory/enabled=false'; "
        "export ROS_LOG_DIR=${ROS_LOG_DIR:-/tmp/dog_remote_ros_log_$(id -un 2>/dev/null || echo robot)}; "
        'mkdir -p "$ROS_LOG_DIR"'
    )


def ssh_command(profile: ProductProfile, remote_command: str) -> str:
    pass_file = sshpass_file(profile.password)
    wrapped = (
        "IFS= read -r DOG_REMOTE_SUDO_PASS || DOG_REMOTE_SUDO_PASS=; "
        "export DOG_REMOTE_SUDO_PASS; "
        f"{remote_command}"
    )
    command = (
        f"{ssh_prefix_command(profile)} {quote(wrapped)} < {quote(pass_file)}"
    )
    return _with_transport_setup(profile, command)


def rsync_prefix_command(
    profile: ProductProfile,
    *,
    options: str = "-avP",
    connect_timeout: int | None = None,
) -> str:
    return (
        f"{sshpass_command(profile.password)} rsync {options} "
        f"-e {quote(_rsync_ssh_command(profile, connect_timeout))}"
    )


def rsync_command(
    profile: ProductProfile,
    source: str,
    target: str,
    *,
    options: str = "-avP",
    connect_timeout: int | None = None,
) -> str:
    command = (
        f"{rsync_prefix_command(profile, options=options, connect_timeout=connect_timeout)} "
        f"{quote(source)} {quote(target)}"
    )
    return _with_transport_setup(profile, command)


def rsync_pull_command(
    profile: ProductProfile,
    remote_path: str,
    local_dir: str,
    *,
    options: str = "-avP",
    connect_timeout: int | None = None,
) -> str:
    return rsync_command(
        profile,
        remote_target_path(profile, remote_path),
        local_dir,
        options=options,
        connect_timeout=connect_timeout,
    )


def rsync_push_command(
    profile: ProductProfile,
    local_path: str,
    remote_dir: str,
    *,
    options: str = "-avP",
    connect_timeout: int | None = None,
) -> str:
    return rsync_command(
        profile,
        local_path,
        remote_target_path(profile, remote_dir),
        options=options,
        connect_timeout=connect_timeout,
    )
