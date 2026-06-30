from __future__ import annotations

from pathlib import Path

from dog_remote_tool.core.paths import resource_dir
from dog_remote_tool.modules.ota.package_classifier import package_family


RESOURCE_PACKAGE_DIR = resource_dir("ota", "packages")
DEFAULT_PACKAGE_DIRS = (
    RESOURCE_PACKAGE_DIR,
    Path.home() / "Downloads",
    Path.home() / "下载",
)
DEFAULT_NX_TOOLS = RESOURCE_PACKAGE_DIR / "ota_tools_R36.4.4_aarch64.tbz2"
LEGACY_NX_TOOLS = Path.home() / "Downloads" / "ota_tools_R36.4.4_aarch64.tbz2"


def package_candidates(patterns: tuple[str, ...], package_dirs: tuple[Path, ...] | None = None) -> list[Path]:
    candidates: list[Path] = []
    roots = DEFAULT_PACKAGE_DIRS if package_dirs is None else package_dirs
    for root in roots:
        if not root.is_dir():
            continue
        for pattern in patterns:
            candidates.extend(path for path in root.glob(pattern) if path.is_file())
    return candidates


def latest_local(pattern: str, package_dirs: tuple[Path, ...] | None = None) -> Path | None:
    latest: tuple[float, Path] | None = None
    for path in package_candidates((pattern,), package_dirs):
        mtime = path.stat().st_mtime
        if latest is None or mtime > latest[0]:
            latest = (mtime, path)
    return latest[1] if latest else None


def latest_package_for_family(family: str, package_dirs: tuple[Path, ...] | None = None) -> Path | None:
    latest: tuple[float, Path] | None = None
    for path in package_candidates(("*.tar.gz", "*.zip"), package_dirs):
        if package_family(path) != family:
            continue
        mtime = path.stat().st_mtime
        if latest is None or mtime > latest[0]:
            latest = (mtime, path)
    return latest[1] if latest else None


def default_nx_tools(package_dirs: tuple[Path, ...] | None = None) -> Path | None:
    if DEFAULT_NX_TOOLS.is_file():
        return DEFAULT_NX_TOOLS
    if LEGACY_NX_TOOLS.is_file():
        return LEGACY_NX_TOOLS
    return latest_local("ota_tools*.tbz2", package_dirs)
