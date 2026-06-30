from dog_remote_tool.ui import map_helpers
from dog_remote_tool.ui.pages.navigation import page as navigation_page
from dog_remote_tool.ui.status_styles import style_for_state


def test_style_for_state_returns_match_and_default():
    styles = {
        "ready": ("#ffffff", "#111111", "#222222"),
        "unknown": ("#eeeeee", "#333333", "#444444"),
    }

    assert style_for_state(styles, "ready") == ("#ffffff", "#111111", "#222222")
    assert style_for_state(styles, "missing") == ("#eeeeee", "#333333", "#444444")


def test_existing_status_style_wrappers_keep_fallbacks():
    assert map_helpers.mapping_operation_style("missing") == map_helpers.MAPPING_OPERATION_STYLES["idle"]
    assert map_helpers.mapping_status_style("missing") == map_helpers.MAPPING_STATUS_STYLES["unknown"]
    assert navigation_page._status_style("missing") == navigation_page.STATUS_STYLES["unknown"]
