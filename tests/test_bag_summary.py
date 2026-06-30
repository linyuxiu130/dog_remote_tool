from datetime import datetime

from dog_remote_tool.core.profiles import get_product
from dog_remote_tool.modules import bag
from dog_remote_tool.modules.bag import summary as bag_summary


def _write_bag_metadata(root):
    bag_dir = root / "rosbag2_l2_20260525_093001"
    bag_dir.mkdir()
    (bag_dir / "data_0.mcap").write_bytes(b"abcd")
    (bag_dir / "metadata.yaml").write_text(
        """
rosbag2_bagfile_information:
  duration:
    nanoseconds: 2500000000
  starting_time:
    nanoseconds_since_epoch: 1767225600000000000
  relative_file_paths:
    - data_0.mcap
  topics_with_message_count:
    - topic_metadata:
        name: /cmd_vel
      message_count: 3
    - topic_metadata:
        name: /odom
      message_count: 2
""",
        encoding="utf-8",
    )


def test_record_summary_lines_use_metadata_when_topics_are_not_provided(tmp_path):
    _write_bag_metadata(tmp_path)
    profile = get_product("xg2_s100")

    lines = bag_summary.record_summary_lines(
        "nxl2",
        profile,
        str(tmp_path),
        "L2_20260525_093001",
        [],
        True,
        {},
        datetime(2026, 5, 25, 9, 30, 1),
    )

    text = "\n".join(lines)
    assert "# 数据说明" in text
    assert "L2_20260525_093001" in text
    assert "| L2_20260525_093001 | L2 | `/cmd_vel`<br>`/odom` |" in text
    assert "00:00:02" in text
    assert "B |" in text


def test_bag_backend_write_record_summary_keeps_compatibility_signature(tmp_path):
    profile = get_product("xg2_s100")
    backend = bag.BagBackend(profile, "nxl2")

    summary_path = backend.write_record_summary(
        str(tmp_path),
        "L2_manual",
        ["/remote/rosbag2_l2_20260525_093001"],
        ["/cmd_vel", "/cmd_vel", "/odom"],
        False,
        False,
        True,
        False,
        False,
        [],
        [],
        {},
        {"started_at": "2026-05-25 09:30:01", "duration_seconds": 3.2},
        datetime(2026, 5, 25, 9, 31, 1),
    )

    text = (tmp_path / "record_summary.md").read_text(encoding="utf-8")
    assert summary_path == str(tmp_path / "record_summary.md")
    assert "| L2_manual | L2 | `/cmd_vel`<br>`/odom` | 2026-05-25 09:30:01 | 00:00:03 |" in text
