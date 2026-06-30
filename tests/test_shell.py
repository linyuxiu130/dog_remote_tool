import os
from pathlib import Path

import pytest

from dog_remote_tool.core.profiles import ProductProfile, get_product
from dog_remote_tool.core.quoting import yaml_string
from dog_remote_tool.core import sshpass as sshpass_module
from dog_remote_tool.core.shell import (
    echo_message,
    quote,
    remote_env,
    remote_target_path,
    rsync_command,
    rsync_prefix_command,
    rsync_pull_command,
    rsync_push_command,
    scp_pull_command,
    scp_push_command,
    ssh_command,
    ssh_options,
    ssh_options_argv,
    ssh_options_argv_for_profile,
    ssh_prefix_command,
    sshpass_argv,
    sshpass_file,
    sudo_run_shell,
)


def test_quote_shell_escapes_spaces_and_quotes():
    assert quote("a b'c") == "'a b'\"'\"'c'"


def test_echo_message_quotes_text_for_remote_shell():
    assert echo_message("path a'b") == "printf '%s\\n' 'path a'\"'\"'b'"


def test_sudo_run_shell_can_fallback_or_require_sudo():
    fallback = sudo_run_shell()
    strict = sudo_run_shell(fallback_without_sudo=False)
    probed = sudo_run_shell(probe_sudo=True)

    assert "command -v sudo" in fallback
    assert "else \"$@\"" in fallback
    assert "sudo -S -p '' \"$@\"" in fallback
    assert "command -v sudo" not in strict
    assert "else \"$@\"" not in strict
    assert "sudo -S -p '' \"$@\"" in strict
    assert "sudo_ok=0" in probed
    assert "sudo -S -p '' true" in probed
    assert "if [ \"$sudo_ok\" = 1 ]" in probed
    assert "else \"$@\"" in probed


def test_yaml_string_escapes_backslashes_and_quotes():
    assert yaml_string('map "A" \\ path') == '"map \\"A\\" \\\\ path"'


def test_sshpass_file_is_reused_and_private(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path))

    first = Path(sshpass_file("secret"))
    second = Path(sshpass_file("secret"))

    assert first == second
    assert first.read_text(encoding="utf-8") == "secret\n"
    assert first.stat().st_mode & 0o777 == 0o600


def test_sshpass_file_uses_bounded_collision_retries(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path))
    monkeypatch.setattr(sshpass_module.secrets, "token_hex", lambda size: "collision")
    root = tmp_path / f"dog_remote_tool_sshpass_{os.getuid()}"
    root.mkdir()
    (root / "sshpass_collision.pass").write_text("existing\n", encoding="utf-8")

    with pytest.raises(RuntimeError, match="sshpass 临时密码文件"):
        sshpass_file("collision-password")


def test_sshpass_argv_uses_password_file(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path))

    argv = sshpass_argv("pw")

    assert argv[:2] == ["sshpass", "-f"]
    assert Path(argv[2]).read_text(encoding="utf-8") == "pw\n"


def test_ssh_options_argv_matches_string_options():
    assert ssh_options_argv() == [
        "-o", "StrictHostKeyChecking=no",
        "-o", "UserKnownHostsFile=/dev/null",
        "-o", "GlobalKnownHostsFile=/dev/null",
        "-o", "LogLevel=ERROR",
        "-o", "ConnectTimeout=6",
    ]
    assert ssh_options() == "-o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o GlobalKnownHostsFile=/dev/null -o LogLevel=ERROR -o ConnectTimeout=6"


def test_ssh_options_argv_can_override_timeout_and_alive_options():
    assert ssh_options_argv(30, server_alive_interval=15, server_alive_count_max=8) == [
        "-o", "StrictHostKeyChecking=no",
        "-o", "UserKnownHostsFile=/dev/null",
        "-o", "GlobalKnownHostsFile=/dev/null",
        "-o", "LogLevel=ERROR",
        "-o", "ConnectTimeout=30",
        "-o", "ServerAliveInterval=15",
        "-o", "ServerAliveCountMax=8",
    ]
    assert not any(item.startswith("ConnectTimeout=") for item in ssh_options_argv(include_connect_timeout=False))


