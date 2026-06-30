# RK3588 Full OTA Investigation

Date: 2026-05-25

## Scope

- Device checked: small-dog L1 RK3588, `firefly@192.168.234.1`.
- Current device release: `/etc/release/626002963WCB.yaml`.
- Package checked: `/home/user/测试工具/OTA/ota/packages/626002963WCB.tar.gz`.
- Goal: verify whether the system has a reliable complete flashing path for system image plus MCU/electric-control firmware.

## Confirmed On Device

- U-disk auto OTA is triggered by `/etc/udev/rules.d/99-auto-ota.rules`.
- The systemd entry is `/etc/systemd/system/devices-mount@.service`.
- The mount script is `/usr/local/bin/devices-mount.sh`.
- The fallback OTA script is `/usr/local/bin/devices-ota.sh`.
- The only firmware commands found in the fallback script are:
  - `mcu_upgrade -d /dev/spidev0.0 -f spline_release_*.bin`
  - `mcu_upgrade -d /dev/spidev0.1 -f spline_release_*.bin`
  - `mcu_upgrade -d /dev/ttyS3 -f power_board_release_*.bin`
  - `updateEngine --misc=update --image_url=/userdata/AIO-3588SJD4_Ubuntu.img`
- No other local or remote script was found that calls `mcu_upgrade` with motor `-l/-j`, IMU `-i`, charge-board, or battery parameters.

## Package Coverage

`626002963WCB.tar.gz` contains one RKFW system image and 12 firmware modules:

- supported by the original on-device fallback script: `spline`, `power_board`
- supported after AgibotD1 v0.8.4 `jupdate` reverse-engineering: `spline`, all `motorcontrol_*`, `imu_board`, `power_board`, and the RK3588 system image
- present in the package but not part of normal RK3588 OTA: `charge_board`, `battery(JS_12S2P)`

Follow-up confirmation from the vendor side clarified that the small-dog battery cannot be upgraded while the robot is in working state, so it cannot be upgraded through 3588 OTA. The charging base is unrelated to 3588. These two firmware files are bundled mainly for production convenience.

## Tool Behavior

- `/usr/local/bin/mcu_upgrade --help` exposes `-d`, `-f`, `-i`, `-l`, `-j`, `-r`, `-p`, `-b`, and `--no-check-filename`.
- Binary strings show it has motor, IMU, power, spline, and charge-related code, but the exact device paths and masks are not documented on the device.
- Read-only probes did not establish a safe mapping:
  - `mcu_upgrade -d /dev/ttyS3 -s` timed out.
  - `mcu_upgrade -d /dev/spidev0.0 -s` and `/dev/spidev0.1 -s` failed to open while runtime services were active.

## Conclusion

The on-device fallback script alone is incomplete, but the AgibotD1 v0.8.4 reverse-engineered `jupdate` flow provides the normal small-dog RK3588 OTA path:

- SOC check through `mcu_upgrade -d /dev/ttyS3 -p`
- stop `robot-launch.service`
- update `spline` on `/dev/spidev0.0` and `/dev/spidev0.1`
- update all matching `motorcontrol_*` by reading leg/joint hardware and software versions, then flashing with `-l`/`-j` masks
- update `imu_board` through `/dev/ttyS1 -i`
- update RK3588 image through `updateEngine --misc=update --image_url=<img>`
- update `power_board` through `/dev/ttyS3`
- reboot through `mcu_upgrade -d /dev/ttyS3 -r 5`

DogRemoteTool now treats `charge_board` and `battery(JS_12S2P)` as production-bundled non-OTA files for small-dog RK3588, so they do not block normal OTA and are not flashed by the 3588 OTA path.

## Medium-Dog RK3588 Addendum

Verified read-only on 2026-05-25 against medium-dog RK3588 `robot@192.168.234.1`:

