from __future__ import annotations

import os
from pathlib import Path


def app_root() -> Path:
    env_root = os.environ.get("DOG_REMOTE_TOOL_ROOT")
    if env_root:
        return Path(env_root).expanduser().resolve()
    return Path(__file__).resolve().parents[3]


def resource_dir(*parts: str) -> Path:
    return app_root().joinpath("resources", *parts)


def resource_path(*parts: str) -> Path:
    return resource_dir(*parts)


def version_file() -> Path:
    return app_root() / "VERSION"
