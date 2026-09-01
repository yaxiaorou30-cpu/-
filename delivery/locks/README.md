# Windows 交付依赖锁

本目录只服务于交付构建和交付前验证，不改变根目录现有开发依赖声明。

锁定边界：

- `main`：Web 主程序运行时；
- `test`：主程序运行时加 `pytest`，仅用于回归验证；
- `scrapling`：独立的 Scrapling 运行时，不与主程序混装。
- `bilibili-cli-runtime`：B站 CLI 固定源码 wheel 之外的独立运行依赖；
- `newspaper4k-runtime`：newspaper4k 固定源码 wheel 之外的独立运行依赖；
- `aiotieba-runtime`：aiotieba 固定源码 wheel 之外的独立运行依赖。

目标固定为 Windows 11 x64、CPython 3.13.9。锁文件包含 SHA256，且忽略 2026-08-29 23:59:59（北京时间）之后上传的文件。通常只接受 PyPI 二进制分发包，只有 `jieba==0.42.1`、`bilibili-api-python==17.4.2` 及其纯 Python 传递依赖 `qrcode-terminal` 使用带哈希的官方源码包：Jieba 没有可用 wheel；Bilibili API 较旧可用 wheel 的发布元数据缺少实际运行依赖，因此固定为当前已验证的 17.4.2 源码发布。PEP 517 隔离构建工具不属于运行时锁；D2 必须预构建这些 wheel、记录成品 SHA256，再放入软件私有运行时，不能让终端用户现场编译。生成工具固定为 `uv 0.10.8`，脚本同时校验 `uv.exe` 的 SHA256。

在一个 `include-system-site-packages = false` 的临时虚拟环境中运行：

```powershell
powershell -ExecutionPolicy Bypass -File .\delivery\locks\compile-locks.ps1 -PythonPath "<临时虚拟环境>\Scripts\python.exe" -CacheDir "<临时缓存目录>"
```

生成结果位于 `generated/`：

- `generated/main-win11-x64-py313.lock.txt`
- `generated/test-win11-x64-py313.lock.txt`
- `generated/scrapling-win11-x64-py313.lock.txt`
- `generated/bilibili-cli-runtime-win11-x64-py313.lock.txt`
- `generated/newspaper4k-runtime-win11-x64-py313.lock.txt`
- `generated/aiotieba-runtime-win11-x64-py313.lock.txt`
- `generated/SHA256SUMS.txt`

脚本先在同一目录下的随机暂存目录生成全部文件；只有六个锁和校验清单都成功后，才整体替换 `generated/`，防止失败时混用新旧结果。

可在仓库外的可丢弃目录重建六个环境并校验哈希、依赖完整性和最小导入：

```powershell
powershell -ExecutionPolicy Bypass -File .\delivery\locks\verify-locks.ps1 -BasePythonPath "<CPython 3.13.9 x64>\python.exe" -WorkRoot "<可丢弃目录>" -CacheDir "<临时缓存目录>"
```

验证脚本不删除运行目录，并拒绝把运行目录或缓存放进仓库；每次运行使用新的随机子目录。
由于 `bilibili-api-python` 的旧式构建目录很深，`WorkRoot` 和 `CacheDir` 的绝对路径都必须不超过 80 个字符，避免触发 Windows 传统路径长度限制。

三个外部适配器的公开源码地址、精确提交、版本和许可证记录在 `external-sources.json`。该清单故意不引用本机 `opensource_candidates/` 绝对路径；D2 从精确提交构建 wheel 后再填写 wheel 文件名与 SHA256，不复制整个本机源码目录。

`bilibili-api-python==17.4.2` 的本地安装元数据声明为 `GPL-3.0-or-later`，已在 `external-sources.json` 标记为 D4 分发审查项。未完成许可证义务核对前，不得把 B站子运行时作为正式外发产物。

Playwright/Patchright 的 Python 包版本、内置 `browsers.json` 哈希以及 Chromium、headless shell、FFmpeg 修订号记录在 `browser-runtimes.json`。浏览器压缩包尚未下载或打包；其下载地址和 SHA256 留到 D2 安装器原型阶段固定。

Playwright、Patchright 浏览器二进制不是 Python wheel，须在后续交付构建阶段按锁定包内的浏览器修订号另行固定和校验；它们不由本目录的 Python 哈希锁覆盖。

`numpy` 和 `snownlp` 未出现在当前跟踪源码或测试中，因此没有进入新的交付运行时输入；根目录原有 `requirements.txt` 保持不变。静态零引用、隔离环境全量回归和启动 smoke 共同作为这一边界的验证证据，但不把单元测试单独视为现场功能证明。