def test_ssh_prefix_command_reuses_standard_options_and_quoting(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path))
    profile = ProductProfile(
        key="test",
        label="Test",
        platform="NX",
        host="10.0.0.2",
        user="ro'bot",
        password="pw",
        home="/home/robot",
    )

    command = ssh_prefix_command(profile, connect_timeout=9)

    assert command.startswith("sshpass -f ")
    assert " ssh -o StrictHostKeyChecking=no " in command
    assert " ssh -tt " not in command
    assert "-o ConnectTimeout=9" in command
    assert quote(profile.target) in command

    tty_command = ssh_prefix_command(profile, connect_timeout=9, tty=True)

    assert " ssh -tt -o StrictHostKeyChecking=no " in tty_command
    assert "-o ConnectTimeout=9" in tty_command
    assert quote(profile.target) in tty_command


def test_ssh_commands_enable_connection_reuse_without_plain_password(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path))
    profile = ProductProfile(
        key="test",
        label="Test",
        platform="NX",
        host="10.0.0.2",
        user="robot",
        password="secret-password",
        home="/home/robot",
    )

    command = ssh_prefix_command(profile)

    assert "-o ControlMaster=auto" in command
    assert "-o ControlPersist=10m" in command
    assert "-o ControlPath=" in command
    control_path = command.split("-o ControlPath=", 1)[1].split()[0]
    assert control_path.startswith(str(tmp_path))
    assert Path(control_path).parent.stat().st_mode & 0o777 == 0o700
    assert "secret-password" not in command


def test_ssh_control_path_uses_private_tmp_dir_without_password_when_runtime_dir_missing(tmp_path, monkeypatch):
    monkeypatch.delenv("XDG_RUNTIME_DIR", raising=False)
    monkeypatch.setenv("TMPDIR", str(tmp_path))
    profile = ProductProfile(
        key="test",
        label="Test",
        platform="NX",
        host="10.0.0.2",
        user="robot",
        password="guessable",
        home="/home/robot",
    )

    command = ssh_prefix_command(profile)

    control_path = command.split("-o ControlPath=", 1)[1].split()[0]
    assert control_path.startswith(str(tmp_path / f"dog_remote_tool_ssh_control_{os.getuid()}"))
    assert Path(control_path).parent.stat().st_mode & 0o777 == 0o700
    assert "guessable" not in control_path


def test_ssh_connection_reuse_can_be_disabled(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path))
    monkeypatch.setenv("DOG_REMOTE_TOOL_SSH_CONTROL", "0")
    profile = get_product("xg2_3588")

    command = ssh_prefix_command(profile)

    assert "ControlMaster" not in command
    assert "ControlPersist" not in command
    assert "ControlPath" not in command


def test_profile_aware_ssh_options_argv_adds_connection_reuse_and_alive_options(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path))
    profile = get_product("xg2_3588")

    argv = ssh_options_argv_for_profile(profile, 30, server_alive_interval=15, server_alive_count_max=8)

    assert "-o" in argv
    assert "ControlMaster=auto" in argv
    assert "ControlPersist=10m" in argv
    assert any(item.startswith("ControlPath=") for item in argv)
    assert "ServerAliveInterval=15" in argv
    assert "ServerAliveCountMax=8" in argv
    assert "bot" not in " ".join(argv)


def test_profile_aware_ssh_options_argv_includes_jump_proxy(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path))
    profile = get_product("xg2_s100")

    argv = ssh_options_argv_for_profile(profile, 12)
    joined = " ".join(argv)

    assert "ProxyCommand=" in joined
    assert "192.168.234.1" in joined
    assert "ControlMaster=auto" not in argv
    assert "ControlPersist=10m" not in argv


def test_jump_proxy_connection_reuse_can_be_enabled(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path))
    monkeypatch.setenv("DOG_REMOTE_TOOL_SSH_CONTROL_JUMP", "1")
    profile = get_product("xg2_s100")

    argv = ssh_options_argv_for_profile(profile, 12)
    joined = " ".join(argv)

    assert "ProxyCommand=" in joined
    assert "ControlMaster=auto" in argv
    assert "ControlPersist=10m" in argv
    assert joined.count("ControlMaster=auto") >= 2


def test_jump_proxy_connection_reuse_can_be_disabled(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path))
    monkeypatch.setenv("DOG_REMOTE_TOOL_SSH_CONTROL", "0")
    profile = get_product("xg2_s100")

    command = ssh_prefix_command(profile)

    assert "ProxyCommand=" in command
    assert "ControlMaster" not in command
    assert "ControlPersist" not in command
    assert "ControlPath" not in command


