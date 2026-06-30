from dog_remote_tool.core.markers import extract_marked_payload
from dog_remote_tool.core.profiles import ProductProfile, get_product
from dog_remote_tool.core.shell import quote
from dog_remote_tool.modules import file_manager
from dog_remote_tool.modules.file_manager import actions as file_manager_actions
from dog_remote_tool.modules.file_manager import accounts as file_manager_accounts
from dog_remote_tool.modules.file_manager import browser as file_manager_browser
from dog_remote_tool.modules.file_manager import clipboard as file_manager_clipboard
from dog_remote_tool.modules.file_manager import privilege as file_manager_privilege
from dog_remote_tool.modules.file_manager import transfer as file_manager_transfer
from helpers import remote_command as _remote_command


def test_parse_list_output_extracts_payload_with_surrounding_logs():
    text = """
noise before
DOG_REMOTE_FILE_BEGIN
{"current": "/home/robot", "items": [{"name": "logs", "path": "/home/robot/logs", "kind": "dir", "size": -1, "mtime": 1.5, "mode": "drwxr-xr-x", "owner": "robot", "group": "robot"}]}
DOG_REMOTE_FILE_END
noise after
"""

    current, items, error = file_manager.parse_list_output(text)

    assert current == "/home/robot"
    assert error == ""
    assert items == [
        file_manager.RemoteFileItem(
            name="logs",
            path="/home/robot/logs",
            kind="dir",
            size=-1,
            mtime=1.5,
            mode="drwxr-xr-x",
            owner="robot",
            group="robot",
        )
    ]


def test_parse_list_output_reports_missing_payload():
    current, items, error = file_manager.parse_list_output("plain error")

    assert current == ""
    assert items == []
    assert error == "未读取到远端目录数据"


def test_parse_total_size_output_extracts_marker_value():
    size, error = file_manager.parse_total_size_output("x\nDOG_REMOTE_SIZE_BEGIN\n2048\nDOG_REMOTE_SIZE_END\n")

    assert size == 2048
    assert error == ""


def test_parse_total_size_output_reports_tail_when_marker_value_is_invalid():
    size, error = file_manager.parse_total_size_output("DOG_REMOTE_SIZE_BEGIN\nbad\nDOG_REMOTE_SIZE_END\nfallback")

    assert size is None
    assert error == "fallback"


def test_parse_total_size_output_reports_default_when_output_is_empty():
    size, error = file_manager.parse_total_size_output("")

    assert size is None
    assert error == "未读取到目录大小"


def test_format_size_keeps_file_and_unknown_directory_text():
    assert file_manager.format_size(1536) == "1.5 KB"
    assert file_manager.format_size(-1, "dir") == "未计算"


def test_parse_preview_output_extracts_json_payload():
    payload, error = file_manager.parse_preview_output(
        'DOG_REMOTE_PREVIEW_BEGIN\n{"path": "/tmp/a.txt", "text": "hello"}\nDOG_REMOTE_PREVIEW_END\n'
    )

    assert payload["path"] == "/tmp/a.txt"
    assert payload["text"] == "hello"
    assert error == ""


def test_file_manager_upload_download_use_jump_proxy_for_l2_s100(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path))
    profile = get_product("xg2_s100")

    upload = file_manager.upload_command(profile, "/tmp/a.txt", "/home/robot/log")
    download = file_manager.download_command(profile, "/home/robot/log/a.txt", "/tmp/out")

    assert "ProxyCommand=" in upload.command
    assert "ProxyCommand=" in download.command
    assert "robot@192.168.234.1" in upload.command
    assert "robot@192.168.234.1" in download.command
    assert upload.concurrency == "parallel"
    assert download.concurrency == "parallel"


