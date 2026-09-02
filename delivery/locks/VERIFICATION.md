# D1 依赖锁验证记录（2026-08-30）

## 结论

D1 已完成：Windows 11 x64 / CPython 3.13.9 的六个独立依赖集合已生成带 SHA256 的锁，并在仓库外的全新虚拟环境中完成严格同步、依赖检查和最小导入验证。当前 Web 主入口在隔离测试环境中成功绑定回环地址并返回 HTTP 200；短路径跟踪文件快照中全量回归为 `370 passed, 7 warnings`。

本记录不表示已制作安装器或候选包。剩余外部适配器 wheel、安装器、交付白名单、合并、标签和发布均尚未执行。

## 固定工具与解析边界

- 基础解释器：CPython 3.13.9，64 位，`win32` / `win-amd64`。
- 基础 `python.exe` SHA256：`7679E53FA969789309E81FDAD0D52B8CDA5F83C9ABF7CB31A3C58BF24B31E264`。
- 锁定工具：`uv 0.10.8 (c021be36a 2026-03-03)`。
- `uv.exe` SHA256：`067CF5D81A2DC006C1C76FA160B4DA96A35BC80900C22FAED7ACFC52510FCDF5`。
- 包来源：公开 PyPI，禁用 keyring、额外索引、VCS、直接 URL 和本地路径来源。
- 上传截止时间：`2026-08-29T15:59:59Z`，即北京时间 2026-08-29 23:59:59。
- 通常只允许 wheel；已记录的官方源码包例外为 `jieba==0.42.1` 和 `qrcode-terminal==0.8`。D2 实物复核后，`bilibili-api-python==17.4.2` 改用 PyPI 官方 wheel。

## 锁文件

| 隔离运行时 | 包数 | 锁文件 SHA256 |
|---|---:|---|
| 主程序 | 23 | `6563e6bffab7b96a7f4a3dd538626aa691af0a34c649eabe3041980b6e536d6f` |
| 测试 | 29 | `7c794c8f11dccb06645c6c29be0a4bda0dcac0fe0bade767bd5011193fdc50f3` |
| Scrapling | 22 | `63b8ece936586663d224c959b6a41efdbd5f1f5a592e439dbbf3853cbf628480` |
| Bilibili CLI 运行依赖 | 35 | `3011e71d1d4e6e80fa979526806907a6937c7f89dfd47ee16675f481a818e079` |
| newspaper4k 运行依赖 | 22 | `176e8d005c8310df02cdb9b3c179c71a4ceae807d6d3367d0711bfabe3121a6a` |
| aiotieba 运行依赖 | 17 | `dfbcc13c5bc6e109bd399b110da3d3715211494d5466bf414f24ad419b961d43` |

`generated/SHA256SUMS.txt` 已逐项复算通过。使用相同输入、平台、截止时间和工具重新生成后，六个 SHA256 全部不变。

## 隔离重建与依赖检查

- 六个验证环境均以 `venv --copies --without-pip` 新建，`include-system-site-packages=false`。
- 每个环境均以 `--require-hashes --strict --link-mode copy --no-sources` 从对应锁同步。
- 六个环境的 `uv pip check` 和最小导入 smoke 全部通过。
- 初次 D1 验证曾强制从 sdist 构建 `bilibili-api-python`，较长临时路径触发 Windows 旧式路径长度问题；D2 实物复核证明官方 wheel 的运行依赖和程序文件完整，因此当前策略已改为官方 wheel。验证脚本仍将短路径要求作为旧式源码构建的前置保护。
- Jieba 和 WMI 在 Python 3.13 导入时产生上游 `SyntaxWarning`，未形成依赖冲突或导入失败。
- 两个源码发布的 PEP 517 隔离构建工具不属于运行时哈希锁；D2 必须预构建 wheel 并记录 wheel SHA256，终端用户环境不得现场构建。

## 跟踪文件快照与测试

- 测试时 Git 索引共 100 个跟踪路径；复制当前工作树中存在的 98 个普通文件，跳过用户已授权删除的两个传统 GUI 文件。
- `data/`、`.codex_tmp/`、`requirements/` 的跟踪文件数均为 0；快照硬排除这三个目录，且不存在 Git symlink 或 submodule。
- 第一次较长快照路径运行得到 `367 passed, 3 failed`；三项均为历史归档测试的 WinError 206 路径过长，并非断言或业务逻辑失败。
- 从相同工作树重建 48 字符的短路径快照后，全量结果为 `370 passed, 7 warnings in 14.99s`。
- 七条 warning 均来自 Jieba 在 Python 3.13 下的无效转义序列提示。

父进程只检查到真实 `BAIDU_QIANFAN_API_KEY` 的“存在”状态，没有读取或输出其值。回归子进程改用非真实但非空的占位 Key，以覆盖“环境存在 Key”的隔离路径，同时避免真实付费凭据进入测试；并使用受限执行环境、失效代理和空浏览器目录作为附加围栏。历史上真实百度 Key 保留时的 `370 passed, 2 warnings` 继续作为 `b7a95a7` 基线证据。

## 启动 smoke

- 使用隔离测试锁环境和短路径快照启动 `web_app.py --host 127.0.0.1 --no-browser`。
- 服务只绑定回环地址，主页返回 HTTP 200，响应正文 18130 字节。
- 验证完成后只停止本次创建的临时进程；未打开浏览器，未写入当前工作区数据目录。

## 后续边界

- `external-sources.json` 已固定三个实际启用外部适配器的公开仓库、完整 commit、版本和许可证；D2 才构建并记录 wheel SHA256。
- B站运行依赖 `bilibili-api-python==17.4.2` 的安装元数据为 `GPL-3.0-or-later`；D4 必须完成许可证和分发义务审查，审查前不得正式外发该子运行时。
- `browser-runtimes.json` 已固定 Playwright/Patchright 包版本、`browsers.json` 哈希及 Chromium、headless shell、FFmpeg、Winldd 修订号；D2 已在安装器运行时清单中补全 6 个归档的官方来源、大小和 SHA256。
- 未修改根目录旧 `requirements.txt`；安装器必须显式使用 `delivery/locks/generated/`，不能回退到旧清单。
- `.codex_tmp/`、本机 `requirements/` 和 `data/` 未删除、覆盖、暂存或纳入任何产物。
