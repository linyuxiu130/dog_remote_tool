# 远程调试平台

小狗/中狗机器人远程调试、测试和运维平台。

## 开发启动

```bash
cd dog_remote_tool
PYTHONPATH=src python3 -m dog_remote_tool
```

也可以直接运行：

```bash
bash 启动.sh
```

## 遥控资源

- 小狗二代 3588、小狗二代 S100、中狗 3588、中狗环视版 S100 和中狗激光版 NX 的遥控控制端统一映射到对应 3588 本体 `192.168.234.1:8081`，使用 RobotSDK/robot_remote `Protocol-1.2.0` WebSocket 协议。
- 2026-06-23 实机核实小狗 L2 S100：S100 入口是 `robot@192.168.168.100`，但 `8081` 不监听；遥控入口在 3588 `robot@192.168.234.1:8081`，只读握手返回 `device_type=ZSL-2-Ultra`、`model=ZGW`。工具默认不再使用旧的 F710 event 注入链路。
- 已在实机验证中狗 `robot_remote` 服务同时监听 TCP `8081` 和 UDP `8082`；握手返回 `device_type=ZSM-1`、`model=ZGW`、系统版本 `0.2.3`。工具中的“robot_remote 检查”对中狗默认只读握手和心跳，不获取控制权。
- 小狗 L2 和中狗键盘遥控使用协议 `1003` 遥控帧；已按官方 SDK 通信结果确认 `Move(left_right, forward_back, yaw)` 对应 `lx/ly/rx`，即 `lx=左右平移`、`ly=前进后退`、`rx=转向`。本体速度读取使用远端 `/robot_control_server/mc_state`。

## OTA 资源

