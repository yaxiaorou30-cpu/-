# D2 Windows 在线安装器原型

本目录当前只建立了安装器合同，还不是安装包，也不会修改本机 Python、PATH、注册表或 API Key。合同的作用是先把后续实现不得突破的边界变成可执行检查。

## 已固定的边界

- 仅支持 Windows 11 x64，按当前用户安装到 `%LOCALAPPDATA%\Programs\AI-Opinion-Monitor`，不申请管理员权限。
- 安装器自动准备应用私有 CPython 3.13.9 和隔离虚拟环境；不查找或回退到系统 Python，不修改 PATH，不注册 Python。
- 新加载器只启动浏览器版，绑定 `127.0.0.1`，从 8765 开始检查程序实际选中的端口，通过健康检查后才打开浏览器。
- 安装、修复、升级和卸载均保留 `{app}\data`、`{app}\output` 与 `%LOCALAPPDATA%\AI-Opinion-Monitor\sensitive`；D2 不提供删除这些数据的选项。
- 安装器不索取、不保存、不打印 API Key。教程只说明如何设置 `BAIDU_QIANFAN_API_KEY` 和 `DEEPSEEK_API_KEY` 的 Windows 用户环境变量。
- 工作区内容只能按白名单复制；`.codex_tmp/`、本机 `requirements/`、当前 `data/`、旧启动器及整个本机 `opensource_candidates/` 不得作为来源复制。
- Bilibili 子运行时仅可用于内部原型，完成 D4 的 GPL 分发审查前不得进入正式外发安装器。

## 本机验证

Windows PowerShell 5.1 或 PowerShell 7 均可运行：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\delivery\installer\tests\verify-installer-contract.ps1
```

预期输出：

```text
INSTALLER_CONTRACT=PASS
```

只读检查当前制品计划：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\delivery\installer\tests\verify-artifact-contract.ps1 -Mode PlanOnly
```

当前预期为 `PENDING_ARTIFACTS=14`、`NETWORK_ACTIONS=0`、`FILESYSTEM_MUTATIONS=0`。这 14 项是 6 个待预构建 wheel、5 个待锁定浏览器压缩包和 3 个待锁定工具归档。

严格发布门禁当前必须失败：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\delivery\installer\tests\verify-artifact-contract.ps1 -Mode ReleaseReady
```

只有所有制品都具备不可变来源、文件名和 SHA256 后，`ReleaseReady` 才允许通过。

## 官方依据

- uv 的 `python install --install-dir --no-bin --no-registry` 支持把 Python 放入指定私有目录且不写 Windows Python 注册信息：[uv 命令参考](https://docs.astral.sh/uv/reference/cli/#uv-python-install)。
- uv 默认面向虚拟环境，并支持用明确的解释器路径安装依赖：[uv 与 pip 的兼容说明](https://docs.astral.sh/uv/pip/compatibility/#virtual-environments-by-default)。
- Playwright 要求 Python 包版本与浏览器二进制配套，并支持用 `PLAYWRIGHT_BROWSERS_PATH` 指定私有浏览器目录：[Playwright 浏览器管理](https://playwright.dev/python/docs/browsers#managing-browser-binaries)。
- Inno Setup 的 `PrivilegesRequired=lowest` 使用非管理员安装模式；开始菜单和卸载信息归当前用户：[Inno Setup 非管理员模式](https://jrsoftware.org/ishelp/topic_admininstallmode.htm)。
- Inno Setup 明确提醒卸载时不要无警告删除用户放在应用目录中的数据：[Inno Setup UninstallDelete](https://jrsoftware.org/ishelp/topic_uninstalldeletesection.htm)。
- 当前原型计划固定 Inno Setup 7.1.0 x64；其官方下载页同时提供版本、发布日期和签名验证入口：[Inno Setup 下载](https://jrsoftware.org/isdl.php)。商业使用许可是否适用继续作为 D4 审查项。

## 尚未完成

- 锁定 Python、uv、预构建 wheel 和浏览器压缩包的下载 URL、文件大小与 SHA256。
- 实现只读 `PlanOnly`、实际准备私有运行时、加载器和 Inno Setup 定义。
- 验证安装、重复启动、定向停止、修复、覆盖升级、数据保留和卸载。
- 完成白名单、敏感扫描、许可证审查、干净 Win11 验收和用户批准门禁。

以上未完成项全部完成前，本目录不能被描述为“可发布安装包”。
