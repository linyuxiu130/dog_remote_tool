from __future__ import annotations

import os
import re
from heapq import nsmallest
from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path

import yaml

from dog_remote_tool.core.paths import resource_dir
from dog_remote_tool.modules.bag.names import normalize_topic
from dog_remote_tool.modules.bag import topic_storage as _topic_storage


CUSTOM_PRESET_PREFIX = "custom_preset::"

TOPIC_CONFIG_MAP = {
    "xg": "record_topics_xg.yaml",
    "zg": "record_topics_zg.yaml",
    "nx": "record_topics_nx.yaml",
    "nxl2": "record_topics_nxl2.yaml",
    "net": "record_topics_xg.yaml",
    "zgnx": "record_topics_zg.yaml",
}

DEFAULT_TOPICS = {
    "navigation": {"name": "导航", "topics": ["/cmd_vel", "/odom", "/scan", "/monitor"]},
    "arc": {"name": "回充", "topics": ["/arc/state", "/cmd_vel", "/monitor"]},
    "slam": {"name": "建图&感知", "topics": ["/scan", "/camera/image", "/monitor"]},
    "localization": {"name": "定位", "topics": ["/odom", "/scan", "/monitor"]},
}


@dataclass
class TopicPlan:
    normal_topics: list[str]
    zstd_topics: list[str]
    all_topics: list[str]


def resources_dir(app_root: Path | None = None) -> Path:
    if app_root:
        return app_root.joinpath("resources", "record_bag")
    return resource_dir("record_bag")


def extra_topic_dirs() -> list[Path]:
    raw = os.environ.get("DOG_REMOTE_TOOL_RECORD_BAG_CONFIG_DIR", "")
    return [Path(item).expanduser() for item in raw.split(os.pathsep) if item.strip()]


def load_record_topics(product: str, app_root: Path | None = None) -> dict:
    filename = TOPIC_CONFIG_MAP.get(product, "record_topics_xg.yaml")
    candidates = [
        resources_dir(app_root) / filename,
    ]
    candidates.extend(path / filename for path in extra_topic_dirs())
    for path in candidates:
        if not path.exists():
            continue
        with path.open("r", encoding="utf-8") as fh:
            data = yaml.safe_load(fh) or {}
        return data if isinstance(data, dict) else DEFAULT_TOPICS.copy()
    return DEFAULT_TOPICS.copy()


def custom_preset_key(name: str) -> str:
    return f"{CUSTOM_PRESET_PREFIX}{name}"


def custom_preset_name_from_key(key: str) -> str:
    return key[len(CUSTOM_PRESET_PREFIX):] if key.startswith(CUSTOM_PRESET_PREFIX) else ""


def is_custom_preset_key(key: str) -> bool:
    return key.startswith(CUSTOM_PRESET_PREFIX)


config_dir = _topic_storage.config_dir
load_custom_presets = _topic_storage.load_custom_presets
save_custom_presets = _topic_storage.save_custom_presets
load_topic_overrides = _topic_storage.load_topic_overrides
save_topic_overrides = _topic_storage.save_topic_overrides


def apply_topic_overrides(topics: dict, product: str, overrides: dict) -> dict:
    product_overrides = overrides.get(product, {})
    for topic_key, override in product_overrides.items():
        config = topics.get(topic_key)
        if not isinstance(config, dict):
            continue
        name = override.get("name")
        if isinstance(name, str) and name.strip():
            config["name"] = name.strip()
        if isinstance(override.get("topics"), list):
            merged = []
            for topic in override.get("topics", []):
                normalized = normalize_topic(topic) if isinstance(topic, str) else ""
                if normalized and normalized not in merged:
                    merged.append(normalized)
            config["topics"] = merged
            config.pop("zstd_topics", None)
            config.pop("lz4_topics", None)
            continue
        removed = set(override.get("removed", []))
        merged = [topic for topic in config.get("topics", []) if topic not in removed]
        for topic in override.get("added", []):
            normalized = normalize_topic(topic)
            if normalized and normalized not in merged:
                merged.append(normalized)
        config["topics"] = merged
    return topics


def apply_custom_presets(topics: dict, presets: dict[str, list[str]]) -> dict:
    base = [(key, value) for key, value in topics.items() if not is_custom_preset_key(key)]
    rebuilt = {}
    for key, value in base:
        if key == "custom":
            continue
        rebuilt[key] = value
    for name in sorted(presets):
        rebuilt[custom_preset_key(name)] = {
            "name": f"自定义-{name}",
            "topics": presets[name][:],
            "custom_preset_name": name,
        }
    return rebuilt


def selected_topic_plan(record_topics: dict, selected_keys: list[str]) -> TopicPlan:
    all_topics: list[str] = []
    for key in selected_keys:
        config = record_topics.get(key, {})
        all_topics.extend(config.get("topics", []))
        all_topics.extend(config.get("zstd_topics", config.get("lz4_topics", [])))

    normalized_topics: list[str] = []
    seen: set[str] = set()
    for topic in all_topics:
        if not isinstance(topic, str):
            continue
        normalized = normalize_topic(topic)
        if normalized and normalized not in seen:
            seen.add(normalized)
            normalized_topics.append(normalized)
    return TopicPlan(normal_topics=normalized_topics, zstd_topics=[], all_topics=normalized_topics)


def _topic_similarity_text(topic: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", topic.lower())


def suggest_similar_topics(topic: str, remote_topics: list[str], limit: int = 5) -> list[str]:
    query = topic.strip()
    if not query or not remote_topics or limit <= 0:
        return []
    query_norm = _topic_similarity_text(query)
    query_tail = query.rstrip("/").split("/")[-1].lower()
    scored = []
    for candidate in remote_topics:
        candidate = candidate.strip()
        if not candidate or candidate == query:
            continue
        candidate_norm = _topic_similarity_text(candidate)
        candidate_tail = candidate.rstrip("/").split("/")[-1].lower()
        if not candidate_norm:
            continue
        score = SequenceMatcher(None, query_norm, candidate_norm).ratio()
        if query_tail and query_tail == candidate_tail:
            score += 0.25
        elif query_tail and (query_tail in candidate_tail or candidate_tail in query_tail):
            score += 0.12
        if query_norm and (query_norm in candidate_norm or candidate_norm in query_norm):
            score += 0.18
        if score >= 0.42:
            scored.append((-score, candidate))
    return [candidate for _score, candidate in nsmallest(limit, scored)]


def add_topic_suggestions(failed: list[str], remote_rows: list[dict], limit: int = 4) -> list[str]:
    remote_topics = sorted(
        {
            str(row.get("topic", "")).strip()
            for row in remote_rows
            if isinstance(row, dict) and str(row.get("topic", "")).strip()
        }
    )
    if not failed or not remote_topics:
        return failed
    enriched = []
    for item in failed:
        label, separator, reason = item.partition(":")
        topics = [part.strip() for part in label.split(" / ") if part.strip().startswith("/")]
        if not topics and label.strip().startswith("/"):
            topics = [label.strip()]
        suggestions = []
        for topic in topics:
            for suggestion in suggest_similar_topics(topic, remote_topics, limit=limit):
                if suggestion not in suggestions:
                    suggestions.append(suggestion)
        if suggestions:
            base = f"{label}{separator}{reason}" if separator else item
            enriched.append(f"{base}\n  可能是: {', '.join(suggestions[:limit])}")
        else:
            enriched.append(item)
    return enriched
