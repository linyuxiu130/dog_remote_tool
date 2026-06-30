# Dog Remote Tool

面向小狗/中狗机器人实机测试的 PyQt 远程调试工具。它把 SSH、ROS 2、录包、遥控、建图、导航、文件管理、远程访问、OTA 和线刷相关的常用操作集中到一个桌面界面里，方便现场测试和排障。

> 注意：本工具会执行远程命令、升级、刷机、删除文件和运动控制等高风险操作。使用前请确认目标设备、网络、账号和现场安全状态。

## 功能范围

- 设备状态：读取主机、版本、小包、服务、电量、网络和基础运行状态。
- 遥控与视频：支持 L1 SDK 控制、L2/中狗 `robot_remote` 控制、RTSP 画面预览和控制端点检查。
- 录包：按设备类型加载内置 topic 配置，支持远端录包、状态检查、拉取、删除和 metadata 重建。
- 建图与地图：启动/结束/取消建图，读取历史地图，回传 `map.pgm`、`map.pcd`、`map.yaml`、`map.txt` 等文件。
- 导航联调：地图加载、流程预检、单点/多点/巡航/路网导航、导航状态和速度链路检查。
- 文件管理：远端目录浏览、上传、下载、重命名、删除和常用路径操作。
- 远程访问：公网 SSH 映射、FRP 部署、remote_access 脚本同步、NX 联网远程控制包安装。
- OTA 与线刷：3588/NX 远程 OTA、小包安装、S100/Orin NX 本机 USB 线刷预检和执行。
- 移动网络诊断：4G/5G 模块、拨号服务、运营商注册和网络状态检查。

## 支持设备

代码里的设备能力以 `src/dog_remote_tool/core/profiles.py` 为准，界面会根据当前设备 profile 启用或禁用功能。当前主要覆盖：

- 小狗 L1 点足/轮足
- 小狗 L2 3588
- 小狗 L2 S100
- 中狗 3588
- 中狗环视版 S100
- 中狗激光版 NX / ZGNX

部分 S100/NX 动作会映射到对应 3588 控制端，例如 L2 S100 的遥控入口使用 3588 的 `192.168.234.1:8081`。

## 运行环境

推荐环境：

- Ubuntu 22.04
- Python 3.10
- PyQt5
- OpenSSH、`sshpass`、`rsync`
- 可选：OpenCV、NumPy、GStreamer，用于本地 RTSP 画面和地图膨胀显示

常见依赖安装示例：

```bash
sudo apt update
sudo apt install -y \
  python3 python3-pyqt5 python3-yaml python3-numpy python3-opencv \
  openssh-client sshpass rsync
```

如果只运行部分命令生成功能或单元测试，可按缺失模块提示补装依赖。

## 启动

源码方式启动：

```bash
cd dog_remote_tool
PYTHONPATH=src python3 -m dog_remote_tool
```

本机常用启动脚本：

```bash
bash 启动.sh
```

启动脚本会设置 `DOG_REMOTE_TOOL_ROOT` 和 `PYTHONPATH`，并避免重复启动已存在的 `python3 -m dog_remote_tool` 进程。

检查指定设备的小包版本：

```bash
bash 启动.sh --check-versions xg2_3588 xg2_s100
```

## 目录结构

```text
.
├── src/dog_remote_tool/       # 应用源码
│   ├── app.py                 # 程序入口
│   ├── core/                  # profile、命令封装、路径、runner、解析基础设施
│   ├── modules/               # 业务逻辑和命令生成
│   └── ui/                    # PyQt 页面、组件和样式
├── resources/                 # 发布包需要携带的脚本、工具、配置和离线包
├── scripts/                   # 独立辅助脚本
├── tests/                     # 单元测试和 GUI smoke test
├── build/                     # 发布包构建脚本
├── docs/                      # 调研记录和使用手册
└── 启动.sh                    # 本机启动入口
```

`resources/` 是运行和打包所需资源目录，不是缓存目录。里面包含 OTA 工具、线刷工具、录包 topic 配置、remote_access/FRP 资源和 RTSP bridge 离线包。

## 关键资源

- `resources/record_bag/`：不同设备族的录包 topic 配置和 MCAP writer 配置。
- `resources/remote_access/`：`start_remote_access.sh`、`remote_access`、FRP 部署包和 NX community-node 包。
- `resources/ota/packages/`：NX OTA 工具包等随包 OTA 资源。
- `resources/platform-tools/linux-x86_64/`：S100 线刷优先使用的内置 `fastboot`、`dfu-util` 和依赖库。
- `resources/xburn/linux-x86_64/`：S100 整盘烧写使用的 `xburn` 工具和配置。
- `resources/rtsp_bridge/ubuntu22.04-arm64/`：远端 RTSP bridge 所需的最小 arm64 deb 集合。

## 安全约定

- 刷机、升级、删除、重启、服务启停、替换远端脚本、运动控制等动作都应走危险操作确认。
- 只读探测和会修改远端状态的动作要区分清楚。
- 命令日志不应输出密码、完整 `sshpass` 明文或不必要的大段传输进度。
- 远端路径必须经过后端校验，不要只依赖 UI 提示。
- 默认验证不连接实机、不刷机、不重启设备；实机操作需要明确目标和风险范围。

## 测试

编译检查：

```bash
PYTHONPATH=src python3 -m py_compile $(find src tests -name '*.py')
```

GUI 启动 smoke test：

```bash
QT_QPA_PLATFORM=offscreen PYTHONPATH=src python3 tests/smoke_main_window.py
```

运行全部测试：

```bash
PYTHONPATH=src pytest
```

运行单个测试文件：

```bash
PYTHONPATH=src pytest tests/test_ota.py
```

## 打包

默认构建自解压 `.run` 发布包：

```bash
build/build_release.sh
```

构建脚本要求 Python 3.10 和本机可用 PyQt5、SSH 工具、GStreamer 等运行时依赖。输出目录为 `release/`，中间产物在 `.build/`。

常用构建选项：

```bash
# 不携带远端 RTSP 离线 deb 包
DOG_REMOTE_BUNDLE_RTSP_DEBS=0 build/build_release.sh

# 不内置 OpenCV/Numpy/GStreamer，生成更小包
DOG_REMOTE_BUNDLE_OPENCV=0 build/build_release.sh

# 使用 gzip payload，便于兼容排查
DOG_REMOTE_BUNDLE_COMPRESSION=gzip build/build_release.sh
```

`release/` 和 `.build/` 是生成物，不应提交到 Git。

## 开发约定

- 程序入口：`src/dog_remote_tool/app.py`
- 主窗口：`src/dog_remote_tool/ui/main_window.py`
- 页面注册：`src/dog_remote_tool/ui/main_window_pages.py`
- 设备 profile：`src/dog_remote_tool/core/profiles.py`
- 命令执行：`src/dog_remote_tool/core/runner.py`
- SSH/rsync/shell 封装：`src/dog_remote_tool/core/shell.py`
- 后端模块：`src/dog_remote_tool/modules/`
- 页面模块：`src/dog_remote_tool/ui/pages/`

新增功能优先把可测试逻辑放在 `modules/`，UI 页面只负责输入、状态、按钮和调用后端命令。修改设备能力、命令生成、路径安全、OTA、导航、遥控和文件操作时，应补充或运行对应测试。

## Git 清理建议

提交前保持仓库只包含源码、文档、测试和必要资源。不要提交：

- `.build/`
- `release/`
- `.pytest_cache/`
- `__pycache__/`
- `*.pyc`
- 本地回传数据、日志、故障包和临时快照

`.gitignore` 已覆盖这些常见生成物。
