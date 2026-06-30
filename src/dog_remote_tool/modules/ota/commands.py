from __future__ import annotations

import shlex
from typing import Callable

from dog_remote_tool.core.shell import CommandSpec


def base_args(
    backend_python: Callable[[], str],
    command: str,
    target: str,
    host: str,
    user: str,
    password: str,
    remote_dir: str,
    package: str = "",
    tools: str = "",
    prepare_only: bool = False,
    skip_mcu: bool = False,
) -> list[str]:
    args = [
        backend_python(),
        "-m",
        "dog_remote_tool.modules.ota.backend",
        command,
        "--target",
        target,
        "-H",
        host,
        "-u",
        user,
        "-p",
        password,
        "-d",
        remote_dir,
    ]
    if package:
        args.extend(["--package", package])
    if tools:
        args.extend(["--tools", tools])
    if prepare_only:
        args.append("--prepare-only")
    if skip_mcu:
        args.append("--skip-mcu")
    return args


def command_text(args: list[str]) -> str:
    return " ".join(shlex.quote(part) for part in args)


def masked_command(command: str, password: str) -> str:
    if not password:
        return command
    try:
        parts = shlex.split(command)
    except ValueError:
        return command
    for index, part in enumerate(parts):
        if part in ("-p", "--password") and index + 1 < len(parts):
            parts[index + 1] = "***"
    return " ".join(shlex.quote(part) for part in parts)


def device_info_command(backend_python: Callable[[], str], target: str, host: str, user: str, password: str, remote_dir: str) -> CommandSpec:
    args = base_args(backend_python, "device-info", target, host, user, password, remote_dir)
    return CommandSpec("读取 OTA 设备信息", command_text(args), concurrency="parallel")


def mcu_maintenance_info_command(
    backend_python: Callable[[], str], target: str, host: str, user: str, password: str, remote_dir: str
) -> CommandSpec:
    args = base_args(backend_python, "device-info", target, host, user, password, remote_dir)
    args.append("--mcu-maintenance")
    return CommandSpec("读取 MCU 版本", command_text(args), description="临时停止 robot-launch.service，读取后自动恢复")


def verify_command(backend_python: Callable[[], str], target: str, host: str, user: str, password: str, remote_dir: str) -> CommandSpec:
    args = base_args(backend_python, "verify", target, host, user, password, remote_dir)
    return CommandSpec("OTA 升级后验证", command_text(args), description="读取远端版本和空间", concurrency="parallel")


def precheck_command(
    backend_python: Callable[[], str],
    target: str,
    host: str,
    user: str,
    password: str,
    remote_dir: str,
    package: str,
    tools: str,
) -> CommandSpec:
    args = base_args(backend_python, "precheck", target, host, user, password, remote_dir, package=package, tools=tools)
    return CommandSpec("OTA 预检", command_text(args), description="校验本地包结构并读取远端版本/空间")


def small_precheck_command(
    backend_python: Callable[[], str],
    target: str,
    host: str,
    user: str,
    password: str,
    remote_dir: str,
    package: str,
) -> CommandSpec:
    args = base_args(backend_python, "small-precheck", target, host, user, password, remote_dir, package=package)
    return CommandSpec("小包部署预检", command_text(args), description="校验本地 deb/whl 小包并读取远端版本/空间")


def prepare_command(
    backend_python: Callable[[], str],
    target: str,
    host: str,
    user: str,
    password: str,
    remote_dir: str,
    package: str,
    tools: str,
) -> CommandSpec:
    args = base_args(
        backend_python,
        "run",
        target,
        host,
        user,
        password,
        remote_dir,
        package=package,
        tools=tools,
        prepare_only=True,
    )
    return CommandSpec("OTA 准备但不刷机", command_text(args), dangerous=True, description="上传、远端校验、解压和准备升级文件")


def upgrade_command(
    backend_python: Callable[[], str],
    target: str,
    host: str,
    user: str,
    password: str,
    remote_dir: str,
    package: str,
    tools: str,
    skip_mcu: bool = False,
) -> CommandSpec:
    args = base_args(
        backend_python,
        "run",
        target,
        host,
        user,
        password,
        remote_dir,
        package=package,
        tools=tools,
        skip_mcu=skip_mcu,
    )
    return CommandSpec("执行 OTA 升级", command_text(args), dangerous=True, description="会执行刷机命令，成功后远端自动重启")


def small_deploy_command(
    backend_python: Callable[[], str],
    target: str,
    host: str,
    user: str,
    password: str,
    remote_dir: str,
    package: str,
) -> CommandSpec:
    args = base_args(backend_python, "small-deploy", target, host, user, password, remote_dir, package=package)
    return CommandSpec("执行小包部署", command_text(args), dangerous=True, description="上传 deb/whl 小包并在远端安装，安装前会停止 robot-launch.service")
