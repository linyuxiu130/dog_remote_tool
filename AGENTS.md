# Dog Remote Tool 开发代理规范

本项目是面向实机操作员的 PyQt 远程测试工具，涉及 SSH、ROS、录包、遥控、建图、定位、导航、文件管理、远程访问、OTA 和线刷。修改代码时优先保证设备安全、操作可解释、失败可恢复，其次才是实现便利。

## 项目结构

- 程序入口：`src/dog_remote_tool/app.py`，开发启动命令是 `PYTHONPATH=src python3 -m dog_remote_tool`。
- 主窗口：`src/dog_remote_tool/ui/main_window.py`，负责 `DeviceBar`、全局日志、页面懒加载和关闭清理。
- 公共 UI 组件：`src/dog_remote_tool/ui/components.py`，包含 `DeviceBar`、`CommandPage`、`LogPanel` 和危险命令确认。
- GUI 页面：`src/dog_remote_tool/ui/pages/`，页面只负责交互、状态展示和调用后端模块。
- 后端模块：`src/dog_remote_tool/modules/`，负责命令生成、协议适配、解析、校验和设备专用逻辑。
- 核心基础设施：`src/dog_remote_tool/core/`，包括 `ProductProfile`、`ProcessRunner`、SSH/rsync 命令封装和日志格式化。
- 测试：`tests/`，重点覆盖命令生成、解析、安全校验、页面轻量逻辑和启动 smoke。
- 资源：`resources/`，发布包需要携带的脚本、OTA 工具、录包配置等放这里。
- 发布产物：`release/` 和 `.build/` 是构建输出，不要把修改产物当作源码修复。

## 架构边界

- 开发时不要猜测代码行为、设备能力或远端状态；先读代码、查 profile/能力、看现有测试或用实际命令验证。
- 新功能优先放在 `modules/` 里实现可测试逻辑，UI 页面只做输入收集、按钮状态、提示文案和调用 `CommandSpec`。
- 新页面必须通过 `MainWindow._build_page_specs()` 懒加载，不要在启动阶段导入重模块；`tests/smoke_main_window.py` 会检查这一点。
- 当前设备必须来自 `DeviceBar.current_profile()`，不要在页面里复制默认账号、密码、IP 或设备能力。
- 设备默认值、能力和固定差异放在 `core/profiles.py` 或对应后端模块常量中，不要散落到 UI 控件里。
- 远程命令优先返回 `CommandSpec`，并通过 `CommandPage.set_command()`/`ProcessRunner.run()` 执行。
- 页面内短轮询或独立异步任务优先使用 `ProcessSlot`；页面切换设备、关闭页面或关闭主窗口时必须停止这些进程。
- 共享行为先写成通用 helper，再在 profile/capability/adapter 边界做特化。

## 设备兼容

- 不要根据页面名称或物理型号猜测能力，必须通过 `ProductProfile.key`、`ProductProfile.capabilities` 或适配 helper 判断。
- 已有适配 helper 包括 `l1_control_profile()`、`l2_control_profile()`、`l2_s100_profile()`、`robot_sdk_control_profile()` 等，优先复用。
- 当前 profile 可能被操作员改写 IP、用户名和密码；保留 base profile 的 `key`、`capabilities`、ROS 参数和跳板配置。
- 当一个 UI 动作实际打到另一个控制端点时，日志或状态必须同时表达当前设备和实际目标端点。例如 L2 S100 遥控映射到 L2 3588，中狗 S100/NX 控制映射到中狗 3588。
- 支持多设备的流程使用通用标签；只有在命令目标、安全提示或不支持说明中才写 L1、L2、S100、3588、NX、ZG、ZGNX 等具体名称。
- 不支持的设备要禁用或隐藏危险控件，并给出短说明，说明支持的设备族或缺少的能力。

## 远程命令与安全

- SSH、SCP、rsync、ROS、OTA、线刷、服务启停、重启、删除文件和运动控制都视为高风险操作。
- 只读探测和会修改远端状态的动作要在代码和 UI 上分开。
- 会移动设备、删除文件、刷机、重启、启停服务、上传替换资源、修改配置的动作必须设置 `CommandSpec.dangerous=True`，复用统一确认框。
- OTA/线刷进入不可停止阶段时必须继续使用 `[DOG_REMOTE_STAGE] upgrade_locked` 机制，让 `ProcessRunner` 锁定停止按钮。
- 并发任务必须显式选择 `concurrency` 和必要的 `locks`；长期运行或互斥资源不要默认并发。
- 命令拼接必须使用 `quote()`、`ssh_command()`、`rsync_pull_command()`、`rsync_push_command()`、`sshpass_file()` 等现有封装。
- 不要在 UI 日志里输出密码、sshpass 明文、完整凭据命令或大段无用传输进度；使用 `display_command` 给操作员看安全摘要。
- ROS 环境优先使用 `remote_env(profile)` 或业务模块已有环境 helper，保持 `ROS_DOMAIN_ID`、`RMW_IMPLEMENTATION` 和日志目录一致。
- 涉及 sudo 的远程操作复用现有 sudo helper，不要新增明文密码拼接方式。

