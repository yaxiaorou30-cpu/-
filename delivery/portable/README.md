# Windows 11 自包含便携交付

状态：内部技术原型已通过本机搬迁与启停验证；尚未形成内部验收候选，更不是可外发成品。

## 已接受的交付决定

2026-09-05，交付路线由“开发传统安装器”改为“交付一个自包含的软件目录”。甲方最终只需把目录解压到普通可写位置，双击 `启动软件.cmd`；不需要安装或配置 Python，不需要运行 `pip`，也不需要管理员权限。程序业务功能仍需要访问已支持的网站和 API，但甲方电脑不需要在首次启动时从 GitHub、PyPI 或浏览器 CDN 下载运行依赖。

这项决定取代原先的 Inno Setup 在线安装器路线。`delivery/installer/` 中已经锁定的 Python、wheel 和浏览器制品继续作为可复现输入与校验证据使用，但其在线安装语义不是便携交付合同。

## 预期目录形态

```text
AI-Opinion-Monitor/
├─ 启动软件.cmd
├─ 停止软件.cmd
├─ web_app.py、src/、web/、config/
├─ .runtime/
│  ├─ python/              私有 CPython 3.13.9
│  ├─ browsers/            已锁定的 Chromium/FFmpeg/Winldd
│  └─ launcher/            启停和 Python 引导文件
├─ .venv/                  主程序依赖
├─ .scrapling-venv/        Scrapling 隔离依赖
├─ opensource_candidates/  三个固定版本的隔离适配器运行时
├─ data/                   候选中只能是空目录或明确允许的初始数据
├─ output/                 候选中只能是空目录
└─ THIRD_PARTY_NOTICES.md
```

组装来源必须使用 Git 跟踪文件白名单和已经锁定哈希的外部制品。工作区现有 `.codex_tmp/`、未跟踪的 `requirements/` 和本机 `data/` 既不能被读取为组装输入，也不能进入交付目录。

## 加载器边界

- 用户入口固定调用 Windows 11 自带的 Windows PowerShell 5.1，再启动随软件附带且通过 SHA256 校验的 `pythonw.exe`；没有系统 Python 或 PATH 回退。
- 启动前修复五个隔离环境的搬迁路径，并校验各环境的 Python 启动文件。
- 服务只绑定 `127.0.0.1`，健康检查确认是本程序后才打开浏览器。
- 状态、日志和敏感运行数据默认写入 `%LOCALAPPDATA%\AI-Opinion-Monitor`，不写进便携程序目录。`-StateRoot` 只供临时目录内的自动验收使用。
- 停止时同时核对产品路径、可执行文件路径、PID 和进程启动时间；先通过停止令牌进入程序已有的清理流程，超时后再次核验根进程，再终止该根进程的进程树。状态损坏、跨副本或身份不符时拒绝误杀。
- API Key 只由甲方按教程设置为 Windows 用户环境变量。加载器不索取、不序列化、不打印 Key；业务子进程会继承这些变量，这是用户已接受的边界。

## 当前验证证据

- 已在系统临时目录手工组装完整私有 Python、五套依赖环境和两套已锁定浏览器，规模约 2.01 GiB。
- 整个目录复制到另一个路径后，五套环境导入、aiotieba 原生扩展、Playwright、Patchright 和 Web 应用回环健康检查均通过。
- `启动软件.cmd`、重复启动复用、`停止软件.cmd` 已在 Windows PowerShell 5.1 下通过；测试还覆盖 `READY` 状态、健康 JSON 与监听 PID 绑定、伪造 PID、跨副本状态、停止请求路径的子目录与无效文件名两类越界哨兵、优雅停止、停止脚本强制停止分支、越界状态目录和状态写入失败后的根进程回收。
- 非响应测试运行器会建立“父进程 → 子进程 → 孙进程”，分别记录 PID 和启动时间，并故意忽略停止令牌；测试在启动失败清理后按记录身份确认三者均已退出。该证据不表示加载器会逐个核验所有后代，也不承诺能够管理主动脱离父进程的任意第三方进程。
- 测试分别注入无效 `PYTHONHOME` 和会在解释器启动阶段退出的 `PYTHONPATH`，并验证私有 Python 不受影响；3 个合成 Key 和 11 个启动器环境变量均在测试后恢复。
- 测试开始前会用合成 Key 替换当前进程中的真实值，结束后恢复，因此测试子进程不接收真实 Key。健康请求目标仅为 `127.0.0.1`，这不等同于宣称业务功能离线。
- 普通临时路径以及中文加空格的目录联接路径均已通过源码集成测试；真实中文物理目录仍须在最终候选中复验。

在已有内部原型上复验加载器：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\delivery\portable\tests\verify-portable-launcher.ps1 -ProductRoot "<系统临时目录中的内部原型>"
```

预期输出包含：

```text
SOURCE_CMD_INTEGRATION=PASS
WINDOWS_POWERSHELL=5.1
GRACEFUL_SERVER_EXIT=PASS
PYTHONHOME_POISON_IGNORED=PASS
PYTHONPATH_POISON_IGNORED=PASS
UNSAFE_STOP_FILE_REFUSALS=2
FORCED_STOP_PATH=PASS
ORPHANED_SERVER_ROOTS_AFTER_STATE_WRITE_FAILURE=0
FAILED_START_PROCESS_TREE_CLEANUP=PASS
```

该脚本会把仓库中的加载器源码覆盖到带有内部原型标记的目录，因此结果只证明当前源码集成，不代替未来候选包的只读验收。

## 仍未完成

- 把手工组装步骤固化为仅写入新临时目录、可重复执行的脚本。
- 增加便携目录白名单、布局和敏感路径合同。当前内部原型扫描到 8 个 `direct_url.json` 含本地 `file:///` 构建路径；这些元数据必须在候选生成方式中消除，并由门禁阻止复发。
- 确认候选中没有构建机绝对路径、真实凭据、本机会话、历史数据或本机 `data/` 内容。
- 完成两项分发许可门禁：Bilibili API 的 GPL 传递依赖，以及 newspaper4k 内嵌 Apache-2.0 资源的许可证文本义务。
- 编写甲方的解压启动、Windows 环境变量、首次账号、平台登录、日常操作、备份和排障教程。
- 在最终候选的真实中文加空格物理目录中复验，并在存在活动浏览器登录会话时确认优雅关闭不会遗留受管浏览器进程。
- 在干净的 Windows 11 普通用户环境验收，之后再由用户逐项批准候选包、版本、标签和发布。

在以上事项完成前，不得把任何临时目录称为“交付包”，也不得压缩、上传或发送。
