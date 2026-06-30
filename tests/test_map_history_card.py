from dog_remote_tool.ui.map_history_card import map_history_card_stylesheet


def test_map_history_card_stylesheet_defaults_match_unscoped_cards():
    style = map_history_card_stylesheet(True)

    assert "QFrame{background:#eef7ff;border:2px solid #2b78b8;border-radius:8px;}" in style
    assert "QLabel#MapHistoryThumbnail{background:#ffffff;border:1px solid #dce7f3;border-radius:6px;color:#607085;padding:3px;}" in style
    assert "QLabel#MapHistoryTitle{color:#123b63;font-size:11pt;font-weight:700;}" in style


def test_map_history_card_stylesheet_keeps_scoped_dynamic_thumbnail_variant():
    selected = map_history_card_stylesheet(
        True,
        title_font_size="9pt",
        scoped_frame=True,
        thumbnail_padding=4,
        dynamic_thumbnail_bg=True,
        title_line_height="110%",
    )
    unselected = map_history_card_stylesheet(
        False,
        title_font_size="9pt",
        scoped_frame=True,
        thumbnail_padding=4,
        dynamic_thumbnail_bg=True,
        title_line_height="110%",
    )

    assert "QFrame#MapHistoryCard{background:#eef7ff;border:2px solid #2b78b8;border-radius:8px;}" in selected
    assert "QLabel#MapHistoryThumbnail{background:#ffffff;border:1px solid #dce7f3;border-radius:6px;color:#607085;padding:4px;}" in selected
    assert "QLabel#MapHistoryTitle{color:#123b63;font-size:9pt;font-weight:700;line-height:110%;}" in selected
    assert "QLabel#MapHistoryThumbnail{background:#f8fbff;border:1px solid #dce7f3;border-radius:6px;color:#607085;padding:4px;}" in unselected


def test_map_history_card_stylesheet_allows_navigation_selected_border():
    style = map_history_card_stylesheet(True, selected_border="#2f6fa8")

    assert "border:2px solid #2f6fa8" in style
