from __future__ import annotations

import os
from pathlib import Path

from dog_remote_tool.core.paths import resource_path


REMOTE_ACCESS_RESOURCE_NAME = "remote_access"
REMOTE_ACCESS_SCRIPT_NAME = "start_remote_access.sh"
REMOTE_ACCESS_BINARY_NAME = "remote_access"
FRP_ZIP_NAME = "frp_sevice.zip"
COMMUNITY_NODE_DEB_NAME = "community-node_0.0.4-arm64_nx_remote_control.deb"


def bundled_or_downloads_resource(env_name: str, resource_name: str) -> str:
    env_path = os.environ.get(env_name)
    if env_path:
        return str(Path(env_path).expanduser())
    bundled = resource_path(REMOTE_ACCESS_RESOURCE_NAME, resource_name)
    if bundled.is_file():
        return str(bundled)
    return str(Path.home() / "Downloads" / resource_name)
