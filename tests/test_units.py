from dog_remote_tool.core.units import format_byte_size


def test_format_byte_size_scales_binary_units():
    assert format_byte_size(512) == "512 B"
    assert format_byte_size(1536) == "1.5 KB"
    assert format_byte_size(1024 * 1024) == "1.0 MB"


def test_format_byte_size_accepts_custom_max_unit():
    assert format_byte_size(1024**4, ("B", "KB", "MB", "GB", "TB")) == "1.0 TB"


def test_format_byte_size_accepts_custom_precision():
    assert format_byte_size(1536, ("B", "KiB", "MiB"), precision=2) == "1.50 KiB"
