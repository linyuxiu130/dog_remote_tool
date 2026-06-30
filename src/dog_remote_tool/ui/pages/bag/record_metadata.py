from __future__ import annotations

from datetime import datetime

from dog_remote_tool.core.profiles import ProductProfile
from dog_remote_tool.modules import bag


def record_context(
    remote_paths: list[str],
    product: str,
    storage: str,
    cache_gb: int,
    profile: ProductProfile | None = None,
    topics: list[str] | None = None,
    themes: list[str] | None = None,
    started_at: datetime | None = None,
) -> dict:
    return {
        "paths": remote_paths[:],
        "profile": profile,
        "topics": (topics or [])[:],
        "product": product,
        "themes": (themes or [])[:],
        "started_at": started_at,
        "finished_at": None,
        "duration_seconds": None,
        "storage": storage,
        "cache_gb": cache_gb,
    }


def empty_record_context() -> dict:
    return record_context([], "", "", 0)


def record_info(
    profile: ProductProfile,
    current_product: str,
    remote_paths: list[str],
    record_product: str,
    themes: list[str],
    topics: list[str],
    started_at: datetime | None,
    finished_at: datetime | None,
    duration_seconds: int | None,
    storage: str,
    fallback_storage: str,
    cache_gb: int,
    fallback_cache_gb: int,
    now: datetime | None = None,
) -> dict:
    started = started_at.strftime("%Y-%m-%d %H:%M:%S") if started_at else ""
    finished = finished_at.strftime("%Y-%m-%d %H:%M:%S") if finished_at else ""
    timestamp = started_at or now or datetime.now()
    product = record_product or current_product
    dataset_name = bag.dataset_name_from_remote_bags(remote_paths)
    if not dataset_name:
        dataset_name = bag.standard_dataset_name(product, profile, timestamp)
    return {
        "dataset_name": dataset_name,
        "product": product,
        "profile_key": profile.key,
        "profile_label": profile.label,
        "platform": profile.platform,
        "target": profile.target,
        "themes": themes[:],
        "topics": topics[:],
        "started_at": started,
        "finished_at": finished,
        "duration_seconds": duration_seconds,
        "storage": storage or fallback_storage,
        "cache_gb": cache_gb or fallback_cache_gb,
    }