## 文件、录包和路径操作

- 远端路径必须先清洗或校验，优先复用 `clean_remote_path()`、`validate_name()`、`validate_delete_path()`、`is_safe_remote_bag_path()` 等现有函数。
- 删除、移动、覆盖、保存文本必须在后端模块做硬校验，不能只依赖 UI 弹窗。
- 文件管理删除只允许 Home、`/tmp/`、地图数据等授权范围；不要扩大系统目录白名单。
- 录包路径、bag 命名、存储格式要通过 `bag_recording_plan.py`、`bag_names.py` 和 profile 的 `bag_storage` 决定。
- 新增远端输出解析时优先使用明确 marker 或结构化 JSON，避免靠脆弱的自由文本截取。

## UI 行为

- 页面设计以运维效率为主：清楚的目标设备、目标端点、当前状态、可执行动作、禁用原因和失败原因。
- 设备切换时，页面必须停止当前页面的异步进程，重置 profile 相关默认路径，并刷新支持状态。
- 长任务要展示阶段变化或状态，不要刷屏；日志中的噪声应进入 `log_filter.py` 统一过滤。
- 按钮启用状态必须跟能力、连接状态、任务运行状态和危险阶段一致。
- 不要在可复用控件里写死某个型号文案，除非控件本身就是型号专用。
- 状态文本要面向操作员，优先给下一步排查方向，而不是只显示 `failed` 或返回码。

## 运行中工具进程

- 修改源码后不要杀掉、重启或重新拉起正在运行的 Dog Remote Tool，除非用户明确要求。
- 如果变更需要重启 GUI 才生效，说明这一点，让用户决定何时关闭或重启。
- 检查是否已有工具运行时，只匹配真实入口，不要匹配包含字符串的 shell 命令。可参考 `启动.sh` 中对 `python3 -m dog_remote_tool` 的进程匹配方式。
- 关闭主窗口时要确保新增页面实现自己的清理逻辑，并被 `MainWindow.closeEvent()` 调用到。

## 验证方式

- 默认使用非破坏性验证，不连接实机、不刷机、不重启远端设备。
- 当本地检查无法确认设备行为，且目标设备、账号和风险范围明确时，可以连接远端设备做必要验证；优先执行只读探测、状态查询和小范围命令。
- 连接远端设备前先说明目标 profile、实际 endpoint、要执行的命令类型和风险；涉及刷机、重启、删除、服务启停、配置写入或运动控制时，必须等用户明确同意。
- 常用检查：

  ```bash
  PYTHONPATH=src python3 -m py_compile $(find src tests -name '*.py')
  QT_QPA_PLATFORM=offscreen PYTHONPATH=src python3 tests/smoke_main_window.py
  PYTHONPATH=src pytest tests/<targeted_test_file>.py
  ```

- 改动命令生成、解析、路径安全、能力门控、包识别、协议适配时，要跑对应测试或补充测试。
- GUI 结构、页面注册、启动导入相关改动必须跑 offscreen smoke。
- 不要把真实设备操作当作默认验证；只有用户明确指定目标设备和操作时才执行。
- 如果某个验证无法运行，要说明具体命令和原因。

## 测试要求

- 业务逻辑优先写纯函数测试，避免依赖真实机器人、网络、用户 Home 目录和系统工具。
- 对 bug 修复补上能复现旧问题的回归用例。
- 页面测试只覆盖轻量行为、状态变化、命令选择和 signal/slot 结果，不要启动真实长任务。
- 命令生成测试要断言 `title`、`display_command`、`dangerous`、`concurrency`、`locks` 和关键命令片段。
- 新增 profile、capability 或适配 helper 时，同步覆盖相关支持/不支持状态。

## 资源与发布

- 发布包依赖的脚本、工具和配置必须放入 `resources/`，并确认 `build/build_release.sh` 会携带它们。
- `resources/remote_access/`、`resources/ota/packages/`、`resources/record_bag/` 已是现有资源入口，新资源优先归到对应目录。
- 本地开发路径只能作为默认值出现在合适的后端模块中，并尽量提供环境变量覆盖；不要在 UI 里硬编码开发机路径。
- 修改源码不会自动更新 `release/` 下的 `.run`、`.desktop` 或启动脚本；打包是单独动作。
- 保持脚本可执行权限和发布脚本的 `set -euo pipefail` 风格。

## 变更卫生

- 日常验证以源码检查和测试命令为准，不要把版本控制命令作为必须步骤。
- 不要编辑生成物：`__pycache__/`、`.pytest_cache/`、`.build/`、解压缓存、日志、临时回传文件等。
- 不要改动无关文件；如果发现用户已有改动，基于当前文件继续工作，不要回退。
- 修改完成后用实际读文件或目标测试确认结果，再总结改了什么、验证了什么、哪些需要重启 GUI 才生效。
