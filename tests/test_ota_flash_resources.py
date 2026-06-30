from dog_remote_tool.core.paths import resource_path
from dog_remote_tool.modules.ota import flash_resources as ota_flash_resources


def test_flash_resource_paths_follow_tool_root_env(monkeypatch, tmp_path):
    monkeypatch.setenv("DOG_REMOTE_TOOL_ROOT", str(tmp_path))

    platform_tools = tmp_path / "resources" / "platform-tools" / "linux-x86_64" / "bin"
    xburn_bin = tmp_path / "resources" / "xburn" / "linux-x86_64" / "bin"

    assert ota_flash_resources.tool_root() == tmp_path
    assert ota_flash_resources.bundled_fastboot_path() == platform_tools / "fastboot"
    assert ota_flash_resources.bundled_dfu_util_path() == platform_tools / "dfu-util"
    assert ota_flash_resources.bundled_xburn_path() == xburn_bin / "xburn"
    assert ota_flash_resources.bundled_fastboot_path() == resource_path("platform-tools", "linux-x86_64", "bin", "fastboot")
