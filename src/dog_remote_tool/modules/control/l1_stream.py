from __future__ import annotations

from dog_remote_tool.core.network_routes import with_route_repair
from dog_remote_tool.core.profiles import ProductProfile
from dog_remote_tool.core.shell import quote, ssh_prefix_command
from dog_remote_tool.modules.control.l1_stream_remote import L1_STREAM_REMOTE_PY


def build_l1_sdk_stream_command(target: ProductProfile, sdk_root: str, percent_limit: int, interval: float) -> str:
    remote_script = f"""
set -e
stream_py="${{TMPDIR:-/tmp}}/dog_remote_l1_sdk_stream_$$.py"
cat > "$stream_py" <<'PY'
{L1_STREAM_REMOTE_PY.rstrip()}
PY
trap 'rm -f "$stream_py"' EXIT
export DOG_REMOTE_L1_SDK_ROOT={quote(sdk_root)}
export DOG_REMOTE_L1_ROBOT_IP={quote(target.host)}
export DOG_REMOTE_L1_PERCENT_LIMIT={percent_limit}
export DOG_REMOTE_L1_INTERVAL={interval}
    exec python3 -u "$stream_py"
    """
    command = (
        f"{ssh_prefix_command(target)} {quote('bash -lc ' + quote(remote_script))}"
    )
    return with_route_repair(target, command)