- Device release: `/opt/release/version.yaml` reports `0.2.2`, release date `2026-04-25`.
- Package checked: `/home/user/测试工具/OTA/ota/packages/zg_rk3588_ota_v0.2.4.zip`.
- Package contents are complete: one RKFW image plus 7 firmware modules (`imu`, `actuator_joint`, `actuator_wheel`, `uart2can`, `hot_swap`, `power_control`, `battery`) and the matching tools (`mcu_upgrade_tool`, `actuator_upgrade_tool`, `uart2can_upgrade_tool`).
- On-device tools exist: `/opt/runtime/bin/actuator_tool`, `/opt/runtime/bin/mcu_upgrade`, `/opt/runtime/bin/canfd_upgrade`, `/usr/local/bin/updateEngine.sh`, plus `/home/robot/charge_pile_upgrade`.
- Confirmed HAL paths: power control `/dev/ttyCH9344USB6`, IMU `/dev/ttyS1`, actuator groups on CAN ports 0-3 with IDs `[1, 2, 3, 4]`.
- The device itself did not include a complete full OTA script, but the reversed ZsmFactory v0.2.2 package provides the missing medium-dog RK3588 flow:
  - workspace `/userdata/upgrade`
  - stop `robot-launch.service`
  - `imu`: `mcu_upgrade_tool -i -d /dev/ttyS1 -f <imu.bin>`
  - `actuator_joint`: `actuator_upgrade_tool --update <P85.bin> all:1,2,3`
  - `actuator_wheel`: `actuator_upgrade_tool --update <W190.bin> all:4`
  - `uart2can`: `uart2can_upgrade_tool --uart2canfd -d /dev/uart2canfd-can2 -f <uart2canfd.bin>` and `/dev/uart2canfd-can0`
  - `hot_swap`: `mcu_upgrade_tool -d /dev/ttyCH9344USB6 -f <hot_swap.bin>`
  - `power_control`: `mcu_upgrade_tool -d /dev/ttyCH9344USB6 -f <power_zg.bin>`
  - `system`: `updateEngine --misc=update --image_url=<img> --partition=0xFFFC00`
- Battery is confirmed as a separate RK module in ZsmFactory v0.2.2. The factory flow kills holders of `/dev/ttyCH9344USB6` and upgrades both `battery[1]` and `battery[2]` with the package `I0930B_APP*.bin`.

Additional ZsmFactory v0.2.2 evidence from `/home/user/下载/中狗过站上位机v0.2.2.zip`:

- `ReleaseNotes.txt` identifies version `v0.2.2`, date `2026-06-16`, and notes that OTA now supports `deb` and `whl` small-package upgrade plus UWB anchor upgrade.
- `ZsmFactory_autogen/INR4CDFWUZ/moc_UpgradeWorker.cpp` exposes the OTA slots `rkUpgradeConfig`, `startRkUpgrade`, `confirmRkUpgradeResult`, `nxUpgradeConfig`, and `startNxUpgrade`.
- UTF-16 strings in `ZsmFactory.exe` confirm `/userdata/upgrade`, `systemctl stop robot-launch.service`, `unzip/tar`, `updateEngine --misc=update --image_url=... --partition=0xFFFC00`, `/dev/uart2canfd-can2`, `/dev/uart2canfd-can0`, `/dev/ttyCH9344USB6`, `all:1,2,3`, `all:4`, `battery[%1]`, and `sh -lc "fuser -k /dev/ttyCH9344USB6 || true"`.
- The same strings show the v0.2.2 small-package path: `deb_regex`, `.deb`, `.whl`, `python3 -m pip install --upgrade --no-index --find-links %1 %2`, `dpkg -i --force-all`, `dpkg-query -W`, and `python3 -m pip show`. DogRemoteTool supports this as a separate remote small-package deploy path for OTA targets; it accepts single `.deb/.whl` files, deploy directories, and `.zip/.tar.gz` archives containing `.deb/.whl`, uploads them to a temporary remote stage, stops `robot-launch.service`, installs packages, and then attempts to restart `robot-launch.service`. For small-package archives it extracts only `.deb/.whl` members and does not execute bundled `deploy.sh` scripts. This is intentionally separate from the RK3588 full-image flow.
- UWB-related strings are present but not enough to validate a full safe flow by themselves: `fira uci uart`, `RTK MCU`, `Clock MCU`, `/dev/ttyTHS3`, `systemctl stop gpsd gpsd.socket; fuser -k /dev/ttyTHS3 || true`, and `%1 -d /dev/ttyTHS3 -t auto -r`. DogRemoteTool does not execute UWB anchor upgrade from the OTA page yet.

DogRemoteTool now recognizes the package as a complete medium-dog RK3588 full package and allows full flashing only for target `zg3588`; other RK3588 packages remain blocked when firmware modules are not covered.
