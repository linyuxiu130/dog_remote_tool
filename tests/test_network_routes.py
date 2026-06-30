from dog_remote_tool.core.network_routes import route_repair_command, route_repair_rule, with_route_repair
from dog_remote_tool.core.profiles import ProductProfile, get_product
from dog_remote_tool.core.shell import rsync_pull_command, ssh_command


def test_xg2_s100_repairs_route_via_dog_gateway():
    command = route_repair_command(get_product("xg2_s100"))

    assert "192.168.168.0/24" in command
    assert "192.168.234.1" in command
    assert "sudo -n ip route replace" in command
    assert "pkexec ip route replace" in command
    assert "need sudo permission" in command
    assert "DOG_ROUTE_SOURCE_PREFIX" not in command
    assert "unresolved $DOG_ROUTE_HOST route" in command


def test_zg_s100_repairs_route_via_profile_jump_host():
    command = route_repair_command(get_product("zg_surround_s100"))

    assert "192.168.168.0/24" in command
    assert "DOG_ROUTE_GATEWAY=192.168.234.1" in command
    assert "192.168.168." in command


def test_route_repair_accepts_target_only_profile():
    profile = type("Profile", (), {"target": "robot@192.168.168.100", "jump_host": "192.168.234.1"})()

    rule = route_repair_rule(profile)

    assert rule is not None
    assert rule.target_host == "192.168.168.100"
    assert rule.subnet == "192.168.168.0/24"


def test_privileged_route_repair_paths_use_same_gateway_args():
    command = route_repair_command(get_product("xg2_s100"))
    route_args = '"$DOG_ROUTE_SUBNET" via "$DOG_ROUTE_GATEWAY" dev "$DOG_ROUTE_DEV" src "$DOG_ROUTE_SRC" metric 50'

    assert f"sudo -n ip route replace {route_args}" in command
    assert f"pkexec ip route replace {route_args}" in command


def test_route_repair_uses_local_cooldown_before_privileged_attempts():
    command = route_repair_command(get_product("xg2_s100"))

    assert "DOG_ROUTE_COOLDOWN_SECONDS=60" in command
    assert "dog_remote_tool_routes" in command
    assert command.index("DOG_ROUTE_COOLDOWN_SECONDS=60") < command.index("sudo -n ip route replace")
    assert "repair cooldown active" in command


def test_xg1_nx_can_repair_direct_234_subnet():
    rule = route_repair_rule(get_product("xg1_nx"))
    command = route_repair_command(get_product("xg1_nx"))

    assert rule is not None
    assert rule.subnet == "192.168.234.0/24"
    assert "ip route replace \"$DOG_ROUTE_SUBNET\" dev" in command


def test_unknown_profile_has_no_route_repair():
    profile = ProductProfile(
        key="custom",
        label="Custom",
        platform="NX",
        host="10.0.0.2",
        user="robot",
        password="pw",
        home="/home/robot",
    )

    assert route_repair_rule(profile) is None
    assert route_repair_command(profile) == ""
    assert with_route_repair(profile, "echo ok") == "echo ok"


def test_with_route_repair_skips_jump_host_targets():
    command = with_route_repair(get_product("xg2_s100"), "echo ok")

    assert command == "echo ok"


def test_ssh_command_prefixes_route_repair_for_s100(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path))

    command = ssh_command(get_product("xg2_s100"), "echo ok")

    assert "192.168.168.0/24" not in command
    assert "ProxyCommand=" in command
    assert "robot@192.168.234.1" in command
    assert "robot@192.168.168.100" in command


def test_rsync_command_uses_jump_proxy_for_zg_s100(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path))

    command = rsync_pull_command(get_product("zg_surround_s100"), "/tmp/a", "/tmp/b")

    assert "192.168.168.0/24" not in command
    assert "ProxyCommand=" in command
    assert "robot@192.168.234.1" in command
    assert "robot@192.168.168.100:/tmp/a" in command