def test_remote_env_uses_profile_ros_settings():
    profile = ProductProfile(
        key="test",
        label="Test",
        platform="NX",
        host="10.0.0.2",
        user="robot",
        password="pw",
        home="/home/robot",
        ros_domain_id="42",
        rmw="rmw_test",
    )

    env = remote_env(profile)

    assert "/opt/runtime/env.bash" in env
    assert "ROS_DOMAIN_ID=42" in env
    assert "RMW_IMPLEMENTATION=rmw_test" in env
    assert "ROS_LOCALHOST_ONLY=0" in env
    assert "ZENOH_CONFIG_OVERRIDE='transport/shared_memory/enabled=false'" in env


def test_remote_target_path_joins_profile_target_and_path():
    profile = get_product("xg2_s100")

    assert remote_target_path(profile, "/tmp/map.geojson") == "robot@192.168.168.100:/tmp/map.geojson"


def test_ssh_command_redacts_password_into_file(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path))
    profile = ProductProfile(
        key="test",
        label="Test",
        platform="NX",
        host="10.0.0.2",
        user="robot",
        password="pw",
        home="/home/robot",
    )

    command = ssh_command(profile, "echo ok")

    assert "sshpass -f" in command
    assert "robot@10.0.0.2" in command
    assert "echo ok" in command
    assert "sshpass -p" not in command


def test_scp_commands_use_password_file_and_jump_proxy_for_l2_s100(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path))
    profile = get_product("xg2_s100")

    pull = scp_pull_command(profile, "/ota/alg_data/map/map.geojson", "/tmp/map.geojson")
    push = scp_push_command(profile, "/tmp/map.geojson", "/home/robot/map.geojson.uploading")

    assert "ProxyCommand=" in pull
    assert "ControlMaster=auto" not in pull
    assert "ControlPersist=10m" not in pull
    assert "robot@192.168.234.1" in pull
    assert "sshpass -f" in pull
    assert "sshpass -p" not in pull
    assert "robot@192.168.168.100:/ota/alg_data/map/map.geojson" in pull
    assert "robot@192.168.168.100:/home/robot/map.geojson.uploading" in push


def test_rsync_push_command_keeps_local_source_and_remote_target_order(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path))
    profile = get_product("xg2_s100")

    command = rsync_push_command(profile, "/tmp/local.deb", "~/")

    assert " rsync -avP " in command
    assert "ProxyCommand=" in command
    assert "ControlMaster=auto" not in command
    assert "ControlPersist=10m" not in command
    assert "robot@192.168.234.1" in command
    assert command.index("/tmp/local.deb") < command.index("robot@192.168.168.100:~/")
    assert "sshpass -p" not in command

    quiet = rsync_push_command(profile, "/tmp/frp.zip", "~/", options="-a", connect_timeout=12)

    assert "-o ConnectTimeout=12" in quiet
    assert quiet.index("/tmp/frp.zip") < quiet.index("robot@192.168.168.100:~/")


def test_rsync_command_accepts_custom_options_and_timeout(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path))
    profile = get_product("xg2_s100")

    command = rsync_command(
        profile,
        "/tmp/a.txt",
        "robot@192.168.168.100:/tmp/a.txt",
        options="-a --info=progress2",
        connect_timeout=12,
    )

    assert "ProxyCommand=" in command
    assert "-o ConnectTimeout=12" in command
    assert "/tmp/a.txt" in command
    assert "sshpass -p" not in command


def test_rsync_pull_command_uses_connection_reuse(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path))
    profile = get_product("xg2_3588")

    command = rsync_pull_command(profile, "/tmp/a", "/tmp/b")

    assert "ControlMaster=auto" in command
    assert "ControlPersist=10m" in command
    assert "ControlPath=" in command


def test_rsync_prefix_command_can_be_reused_inside_shell_functions(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path))
    profile = get_product("xg2_s100")

    prefix = rsync_prefix_command(profile, options="-a", connect_timeout=20)

    assert prefix.startswith("sshpass -f ")
    assert " rsync -a -e " in prefix
    assert "-o ConnectTimeout=20" in prefix
    assert "ProxyCommand=" in prefix
    assert "sshpass -p" not in prefix
    assert "robot@192.168.168.100" not in prefix