- OTA 工具资源随发布包放在 `resources/ota/packages/`；升级包可从界面手动选择，默认会先看随包资源目录和当前用户下载目录。
- OTA/线刷页面面向小狗 L1 点足/轮足的 3588/NX 远程 OTA，以及中狗 3588 远程 OTA；S100 和 Orin NX 平台按本机 USB 线刷处理。
- 中狗 NX full OTA ZIP（如 `nx_ota_hermes_m_*_full.zip`）按 `zgnx` 远程 NX OTA 执行；同一中狗 NX 设备选择 Orin 线刷包时仍按本机 USB 线刷处理。
- L2 S100 与中狗 S100 识别 S100 线刷包：`product/img_packages/flash_all.sh`、`s100-gpt.json`、`disk/emmc_disk.simg`。
- 中狗 NX 识别 Orin NX 线刷包：`bootloader/flashcmd.txt`、`bootloader/system.img`。
- 线刷执行在本机进行：先解压到 `~/.cache/dog_remote_tool/line_flash/`；S100 线刷目前只允许在“小狗二代 S100”和“中狗环视版 S100”目标下执行，如果已在 fastboot 会直接执行 `bash ./flash_all.sh -m all`，否则会先尝试通过目标 SSH 执行 `sudo reboot usb2 -f` 进入刷写状态，再用 DFU `3652:6610/6615/6620/6625` 引导到 fastboot；Orin NX 执行 `bash ./flashcmd.txt`。如需禁用自动 SSH 进入刷写状态，可在启动工具前设置 `DOG_REMOTE_TOOL_S100_AUTO_REBOOT=0`；SSH 触发默认 12 秒超时，可用 `DOG_REMOTE_TOOL_S100_SSH_TIMEOUT` 调整。
- 本机线刷工具已随工程归档到 `resources/platform-tools/linux-x86_64/`；GUI 会优先使用内置 `bin/fastboot` 和 `bin/dfu-util`，发布包会随 `resources/` 一起携带，系统 PATH 里的同名工具只作为后备。
- S100 DFU 引导默认选择 `secure_ohp` 资产；需要切换时可在启动工具前设置 `DOG_REMOTE_TOOL_S100_BOOT_SECURITY=secure` 或 `DOG_REMOTE_TOOL_S100_BOOT_SECURITY=nosecure`。为避免误刷，检测到多台 `3652:*` DFU 设备会直接中止；检测到多台 fastboot 设备时，预检只警告，执行线刷会直接中止。
- S100 预检会区分 CH340-only 状态：如果只看到 `1a86:8091/1a86:7523`，说明当前只是串口/HUB 枚举，尚未进入 `3652:6610` DFU 或 fastboot 线刷状态。预检还会优先检查同名 `_extracted` 目录或线刷缓存中的 `product/img_packages`、`product/xmodem_tools` 和当前 DFU 引导安全类型所需文件；如果没有可复用解压目录，可设置 `DOG_REMOTE_TOOL_S100_TAR_LIST_CHECK=1` 强制读取 tar 清单，但大包会比较耗时。最后会输出“S100 刷写入口就绪结论”，区分已在 fastboot、已在 `3652:6610`、可尝试 SSH 自动进入，或必须手动按 BOOT/RECOVERY；系统不可达时手动方式是断电后按住 `BOOT/RECOVERY/USB_BOOT`，再上电或插 Type-C，直到看到 `3652:6610` 后松开；如果已在 fastboot，会提前检查 `bootintf=mmc/scsi` 是否分别匹配 `disk/emmc_disk.simg`/`disk/ufs_disk.simg`；未就绪时会给出只读 `watch` 命令，用于观察 USB/fastboot 枚举。
- S100 目标下有独立的“刷写入口”按钮，不需要选择升级包，不会重启或刷机；它只读观察本机 USB/fastboot/SSH 状态，默认最多 45 秒。只有 SSH 端口可达、本机 `sshpass` 可用且密码登录只读探测通过时，才判定为可自动进入刷写状态；可用 `DOG_REMOTE_TOOL_S100_ENTRY_WATCH_SECONDS` 和 `DOG_REMOTE_TOOL_S100_ENTRY_WATCH_INTERVAL` 调整观察时长和间隔。
- 3588 包支持 `*.tar.gz` 和 `*.zip`：小狗 L1 包会读取包内 YAML 的 `motion-control` 字段，`xg` 提示点足、`xgw` 提示轮足；中狗 3588 zip 会按 `package_info.json` 找到 `image/*.img` 并校验 RKFW 文件头。
- 本地已解析的 3588 包线索：`606002963WCB.tar.gz` 对应 `motion-control_0.5.7-xg_arm64.deb`（点足），`626002963WCB.tar.gz` 对应 `motion-control_0.5.7-xgw_arm64.deb`（轮足）。
- OTA 包默认上传/解压到 `~/ota`；中狗 3588 按 ZsmFactory 流程使用 `/userdata/upgrade`；3588 最终镜像固定复制到 `/userdata/update/<包名>/<img>` 后执行 `updateEngine`。
- OTA 页面不再单独选择设备或填写登录信息，OTA 目标跟随顶部“当前设备”和登录配置，避免和全局设备选择不一致。
- OTA 页面会在设备信息里显示远端业务版本、发布日期和 L4T 版本；设备信息读取为只读，不创建远端目录或测试文件。
- NX OTA 工具包已归档到 `resources/ota/packages/ota_tools_R36.4.4_aarch64.tbz2`，发布包会一并携带；NX full OTA ZIP 默认刷写随包 `rtk_mcu`，可在 OTA 页取消“刷 NX MCU”后仅执行系统 OTA。
- OTA 页选择升级包只做本地包信息显示，不自动执行远端预检；点击 `升级` 时仍会先做完整包结构校验。3588 默认按全量升级处理：小狗 3588 按 AgibotD1 v0.8.4 反编译链路刷 `spline`、`motorcontrol`、`imu_board`、`power_board` 和系统镜像，包内 `charge_board` 与 `battery(JS_12S2P)` 属于产线随包内容，常规 3588 OTA 不执行；中狗 3588 ZIP 全量包按 ZsmFactory v0.2.2 反编译参数执行 7 模块全量刷写，电池会分别刷写 `battery[1]` 和 `battery[2]`。
- 远程 OTA 目标支持 ZsmFactory v0.2.2 的小包升级路径：可选择单个 `.deb`、单个 `.whl`、包含 `.deb/.whl` 的小包目录，或包含 `.deb/.whl` 的 `.zip/.tar.gz` 小包压缩包；执行时上传到远端目录下的临时子目录，安装前停止 `robot-launch.service`，`.deb` 使用 `dpkg -i --force-all`，`.whl` 使用 `python3 -m pip install --upgrade --no-index --find-links`，安装后尝试重启 `robot-launch.service`。小包压缩包只提取并安装 `.deb/.whl`，不执行随包 `deploy.sh`。UWB 锚点升级字符串已解析记录，但 OTA 页面暂不执行 UWB 升级。
- 远程 OTA 依赖本机可用 `ssh` 和 `sshpass`，`rsync` 可选；缺失时设备信息读取或执行阶段会提示错误。

