from dog_remote_tool.core.profiles import get_product
from dog_remote_tool.modules import localization


def test_localization_fetch_map_files_reuses_rsync_helpers_for_required_and_optional_pull(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path))
    profile = get_product("xg2_s100")

    command = localization.fetch_map_files_command(
        profile,
        "/opt/data/.robot/map/history_map/a/map.pgm",
        "/tmp/localization/map.pgm",
        "/tmp/localization/map.yaml",
    )

    assert "fetch_required()" in command
    assert command.count(" rsync -a ") == 3
    assert "map.txt" in command
    assert ">/dev/null 2>&1 || true" in command
    assert "192.168.168.0/24" not in command
    assert "ProxyCommand=" in command
