from __future__ import annotations

import os
import subprocess

from dog_remote_tool.core.quoting import quote
import dog_remote_tool.modules.ota.backend_runner as _runner
from dog_remote_tool.modules.ota.targets import OtaTarget


def run_remote_script(target: OtaTarget, script: str, env: dict[str, str]) -> None:
    remote_script = "/tmp/dog_remote_ota_%s.sh" % os.getpid()
    _runner.run_stream(
        _runner.ssh_args(target, f"cat > {quote(remote_script)} && chmod 700 {quote(remote_script)}"),
        input_text=script,
    )
    env_values = dict(env)
    sudo_password = env_values.pop("SUDO_PASSWORD", target.password)
    env_prefix = " ".join(f"{key}={quote(value)}" for key, value in env_values.items())
    remote = (
        "IFS= read -r SUDO_PASSWORD || exit 1; export SUDO_PASSWORD; "
        f"{env_prefix} bash {quote(remote_script)}"
    )
    try:
        _runner.run_stream(_runner.ssh_args(target, remote), input_text=sudo_password + "\n")
    finally:
        try:
            _runner.capture(_runner.ssh_args(target, f"rm -f {quote(remote_script)}"))
        except subprocess.CalledProcessError:
            pass
