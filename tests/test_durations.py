from dog_remote_tool.core.durations import format_seconds


def test_format_seconds_defaults_to_padded_hours():
    assert format_seconds(None) == "-"
    assert format_seconds(3661.9) == "01:01:01"


def test_format_seconds_can_hide_empty_hours_and_round():
    assert format_seconds(9.4, always_hours=False, rounded=True) == "00:09"
    assert format_seconds(3661, always_hours=False, rounded=True) == "1:01:01"
