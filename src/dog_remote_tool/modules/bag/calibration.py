from __future__ import annotations

import os
import subprocess
from typing import Callable


REMOTE_CALIBRATION_FILES = ("/ota/calibration_results.yaml",)
L2_CALIBRATION_FILES = ("/ota/calibration_results.yaml", "/ota/l2_new.yaml")


def calibration_files_for_product(product: str) -> tuple[str, ...]:
    if product == "nxl2":
        return L2_CALIBRATION_FILES
    return REMOTE_CALIBRATION_FILES


def download_calibration_files(
    calibration_dir: str,
    build_rsync_command: Callable[[str, str], list[str]],
    log: Callable[[str], None],
    product: str = "",
) -> bool:
    log("正在保存标定文件...")
    calibration_success = False
    for remote_file in calibration_files_for_product(product):
        cmd = build_rsync_command(remote_file, calibration_dir + os.sep)
        result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=60)
        if result.returncode == 0:
            calibration_success = True
            log(f"✓ 标定文件保存完成: calibration/{os.path.basename(remote_file)}")
        else:
            hint = (result.stdout or "").strip().splitlines()
            log(f"  标定文件未保存: {remote_file} ({hint[-1][:120] if hint else '远端文件不存在或无法访问'})")
    return calibration_success