## 远程访问资源

- 远程访问、FRP 5G 公网映射和 NX 联网远程控制统一放在“远程访问”页面。
- “公网连接”里的第一个按钮用于打开或关闭公网 SSH 映射；页面会自动刷新当前状态。`0.2.9(B)+` 新版本使用 `robot-launch start/stop remote_access` 管理，旧版本才使用脚本直启兼容流程。
- “替换远程脚本”按钮用于新版本设备：比对工具内置脚本和远端 `/opt/robot/nx-launch/script/start_remote_access.sh`，不一致时先在同目录生成 `.bak.<时间>` 备份，再替换远端脚本；该按钮不启动也不关闭公网连接。
- 公网连接使用工具内置资源：`resources/remote_access/start_remote_access.sh` 和 `resources/remote_access/remote_access`；发布包会携带这两个文件。
- FRP 部署包默认使用随包 `resources/remote_access/frp_sevice.zip`，也可用 `DOG_REMOTE_TOOL_FRP_ZIP` 覆盖或在界面手动选择。
- FRP 推荐流程：部署包、生成 `/opt/frp-client/frpc.toml`，再后台启动 `/opt/frp-client/frpc`。
- NX 联网远程控制 community-node 包默认使用随包 `resources/remote_access/community-node_0.0.4-arm64_nx_remote_control.deb`，也可用 `DOG_REMOTE_TOOL_COMMUNITY_NODE_DEB` 覆盖或在界面手动选择。
- 当前改动只更新源码；`release/` 下的可执行发布包需要单独运行打包脚本后才会同步。

## 发行包体积

- 默认运行 `build/build_release.sh` 会生成瘦身包：保留本地 RTSP 视频、地图膨胀层和常用资源，并只携带 3588 镜像缺失的最小远端 RTSP arm64 `.deb` 集合。自解压 payload 默认使用 `xz` 压缩；如需旧 gzip 格式，可用 `DOG_REMOTE_BUNDLE_COMPRESSION=gzip build/build_release.sh`。
- 如需完全不携带远端 RTSP 离线包，可用 `DOG_REMOTE_BUNDLE_RTSP_DEBS=0 build/build_release.sh`。
- 需要极简包时，可用 `DOG_REMOTE_BUNDLE_OPENCV=0 build/build_release.sh`；该包不内置 OpenCV/Numpy/GStreamer，本地 RTSP 画面和地图障碍膨胀依赖目标电脑已有对应 Python 包。
- 兼容排查时可用 `DOG_REMOTE_BUNDLE_GSTREAMER_ALL=1` 带上全部本机 GStreamer 插件，或用 `DOG_REMOTE_BUNDLE_QT_NATIVE_THEME=1` 带上 Qt 原生主题插件。

## 建图页面

- “建图”和“定位”页面会按当前目标切换默认参数：小狗二代 S100 使用 `SENSOR_TYPE=nx_xg_rs`、建图保存目录 `/ota/alg_data/map`、标定文件 `/ota/calibration_results.yaml`；中狗 S100/NX 使用 `SENSOR_TYPE=nx_zg`、建图保存目录 `/ota/alg_data/map`、标定文件 `/ota/calibration_results.yaml`。
- 支持一键开始建图、显示当前建图状态、结束并保存建图、取消建图，并手动选择历史地图回传。
- 本地新数据默认归档到 `~/data/`：Bag 回传使用 `bags/`，地图回传使用 `maps/`，日志和故障包建议放 `logs/`、`fault_logs/`。
- “回传 map.pcd / map.pgm / map.txt”会从远端建图保存目录递归同步 `map.pcd`、`map.pgm`、`map.yaml`、`map.txt` 和 `map.static/static_map.txt` 到本地回传目录。
- “开始建图 / 结束并保存建图 / 取消建图 / 查看状态”默认走 `robot_alg_manager` App WebSocket 方案，通过 `start_mapping: 1`、`stop_mapping: 1`、`cancel_mapping`、`get_mapping_status` 控制和读取建图。
- 建图状态按 alg 返回值解析：`MappingReady/Ready/StandBy` 为空闲就绪，`MappingRunning/Mapping` 为建图中，`MappingSaveBegin/MappingSaving` 为保存中，`MappingSaveEnd/MappingSaved` 为保存完成，`MappingError` 等错误值会直接提示失败；默认 UI 和命令入口不再使用旧状态码控制建图。
- 状态详情只展示 alg 状态、历史地图文件和本工具建图动作日志，用于排查 alg 返回异常或地图未落盘的问题。
- L2 S100 普通建图会在远端地图目录产生当前 `map.pgm/map.yaml/map.pcd` 和 `history_map/<时间>/` 历史地图文件。
- 页面会自动读取当前目标建图保存目录下的 `history_map/<时间>/map.pgm`，不再把当前 `map.pgm` 混入历史地图列表。
- 下拉框切换地图时会自动拉取选中的 `map.pgm` 到 `~/data/maps/_preview/` 并在页面内显示；“回传选中地图”只回传所选 `map.pgm` 所在目录。
- 建图页隐藏通用“停止任务”按钮；保存退出用“结束并保存建图”，放弃当前结果用“取消建图”。
- 建图页日志只显示动作结果，不打印完整 SSH/SCP/rsync 命令。

