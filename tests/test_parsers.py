from dog_remote_tool.core.parsers import parse_key_value_fields, parse_key_values


def test_parse_key_values_strips_keys_values_and_keeps_value_equals():
    output = "\n".join(
        [
            "noise",
            " A = 1 ",
            "B=x=y",
            "",
        ]
    )

    assert parse_key_values(output) == {"A": "1", "B": "x=y"}


def test_parse_key_value_fields_reads_space_separated_assignments():
    text = "noise POSE=ok X=1.25 Y=-2.5 YAW=0.75 EXTRA=a=b"

    assert parse_key_value_fields(text) == {
        "POSE": "ok",
        "X": "1.25",
        "Y": "-2.5",
        "YAW": "0.75",
        "EXTRA": "a=b",
    }


def test_parse_key_value_fields_accepts_custom_separator():
    text = "SSID=Lab WiFi\tSIGNAL=-35\tnoise\tEXTRA=a=b"

    assert parse_key_value_fields(text, separator="\t") == {
        "SSID": "Lab WiFi",
        "SIGNAL": "-35",
        "EXTRA": "a=b",
    }
