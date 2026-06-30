from dog_remote_tool.ui.pages.bag import remote_topics as bag_remote_topics


def _display_name(key: str, config: dict) -> str:
    return str(config.get("name") or key)


def test_theme_entries_normalize_config_topics():
    entries = bag_remote_topics.theme_entries(
        {
            "nav": {"name": "导航", "topics": ["cmd_vel", "/odom"]},
            "empty": {"name": "空", "topics": []},
        },
        _display_name,
    )

    assert entries == [("nav", "导航", {"/cmd_vel", "/odom"})]
    assert bag_remote_topics.theme_for_topic("/cmd_vel", entries)["label"] == "导航"
    assert bag_remote_topics.theme_index(entries)["/cmd_vel"]["label"] == "导航"


def test_view_rows_filter_and_sort_by_theme():
    entries = [
        ("nav", "导航", {"/cmd_vel", "/odom"}),
        ("loc", "定位", {"/scan"}),
    ]
    rows = [
        {"topic": "/scan", "hz": 10},
        {"topic": "/unknown", "hz": None},
        {"topic": "/cmd_vel", "hz": 20},
    ]

    all_rows = bag_remote_topics.view_rows(rows, entries, bag_remote_topics.VIEW_ALL, set())
    assert [row["topic"] for row in all_rows] == ["/cmd_vel", "/scan", "/unknown"]
    assert [row["_theme"]["label"] for row in all_rows] == ["导航", "定位", "未归类"]

    selected_rows = bag_remote_topics.view_rows(rows, entries, bag_remote_topics.VIEW_SELECTED, {"loc"})
    assert [row["topic"] for row in selected_rows] == ["/scan"]

    unclassified_rows = bag_remote_topics.view_rows(rows, entries, bag_remote_topics.VIEW_UNCLASSIFIED, set())
    assert [row["topic"] for row in unclassified_rows] == ["/unknown"]

    nav_rows = bag_remote_topics.view_rows(rows, entries, "nav", set())
    assert [row["topic"] for row in nav_rows] == ["/cmd_vel"]


def test_theme_color_hex_is_stable():
    assert bag_remote_topics.theme_color_hex(bag_remote_topics.VIEW_UNCLASSIFIED, 0) == "#f8fafc"
    assert bag_remote_topics.theme_color_hex("nav", 0) == "#eff6ff"
    assert bag_remote_topics.theme_color_hex("nav", len(bag_remote_topics.THEME_PALETTE)) == "#eff6ff"


def test_table_row_values_format_hz_and_default_theme():
    theme, values, numeric_hz = bag_remote_topics.table_row_values(
        {"topic": "/cmd_vel", "type": "geometry_msgs/msg/Twist", "hz": 12.345, "status": "正常"}
    )

    assert theme["label"] == "未归类"
    assert values == ["未归类", "/cmd_vel", "geometry_msgs/msg/Twist", "12.35", "正常"]
    assert numeric_hz == 12.35
