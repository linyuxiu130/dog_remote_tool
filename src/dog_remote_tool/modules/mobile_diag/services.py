from __future__ import annotations

from dog_remote_tool.core.network_routes import with_route_repair
from dog_remote_tool.core.profiles import ProductProfile
from dog_remote_tool.core.shell import CommandSpec, quote, ssh_command, ssh_prefix_command, sudo_run_shell


def _ssh_prefix(profile: ProductProfile) -> str:
    return ssh_prefix_command(profile)


def script_printer_command() -> str:
    return "python3 -m dog_remote_tool.modules.mobile_diag --print-script"


def diag_command(profile: ProductProfile) -> CommandSpec:
    command = f"{script_printer_command()} | {_ssh_prefix(profile)} {quote('bash -s')}"
    return CommandSpec(
        "4G/5G 完整诊断",
        with_route_repair(profile, command),
        display_command="执行：4G/5G 完整诊断",
        concurrency="parallel",
    )


def recover_and_diag_command(profile: ProductProfile) -> CommandSpec:
    inner = (
        "set -e; "
        "if ! (systemctl cat quectel-cm.service >/dev/null 2>&1 || [ -f /etc/systemd/system/quectel-cm.service ] || [ -f /lib/systemd/system/quectel-cm.service ]); then "
        "echo '[WARN] 当前设备未安装 quectel-cm.service。'; "
        "echo '[WARN] 请选择带 4G/5G 模块的 3588 端，或先确认远端镜像已部署拨号服务。'; "
        "exit 0; "
        "fi; "
        "echo '[INFO] 启用 quectel-cm.service 开机自启'; "
        "sudo systemctl enable quectel-cm.service >/dev/null; "
        "echo '[INFO] 启动/重启 quectel-cm.service'; "
        "sudo systemctl restart quectel-cm.service || sudo systemctl start quectel-cm.service; "
        "echo '[INFO] 等待模块日志刷新'; "
        "sleep 10; "
        "bash -s"
    )
    command = f"{script_printer_command()} | {_ssh_prefix(profile)} {quote(inner)}"
    return CommandSpec(
        "检测并恢复 4G/5G 网络服务",
        with_route_repair(profile, command),
        display_command="执行：检测并恢复 4G/5G 网络服务",
    )


def service_status_command(profile: ProductProfile) -> CommandSpec:
    inner = (
        sudo_run_shell(fallback_without_sudo=False) +
        "echo '== quectel-cm.service =='; "
        "systemctl is-enabled quectel-cm.service 2>/dev/null || true; "
        "systemctl is-active quectel-cm.service 2>/dev/null || true; "
        "systemctl --no-pager --full status quectel-cm.service 2>/dev/null | sed -n '1,18p' || true; "
        "echo '== latest logs =='; "
        "sudo_run journalctl -u quectel-cm.service -n 30 --no-pager || true"
    )
    return CommandSpec("查看 quectel-cm 服务状态", ssh_command(profile, inner), display_command="执行：查看 quectel-cm 服务状态", concurrency="parallel")


def restart_service_command(profile: ProductProfile) -> CommandSpec:
    inner = (
        "set -e; "
        + sudo_run_shell(fallback_without_sudo=False)
        + "if ! (systemctl cat quectel-cm.service >/dev/null 2>&1 || "
        "[ -f /etc/systemd/system/quectel-cm.service ] || "
        "[ -f /lib/systemd/system/quectel-cm.service ]); then "
        "echo '[ERROR] 未找到 quectel-cm.service'; exit 1; "
        "fi; "
        "echo '[INFO] 启动/重启 quectel-cm.service'; "
        "sudo_run systemctl restart quectel-cm.service || sudo_run systemctl start quectel-cm.service; "
        "sleep 3; "
        "echo '[INFO] 当前状态:'; "
        "systemctl is-active quectel-cm.service || true; "
        "sudo_run journalctl -u quectel-cm.service -n 20 --no-pager || true"
    )
    return CommandSpec("启动/重启 quectel-cm", ssh_command(profile, inner), display_command="执行：启动/重启 quectel-cm")


def enable_service_command(profile: ProductProfile) -> CommandSpec:
    inner = (
        "set -e; "
        + sudo_run_shell(fallback_without_sudo=False)
        + "if ! (systemctl cat quectel-cm.service >/dev/null 2>&1 || "
        "[ -f /etc/systemd/system/quectel-cm.service ] || "
        "[ -f /lib/systemd/system/quectel-cm.service ]); then "
        "echo '[ERROR] 未找到 quectel-cm.service'; exit 1; "
        "fi; "
        "echo '[INFO] 设置 quectel-cm.service 开机自启'; "
        "sudo_run systemctl enable quectel-cm.service; "
        "echo '[INFO] enabled='$(systemctl is-enabled quectel-cm.service 2>/dev/null || true); "
        "echo '[INFO] active='$(systemctl is-active quectel-cm.service 2>/dev/null || true)"
    )
    return CommandSpec("启用 quectel-cm 开机自启", ssh_command(profile, inner), display_command="执行：启用 quectel-cm 开机自启")


def reboot_command(profile: ProductProfile) -> CommandSpec:
    inner = (
        sudo_run_shell(fallback_without_sudo=False) +
        "echo '[INFO] 即将重启远端设备'; "
        "sudo_run systemctl enable quectel-cm.service >/dev/null 2>&1 || true; "
        "sudo_run reboot"
    )
    return CommandSpec("重启远端设备", ssh_command(profile, inner), dangerous=True, display_command="执行：重启远端设备")
