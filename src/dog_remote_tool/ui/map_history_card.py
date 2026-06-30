from __future__ import annotations


def map_history_card_stylesheet(
    selected: bool,
    *,
    title_font_size: str = "11pt",
    selected_border: str = "#2b78b8",
    scoped_frame: bool = False,
    thumbnail_padding: int = 3,
    dynamic_thumbnail_bg: bool = False,
    title_line_height: str = "",
) -> str:
    border = selected_border if selected else "#d8e2ef"
    bg = "#eef7ff" if selected else "#ffffff"
    text = "#123b63" if selected else "#24384f"
    frame_selector = "QFrame#MapHistoryCard" if scoped_frame else "QFrame"
    thumb_bg = "#ffffff" if not dynamic_thumbnail_bg or selected else "#f8fbff"
    line_height = f"line-height:{title_line_height};" if title_line_height else ""
    return (
        f"{frame_selector}{{background:{bg};border:2px solid {border};border-radius:8px;}}"
        f"QLabel#MapHistoryThumbnail{{background:{thumb_bg};border:1px solid #dce7f3;border-radius:6px;color:#607085;padding:{thumbnail_padding}px;}}"
        f"QLabel#MapHistoryTitle{{color:{text};font-size:{title_font_size};font-weight:700;{line_height}}}"
    )
