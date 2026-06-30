from __future__ import annotations

import sys

import dog_remote_tool.modules.mobile_diag.parse as _mobile_diag_parse
import dog_remote_tool.modules.mobile_diag.performance as _mobile_diag_performance
import dog_remote_tool.modules.mobile_diag.ros_shm as _mobile_diag_ros_shm
import dog_remote_tool.modules.mobile_diag.services as _mobile_diag_services
from dog_remote_tool.modules.mobile_diag.network_script import DIAG_SCRIPT


diag_command = _mobile_diag_services.diag_command
recover_and_diag_command = _mobile_diag_services.recover_and_diag_command
service_status_command = _mobile_diag_services.service_status_command
restart_service_command = _mobile_diag_services.restart_service_command
enable_service_command = _mobile_diag_services.enable_service_command
reboot_command = _mobile_diag_services.reboot_command
parse_performance_probe_output = _mobile_diag_parse.parse_performance_probe_output
probe_float = _mobile_diag_parse.probe_float
format_probe_percent = _mobile_diag_parse.format_probe_percent
format_probe_temp = _mobile_diag_parse.format_probe_temp
performance_snapshot_command = _mobile_diag_performance.performance_snapshot_command
performance_sample_command = _mobile_diag_performance.performance_sample_command
performance_probe_command = _mobile_diag_performance.performance_probe_command
ros_shm_check_command = _mobile_diag_ros_shm.ros_shm_check_command
ros_shm_cleanup_command = _mobile_diag_ros_shm.ros_shm_cleanup_command


def main(argv: list[str] | None = None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    if argv == ["--print-script"]:
        try:
            sys.stdout.write(DIAG_SCRIPT)
        except BrokenPipeError:
            return 0
        return 0
    sys.stderr.write("usage: python3 -m dog_remote_tool.modules.mobile_diag --print-script\n")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
