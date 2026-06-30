from __future__ import annotations

from pathlib import Path

import yaml

from dog_remote_tool.modules.bag.names import normalize_topic


def config_dir() -> Path:
    return Path.home() / ".zs_record_bag"


def load_custom_presets() -> dict[str, list[str]]:
    path = config_dir() / "custom_topic_presets.yaml"
    if not path.exists():
        return {}
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        raw = data.get("presets", data)
        if not isinstance(raw, dict):
            return {}
        presets: dict[str, list[str]] = {}
        for name, topics in raw.items():
            if not isinstance(name, str) or not isinstance(topics, list):
                continue
            normalized = []
            for topic in topics:
                if isinstance(topic, str):
                    item = normalize_topic(topic)
                    if item and item not in normalized:
                        normalized.append(item)
            presets[name] = normalized
        return presets
    except Exception:
        return {}


def save_custom_presets(presets: dict[str, list[str]]) -> None:
    path = config_dir() / "custom_topic_presets.yaml"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump({"presets": presets}, allow_unicode=True, sort_keys=True), encoding="utf-8")


def load_topic_overrides() -> dict:
    path = config_dir() / "topic_overrides.yaml"
    if not path.exists():
        return {}
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def save_topic_overrides(overrides: dict) -> None:
    path = config_dir() / "topic_overrides.yaml"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(overrides, allow_unicode=True, sort_keys=True), encoding="utf-8")
