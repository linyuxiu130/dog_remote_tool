from __future__ import annotations

from dog_remote_tool.modules import bag


def topic_display_name(record_topics: dict, key: str, config: dict | None = None) -> str:
    config = config or record_topics.get(key, {})
    if bag.is_custom_preset_key(key):
        return bag.custom_preset_name_from_key(key) or str(config.get("name") or key)
    return str(config.get("name") or key)


def topic_tooltip(record_topics: dict, key: str, config: dict | None = None) -> str:
    config = config or record_topics.get(key, {})
    name = topic_display_name(record_topics, key, config)
    topics = len(config.get("topics", []))
    if bag.is_custom_preset_key(key):
        return f"主题：{name}\n类型：自定义主题\nTopic：{topics} 个"
    return f"主题：{name}\n内部标识：{key}\nTopic：{topics} 个"


def topic_name_exists(record_topics: dict, name: str, current_key: str = "") -> bool:
    normalized = name.strip()
    for key, config in record_topics.items():
        if key == current_key:
            continue
        if topic_display_name(record_topics, key, config).strip() == normalized:
            return True
    return False


def editable_topic_list(config: dict) -> list[str]:
    topics = list(dict.fromkeys(config.get("topics", [])))
    for topic in config.get("zstd_topics", config.get("lz4_topics", [])):
        if topic not in topics:
            topics.append(topic)
    return topics


def normalize_topic_values(values: list[str]) -> list[str]:
    topics: list[str] = []
    for value in values:
        topic = bag.normalize_topic(value)
        if topic and topic not in topics:
            topics.append(topic)
    return topics


def set_config_topics(config: dict, topics: list[str]) -> None:
    config["topics"] = topics
    config.pop("zstd_topics", None)
    config.pop("lz4_topics", None)
