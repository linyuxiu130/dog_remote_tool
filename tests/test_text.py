from dog_remote_tool.core.text import compact_lines, last_nonempty_line, strip_ansi, strip_control_chars


def test_strip_ansi_removes_terminal_color_sequences():
    assert strip_ansi("\x1b[31mERROR\x1b[0m ok") == "ERROR ok"


def test_strip_ansi_removes_osc_and_visible_escape_sequences():
    assert strip_ansi("\x1b]0;title\x07title ␛[31mred") == "title red"


def test_strip_control_chars_keeps_line_breaks_and_tabs():
    assert strip_control_chars("a\x00b\tc\nd") == "ab\tc\nd"


def test_compact_lines_joins_lines_and_truncates():
    assert compact_lines(" first\nsecond ", limit=20) == "first；second"
    assert compact_lines("abcdef", limit=3) == "abc..."


def test_last_nonempty_line_strips_blank_lines():
    assert last_nonempty_line(" first \n\n second  \n") == "second"
    assert last_nonempty_line("\n \n") == ""
