from __future__ import annotations

from collections.abc import Callable

from dog_remote_tool.modules.bag.names import normalize_topic


VIEW_ALL = "__all__"
VIEW_SELECTED = "__selected__"
VIEW_UNCLASSIFIED = "__unclassified__"

THEME_PALETTE = (
    "#eff6ff",
    "#f0fdf4",
    "#fff7ed",
    "#f5f3ff",
    "#ecfeff",
    "#fdf2f8",
    "#fefce8",
    "#f1f5f9",
)
UNCLASSIFIED_COLOR = "#f8fafc"


def default_view_items() -> list[tuple[str, str]]:
    return [
        ("全量显示", VIEW_ALL),
        ("当前选中主题", VIEW_SELECTED),
        ("未归类", VIEW_UNCLASSIFIED),
    ]


def topic_theme_items(record_topics: dict, display_name: Callable[[str, dict], str]) -> list[tuple[str, str]]:
    return [(display_name(key, config), key) for key, config in record_topics.items()]


def theme_entries(record_topics: dict, display_name: Callable[[str, dict], str]) -> list[tuple[str, str, set[str]]]:
    entries: list[tuple[str, str, set[str]]] = []
    for key, config in record_topics.items():
        topics = {
            normalized
            for topic in config.get("topics") or []
            if isinstance(topic, str)
            for normalized in [normalize_topic(topic)]
            if normalized
        }
        if not topics:
            continue
        entries.append((key, display_name(key, config), topics))
    return entries


def theme_for_topic(topic: str, entries: list[tuple[str, str, set[str]]]) -> dict:
    normalized = normalize_topic(topic)
    matches = [(index, key, name) for index, (key, name, topics) in enumerate(entries) if normalized in topics]
    if not matches:
        return {"key": VIEW_UNCLASSIFIED, "label": "未归类", "all": "未归类", "order": len(entries) + 1}
    index, key, name = matches[0]
    return {
        "key": key,
        "label": name,
        "all": " / ".join(item[2] for item in matches),
        "order": index,
    }


def theme_index(entries: list[tuple[str, str, set[str]]]) -> dict[str, dict]:
    grouped: dict[str, list[tuple[int, str, str]]] = {}
    for index, (key, name, topics) in enumerate(entries):
        for topic in topics:
            grouped.setdefault(topic, []).append((index, key, name))
    lookup: dict[str, dict] = {}
    for topic, matches in grouped.items():
        index, key, name = matches[0]
        lookup[topic] = {
            "key": key,
            "label": name,
            "all": " / ".join(item[2] for item in matches),
            "order": index,
        }
    return lookup


def theme_color_hex(theme_key: str, order: int) -> str:
    if theme_key == VIEW_UNCLASSIFIED:
        return UNCLASSIFIED_COLOR
    return THEME_PALETTE[order % len(THEME_PALETTE)]


def view_rows(
    rows: list[dict],
    entries: list[tuple[str, str, set[str]]],
    view_key: str,
    selected_keys: set[str],
) -> list[dict]:
    enriched = []
    themes_by_topic = theme_index(entries)
    unclassified = {"key": VIEW_UNCLASSIFIED, "label": "未归类", "all": "未归类", "order": len(entries) + 1}
    for row in rows:
        topic = str(row.get("topic") or "")
        theme = themes_by_topic.get(normalize_topic(topic), unclassified)
        if view_key == VIEW_SELECTED and theme["key"] not in selected_keys:
            continue
        if view_key == VIEW_UNCLASSIFIED and theme["key"] != VIEW_UNCLASSIFIED:
            continue
        if view_key not in (VIEW_ALL, VIEW_SELECTED, VIEW_UNCLASSIFIED) and theme["key"] != view_key:
            continue
        item = dict(row)
        item["_theme"] = theme
        enriched.append(item)
    enriched.sort(key=lambda item: (item["_theme"]["order"], item["_theme"]["label"], str(item.get("topic") or "")))
    return enriched


def table_row_values(row: dict) -> tuple[dict, list[str], float | None]:
    hz_value = row.get("hz")
    theme = row.get("_theme") or {"key": VIEW_UNCLASSIFIED, "label": "未归类", "all": "未归类", "order": 0}
    return (
        theme,
        [
            str(theme["label"]),
            str(row.get("topic") or ""),
            str(row.get("type") or ""),
            "--" if hz_value is None else f"{float(hz_value):.2f}",
            str(row.get("status") or ""),
        ],
        None if hz_value is None else round(float(hz_value), 2),
    )