## 导航页面

- “导航”页面面向 NX、S100、ZGNX 导航联调；默认从当前设备的建图保存目录读取 `history_map/<时间>/map.pgm`，自动换算同目录 `map.pcd` 作为导航地图，并在页面内加载地图预览。
- 顶部状态卡显示地图、定位、授权/标定、导航栈和任务状态；“流程预检”会检查地图文件、授权文件、标定文件、导航进程、`/start_navigation` 订阅者、`/navigate_to_pose`/`/navigate_through_poses` action server、定位状态、关键 topic、`/navigation_cmd`/`/handle_vel`/`/cmd_vel` 最近一次速度采样和导航日志中的 lifecycle 异常。
- “流程预检”会报告地图、授权、标定、`/start_navigation` 订阅者、导航 action server 和定位准入状态；巡航、多点和路网导航仍按这些前置状态做较严格检查。普通单点目标会直接下发当前地图和目标信息，避免一次点击受状态刷新或定位回显延迟影响。
- 当前页面提供 `巡航`、`多点导航` 和 `路网导航` 入口。点位可在地图预览上点击添加，也可在点位框中按 `x,y` 或 `x,y,yaw` 每行填写一个点；发送走 `/start_navigation`，消息类型 `robots_dog_msgs/msg/StartNavigation`。`加载地图` 会加载定位 PCD 并单独发送 `CMD_INITIALIZE` 初始化导航地图；普通目标在 START 阶段发送 `GoalTask`，携带当前 2D `map.yaml`、`map_type=MAP_TYPE_MAP_2D` 和 `source_type=SOURCE_TYPE_GOAL`，发送后开启导航模式并返回 UI。普通目标会启动远端后台监控，任务完成、失败、取消或回到空闲时释放导航控制权。多点/建图轨迹寻迹使用 `GoalTask.goal_task_type=GOAL_TASK_TYPE_GOAL_2D`、`map_type=MAP_TYPE_MAP_2D`，多点使用 `GoalTask.source_type=SOURCE_TYPE_REFERENCE_LINE`，路网导航使用 `GoalTask.goal_task_type=GOAL_TASK_TYPE_GOAL_ROUTE`、`map_type=MAP_TYPE_MAP_ROUTE`。导航运动控制由远端导航栈下发到底盘；中狗手动遥控走 3588 `robot_remote` 的 `1003` 帧。
- 实机 XGL2/S100 当前非运动预检结果：前单雷达设备需将远端 `/opt/runtime/bin/start_rslidar_driver.sh` 切到 `zs_m1_air.launch.py`，并将 `/opt/robot/robot_localization/install/localization/share/localization/config/ros_params_loc_zg.yaml` 的 `dual_lidar_config.enable_dual_lidar` 设为 `false`。修改后 `/front_lidar` 有数据、`/rear_lidar` 无发布者符合预期，但定位仍报 `LIDAR data lost`，`/navigation_state` 报 `Laser scan data missing`，`map -> base_link` TF 不存在，Nav2 lifecycle 仍未全 active，因此工具会继续阻止巡航/多点导航下发。