def test_file_manager_privilege_helpers_reuse_strict_sudo_run():
    profile = get_product("xg2_s100")

    shell = file_manager_privilege.sudo_sh(profile, "echo ok")
    command = file_manager_privilege.sudo_exec(profile, "rm -f /tmp/a")
    spec = file_manager.mkdir_command(profile, "/home/robot", "logs")

    assert "sudo_run() {" in shell
    assert "sudo_run sh -c 'echo ok'" in shell
    assert "sudo_run rm -f /tmp/a" in command
    assert "command -v sudo" not in shell
    assert "command -v sudo" not in command
    assert "printf '%s\\n' \"$DOG_REMOTE_SUDO_PASS\" | sudo -S -p '' sh -c" not in spec.command
    assert "sudo_run sh -c" in spec.command


def test_file_manager_clipboard_export_and_copy_suffix_logic():
    profile = get_product("xg2_s100")

    assert file_manager.paste_command is file_manager_clipboard.paste_command

    spec = file_manager.paste_command(profile, ["/home/robot/a.txt"], "/home/robot/dst", move=False)

    assert spec.title == "复制到远端目录"
    assert "cp -a -- /home/robot/a.txt" in spec.command
    assert "_copy${ext}" in spec.command
    assert "_copy${n}${ext}" in spec.command


def test_file_manager_copy_allows_protected_source_but_cut_rejects_it():
    profile = get_product("xg2_s100")

    spec = file_manager.paste_command(profile, ["/etc/hosts"], "/home/robot/dst", move=False)

    assert "cp -a -- /etc/hosts" in spec.command

    try:
        file_manager.paste_command(profile, ["/etc/hosts"], "/home/robot/dst", move=True)
    except ValueError as exc:
        assert "禁止删除系统关键路径" in str(exc)
    else:
        raise AssertionError("cut from protected path should be rejected")


def test_file_manager_paste_quotes_paths_in_status_messages():
    profile = get_product("xg2_s100")
    source = "/home/robot/a'file.txt"
    target_dir = "/home/robot/d'st"

    spec = file_manager.paste_command(profile, [source], target_dir, move=False)
    remote_command = _remote_command(spec, profile.target)

    assert f"cp -a -- {quote(source)}" in remote_command
    assert quote(f"[ERROR] 源文件不存在：{source}") in remote_command
    assert f"printf '%s%s\\n' {quote(f'[INFO] 已复制: {source} -> ')} \"$dest\"" in remote_command
    assert "echo '[ERROR] 源文件不存在：" not in remote_command


def test_file_manager_cut_same_dir_quotes_status_message():
    profile = get_product("xg2_s100")
    source = "/home/robot/a'file.txt"

    spec = file_manager.paste_command(profile, [source], "/home/robot", move=True)
    remote_command = _remote_command(spec, profile.target)

    assert quote(f"[INFO] 剪切源和目标相同，无需操作：{source}") in remote_command
    assert "echo '[INFO] 剪切源和目标相同" not in remote_command


def test_file_manager_account_probe_export_and_scope():
    profile = get_product("xg2_s100")

    assert file_manager.account_probe_command is file_manager_accounts.account_probe_command

    spec = file_manager.account_probe_command(profile)

    assert spec.title == "探测可用账号"
    assert spec.display_command == "探测当前设备可用账号"
    assert profile.host not in spec.display_command
    assert "echo ONLINE" in spec.command
    assert "当前账号不可用时" in spec.command


def test_file_manager_account_probe_quotes_available_account_message(monkeypatch):
    profile = get_product("xg2_s100")
    candidate = ProductProfile(
        key="xg2_quote",
        label="Dog's account",
        platform=profile.platform,
        host=profile.host,
        user="ro'bot",
        password="pw",
        home="/home/robot",
    )
    monkeypatch.setitem(file_manager_accounts.PRODUCTS, candidate.key, candidate)

    spec = file_manager.account_probe_command(profile)
    target = f"{candidate.user}@{candidate.host}"

    assert quote(f"[INFO] 可用账号: {candidate.label} {target}") in spec.command
    assert "echo '[INFO] 可用账号:" not in spec.command
