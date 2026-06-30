from __future__ import annotations

import shlex
import subprocess
from typing import Callable

from dog_remote_tool.core.profiles import ProductProfile
from dog_remote_tool.core.shell import ssh_options_argv_for_profile, sshpass_argv
import dog_remote_tool.modules.bag.finalize as _bag_finalize
import dog_remote_tool.modules.bag.local as _bag_local
import dog_remote_tool.modules.bag.logs as _bag_logs
import dog_remote_tool.modules.bag.names as _bag_names
import dog_remote_tool.modules.bag.remote_delete as _bag_remote_delete
import dog_remote_tool.modules.bag.remote_files as _bag_remote_files
import dog_remote_tool.modules.bag.recording_control as _bag_recording_control
import dog_remote_tool.modules.bag.recording_plan as _bag_recording_plan
from dog_remote_tool.modules.bag.backend_transfer import BagBackendTransferMixin
import dog_remote_tool.modules.bag.topic_check as _bag_topic_check
import dog_remote_tool.modules.bag.topic_probe as _bag_topic_probe


class BagBackend(BagBackendTransferMixin):
    def __init__(self, profile: ProductProfile, product: str | None = None, log: Callable[[str], None] | None = None) -> None:
        self.profile = profile
        self.product = product or _bag_names.profile_product_key(profile)
        self.log = log or (lambda _message: None)

    def ssh_options(self, connect_timeout: int = 10) -> list[str]:
        return ssh_options_argv_for_profile(
            self.profile,
            connect_timeout,
            server_alive_interval=15,
            server_alive_count_max=8,
        )

    def ssh_bash_command(self, remote_cmd: str, timeout: int = 15, *, login_shell: bool = True) -> subprocess.CompletedProcess:
        bash_flag = "-lc" if login_shell else "-c"
        wrapped_cmd = (
            "IFS= read -r DOG_REMOTE_SUDO_PASS || DOG_REMOTE_SUDO_PASS=; "
            "export DOG_REMOTE_SUDO_PASS; "
            f"{remote_cmd}"
        )
        remote_bash = f"bash {bash_flag} {shlex.quote(wrapped_cmd)}"
        cmd = [
            *sshpass_argv(self.profile.password),
            "ssh", *self.ssh_options(), self.profile.target, remote_bash,
        ]
        return subprocess.run(cmd, input=self.profile.password + "\n", capture_output=True, text=True, timeout=timeout)

    def start_remote_recording(self, script: str, remote_bag_paths: list[str]) -> tuple[bool, str]:
        return _bag_recording_control.start_remote_recording(remote_bag_paths, script, self.ssh_bash_command, self.log)

    def ros_env_lines(self) -> list[str]:
        return _bag_recording_plan.ros_env_lines(self.product)

    def build_record_plan(self, save_path: str, storage: str, cache_gb: int, topic_plan) -> _bag_recording_plan.RecordPlan:
        return _bag_recording_plan.build_record_plan(
            self.profile,
            self.product,
            save_path,
            storage,
            cache_gb,
            topic_plan,
            self.log,
        )

    def check_connection(self) -> tuple[bool, str]:
        try:
            result = self.ssh_bash_command('echo "连接成功"', timeout=10)
        except subprocess.TimeoutExpired:
            return False, "timeout"
        except Exception as exc:
            return False, str(exc)
        if result.returncode == 0:
            return True, ""
        return False, (result.stderr or result.stdout or f"return code {result.returncode}")[:300]

    def topic_check_units(self, topics: list[str]) -> list[dict]:
        return _bag_topic_check.topic_check_units(topics)

    def check_topics(self, topics: list[str], progress: Callable[[int, int, str], None] | None = None) -> tuple[list[str], list[str]]:
        return _bag_topic_probe.check_topics(topics, self.ros_env_lines(), self.ssh_bash_command, self.log, progress)

    def _topic_probe_env_lines(self) -> list[str]:
        return _bag_topic_probe.topic_probe_env_lines(self.profile, self.ros_env_lines())

    def list_remote_topics(self) -> list[dict]:
        return _bag_topic_probe.list_remote_topics(self.profile, self.ros_env_lines(), self.ssh_bash_command)

    def inspect_remote_topics(self, sample_seconds: float = 1.5, workers: int = 16) -> list[dict]:
        return _bag_topic_probe.inspect_remote_topics(
            self.profile,
            self.ros_env_lines(),
            self.ssh_bash_command,
            sample_seconds,
            workers,
        )

    def stop_remote_recording(self, remote_bag_paths: list[str]) -> bool:
        return _bag_recording_control.stop_remote_recording(remote_bag_paths, self.ssh_bash_command, self.log)

    def wait_remote_bags_finalized(self, remote_bag_paths: list[str], timeout: int = 180) -> bool:
        ready_paths = self.wait_remote_bags_finalized_paths(remote_bag_paths, timeout)
        return all(path in ready_paths for path in remote_bag_paths)

    def wait_remote_bags_finalized_paths(self, remote_bag_paths: list[str], timeout: int = 180) -> set[str]:
        return _bag_finalize.wait_remote_bags_finalized_paths(
            remote_bag_paths,
            self._remote_bag_statuses,
            self._remote_bag_status,
            self._reindex_remote_bag,
            self.log,
            timeout,
        )

    def _remote_bag_status(self, remote_path: str) -> dict[str, int]:
        result = self.ssh_bash_command(_bag_remote_files.remote_bag_status_command(remote_path), timeout=10)
        if result.returncode != 0:
            raise RuntimeError(result.stderr.strip() or result.stdout.strip() or f"return code {result.returncode}")
        return _bag_remote_files.parse_remote_bag_status(result.stdout)

    def _remote_bag_statuses(self, remote_paths: list[str]) -> dict[str, dict[str, int]]:
        if not remote_paths:
            return {}
        result = self.ssh_bash_command(_bag_remote_files.remote_bag_statuses_command(remote_paths), timeout=15)
        if result.returncode != 0:
            raise RuntimeError(result.stderr.strip() or result.stdout.strip() or f"return code {result.returncode}")
        return _bag_remote_files.parse_remote_bag_statuses(result.stdout)

    def remote_bags_size(self, remote_paths: list[str]) -> int:
        if not remote_paths:
            return 0
        result = self.ssh_bash_command(_bag_remote_files.remote_bags_size_command(remote_paths), timeout=20)
        if result.returncode != 0:
            raise RuntimeError(result.stderr.strip() or result.stdout.strip() or f"return code {result.returncode}")
        return _bag_remote_files.parse_remote_bags_size(result.stdout)

    def remote_recorded_topic_counts(self, remote_paths: list[str]) -> tuple[dict[str, int], list[str]]:
        if not remote_paths:
            return {}, []
        result = self.ssh_bash_command(_bag_remote_files.remote_bag_topic_counts_command(remote_paths), timeout=20)
        if result.returncode != 0:
            detail = result.stderr.strip() or result.stdout.strip() or f"return code {result.returncode}"
            return {}, [f"远端 metadata 读取失败: {detail[:200]}"]
        return _bag_remote_files.parse_remote_bag_topic_counts(result.stdout)

    def validate_remote_recorded_topics(self, remote_paths: list[str], expected_topics: list[str]) -> dict:
        counts, errors = self.remote_recorded_topic_counts(remote_paths)
        return _bag_local.validate_topic_counts(counts, expected_topics, self.topic_check_units(expected_topics), errors)

    def _reindex_remote_bag(self, remote_path: str) -> bool:
        remote_cmd = _bag_remote_files.remote_bag_reindex_command(remote_path)
        cmd = [
            *sshpass_argv(self.profile.password),
            "ssh", *self.ssh_options(), self.profile.target,
            f"bash -lc {shlex.quote(remote_cmd)}",
        ]
        return _bag_remote_files.run_remote_bag_reindex(cmd, remote_path, self.log)

    def scan_remote_bags(self, scan_dirs: list[str]) -> tuple[list[dict], dict | None]:
        result = self.ssh_bash_command(_bag_remote_files.remote_bag_scan_command(scan_dirs), timeout=30)
        if result.returncode != 0:
            raise RuntimeError((result.stderr or result.stdout or f"return code {result.returncode}")[:300])
        return _bag_remote_files.parse_remote_bag_scan_output(result.stdout)

    def resolve_remote_log_path(self) -> str:
        paths = self.resolve_remote_log_paths()
        if paths:
            return paths[0]
        candidates = _bag_logs.candidate_log_paths(self.product)
        return candidates[0] if candidates else "/tmp/zsibot/log"

    def resolve_remote_log_paths(self, log_kind: str = "all") -> list[str]:
        candidates = _bag_logs.candidate_log_paths(self.product, log_kind)
        if not candidates:
            return []
        try:
            result = self.ssh_bash_command(_bag_logs.resolve_log_paths_command(candidates), timeout=8)
        except Exception:
            return []
        if result.returncode != 0:
            return []
        return _bag_logs.parse_resolved_log_paths(result.stdout, candidates)

    def delete_remote_bags(self, remote_paths: list[str], auto_delete: bool = False) -> tuple[list[str], list[str]]:
        return _bag_remote_delete.delete_remote_bags(
            self.profile,
            remote_paths,
            self.ssh_options(),
            self.log,
            auto_delete,
        )

    @staticmethod
    def is_safe_remote_bag_path(remote_path: str, profile: ProductProfile | None = None) -> bool:
        return _bag_remote_files.is_safe_remote_bag_path(remote_path, profile)
