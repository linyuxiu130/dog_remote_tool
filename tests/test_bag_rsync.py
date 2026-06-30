from dog_remote_tool.core.profiles import get_product
from dog_remote_tool.modules import bag
from dog_remote_tool.modules.bag import rsync as bag_rsync


def test_local_log_source_dir_sanitizes_remote_path():
    assert bag_rsync.local_log_source_dir("/tmp/log/alg data/") == "tmp_log_alg_data"
    assert bag.BagBackend.local_log_source_dir("///") == "remote_log"


def test_build_rsync_command_includes_excludes_and_ssh_options():
    profile = get_product("xg2_s100")
    command = bag_rsync.build_rsync_command(
        profile,
        ["-o", "ConnectTimeout=30"],
        "/remote/",
        "/local/",
        rsync_args=["-avz"],
        excludes=["*.mcap", "*.db3"],
    )

    assert command[:2] == ["sshpass", "-f"]
    assert "rsync" in command
    assert "--exclude" in command
    assert "*.mcap" in command
    assert "-e" in command
    assert "ssh -o ConnectTimeout=30" in command
    assert f"{profile.target}:/remote/" in command
    assert command[-1] == "/local/"


def test_split_rsync_output_preserves_partial_line():
    remaining, lines = bag_rsync.split_rsync_output("abc", "def\n50% 1.0MB/s\rpartial")

    assert lines == ["abcdef", "50% 1.0MB/s"]
    assert remaining == "partial"


def test_parse_rsync_progress_and_warning_detection():
    assert bag_rsync.parse_rsync_progress("12345 42% 1.5MB/s") == (42, "1.5 MB/s")
    assert bag_rsync.parse_rsync_progress("no percent") is None
    assert bag_rsync.is_warning_line("Permission denied")
    assert bag_rsync.is_warning_line("connection refused")
    assert not bag_rsync.is_warning_line("regular output")


def test_remember_output_tail_keeps_recent_lines():
    tail: list[str] = []
    for index in range(12):
        bag_rsync.remember_output_tail(tail, f"line-{index}", limit=4)

    assert tail == ["line-8", "line-9", "line-10", "line-11"]
