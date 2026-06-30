from dog_remote_tool.core.markers import extract_marked_payload


def test_extract_marked_payload_reads_last_started_block():
    text = "\n".join(
        [
            "noise",
            "BEGIN",
            "old",
            "BEGIN",
            "new",
            "END",
            "tail",
        ]
    )

    assert extract_marked_payload(text, "BEGIN", "END") == "new"


def test_extract_marked_payload_returns_empty_when_markers_missing():
    assert extract_marked_payload("plain output", "BEGIN", "END") == ""
