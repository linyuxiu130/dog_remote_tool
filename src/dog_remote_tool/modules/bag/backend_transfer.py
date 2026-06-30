from __future__ import annotations

from datetime import datetime
from typing import Callable

from dog_remote_tool.core.profiles import ProductProfile
import dog_remote_tool.modules.bag.calibration as _bag_calibration
import dog_remote_tool.modules.bag.download as _bag_download
import dog_remote_tool.modules.bag.local as _bag_local
import dog_remote_tool.modules.bag.pull as _bag_pull
import dog_remote_tool.modules.bag.rsync as _bag_rsync
import dog_remote_tool.modules.bag.summary as _bag_summary
import dog_remote_tool.modules.bag.transfer as _bag_transfer


class BagBackendTransferMixin:
    profile: ProductProfile
    product: str
    log: Callable[[str], None]

    @staticmethod
    def local_log_source_dir(remote_log_path: str) -> str:
        return _bag_rsync.local_log_source_dir(remote_log_path)

    def build_rsync_command(
        self,
        remote_path: str,
        local_path: str,
        rsync_args: list[str] | None = None,
        excludes: list[str] | None = None,
    ) -> list[str]:
        return _bag_rsync.build_rsync_command(
            self.profile,
            self.ssh_options(connect_timeout=30),
            remote_path,
            local_path,
            rsync_args,
            excludes,
        )

    def run_rsync_with_progress(
        self,
        cmd: list[str],
        label: str,
        idle_timeout: int,
        progress: Callable[[str, float, str], None] | None = None,
        progress_prefix: str = "",
    ) -> bool:
        return _bag_rsync.run_rsync_with_progress(cmd, label, idle_timeout, self.log, progress, progress_prefix)

    def pull_bag_and_log(
        self,
        remote_bag_paths: list[str],
        local_base_dir: str,
        expected_topics: list[str],
        include_bag: bool,
        include_log: bool,
        delete_remote_on_success: bool = False,
        progress: Callable[[str, float, str], None] | None = None,
        record_info: dict | None = None,
        log_kind: str = "all",
    ) -> dict:
        lock_handles = self.acquire_transfer_locks(local_base_dir, remote_bag_paths) if include_bag else []
        try:
            return self._pull_bag_and_log_locked(
                remote_bag_paths,
                local_base_dir,
                expected_topics,
                include_bag,
                include_log,
                delete_remote_on_success,
                progress,
                record_info,
                log_kind,
            )
        finally:
            _bag_transfer.release_transfer_locks(lock_handles)

    def _pull_bag_and_log_locked(
        self,
        remote_bag_paths: list[str],
        local_base_dir: str,
        expected_topics: list[str],
        include_bag: bool,
        include_log: bool,
        delete_remote_on_success: bool = False,
        progress: Callable[[str, float, str], None] | None = None,
        record_info: dict | None = None,
        log_kind: str = "all",
    ) -> dict:
        return _bag_pull.pull_bag_and_log_locked(
            self,
            self.product,
            self.profile,
            self.log,
            remote_bag_paths,
            local_base_dir,
            expected_topics,
            include_bag,
            include_log,
            delete_remote_on_success,
            progress,
            record_info,
            log_kind,
        )

    def download_remote_bags(
        self,
        remote_bag_paths: list[str],
        bag_dir: str,
        progress: Callable[[str, float, str], None] | None = None,
    ) -> bool:
        return _bag_download.download_remote_bags(
            remote_bag_paths,
            bag_dir,
            self.wait_remote_bags_finalized_paths,
            self.wait_remote_bags_finalized,
            self.build_rsync_command,
            self.run_rsync_with_progress,
            self.log,
            progress,
        )

    def download_remote_logs(
        self,
        log_dir: str,
        progress: Callable[[str, float, str], None] | None = None,
        log_kind: str = "all",
    ) -> bool:
        return _bag_download.download_remote_logs(
            log_dir,
            self.product,
            lambda: self.resolve_remote_log_paths(log_kind),
            self.local_log_source_dir,
            self.build_rsync_command,
            self.run_rsync_with_progress,
            self.log,
            progress,
            log_kind,
        )

    def download_calibration_files(self, calibration_dir: str) -> bool:
        return _bag_calibration.download_calibration_files(calibration_dir, self.build_rsync_command, self.log, self.product)

    @staticmethod
    def acquire_transfer_locks(local_base_dir: str, remote_bag_paths: list[str]):
        return _bag_transfer.acquire_transfer_locks(local_base_dir, remote_bag_paths)

    @staticmethod
    def unique_directory_path(path: str) -> str:
        return _bag_transfer.unique_directory_path(path)

    @staticmethod
    def is_transfer_complete_directory(path: str) -> bool:
        return _bag_transfer.is_transfer_complete_directory(path)

    @staticmethod
    def write_transfer_state_marker(path: str, complete: bool) -> None:
        _bag_transfer.write_transfer_state_marker(path, complete)

    def transfer_target_directory(
        self,
        local_base_dir: str,
        dataset_name: str,
        remote_bag_paths: list[str],
        include_bag: bool,
    ) -> str:
        target_dir, message = _bag_transfer.transfer_target_directory(local_base_dir, dataset_name, remote_bag_paths, include_bag)
        if message:
            self.log(message)
        return target_dir

    @staticmethod
    def find_reusable_transfer_directory(local_base_dir: str, remote_bag_paths: list[str]) -> str:
        return _bag_transfer.find_reusable_transfer_directory(local_base_dir, remote_bag_paths)

    def write_record_summary(
        self,
        target_dir: str,
        dataset_name: str,
        remote_bag_paths: list[str],
        expected_topics: list[str],
        include_bag: bool,
        include_log: bool,
        bag_success: bool,
        log_success: bool,
        calibration_success: bool,
        deleted: list[str],
        delete_failed: list[str],
        validation: dict,
        record_info: dict,
        transfer_time: datetime,
    ) -> str:
        return _bag_summary.write_record_summary(
            self.product,
            self.profile,
            target_dir,
            dataset_name,
            expected_topics,
            include_bag,
            record_info,
            transfer_time,
        )

    @staticmethod
    def directory_size(path: str) -> int:
        return _bag_local.directory_size(path)

    @staticmethod
    def local_bag_paths(bag_dir: str) -> list[str]:
        return _bag_local.local_bag_paths(bag_dir)

    def validate_pulled_recording(
        self,
        target_dir: str,
        bag_success: bool,
        log_success: bool,
        expected_topics: list[str],
    ) -> dict:
        return _bag_local.validate_pulled_recording(
            target_dir,
            bag_success,
            log_success,
            expected_topics,
            self.topic_check_units(expected_topics),
        )
