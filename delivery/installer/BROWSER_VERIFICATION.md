# D2 浏览器制品验证记录（2026-09-02）

## 结论

Playwright 1.61.0 与 Playwright/Patchright 1.62.x 在 Windows 11 x64 所需的 2 套 Chromium、2 套 headless shell、FFmpeg 1011 和 Winldd 1007 已具备固定官方 URL、唯一交付文件名、大小和 SHA256。6 个归档只保留在系统临时目录，尚未复制到候选包，也不代表安装器已经完成。

## 锁定制品

| 制品 | 文件名 | 大小 | SHA256 |
|---|---|---:|---|
| Chromium 1228 | `playwright-chromium-1228-win64.zip` | 192,511,857 | `ebc0c2b75e2ea98151a7f18ff47037bfcbab44a8660e79b9ffa6520f9b7607ab` |
| Chromium headless shell 1228 | `playwright-chromium-headless-shell-1228-win64.zip` | 119,099,822 | `5cfda0c763aa6a867ce2efad0c467e3220e9c5c01c4cba02fd57afe49ede5457` |
| Chromium 1234 | `playwright-chromium-1234-win64.zip` | 201,068,834 | `045621e45a9dd27002c7fc1d8e10fe9f5f71f4cadbf44ec6f397f56f0179725c` |
| Chromium headless shell 1234 | `playwright-chromium-headless-shell-1234-win64.zip` | 120,106,945 | `46cc69ef55ba29268ffe32dda4192a9d2165be42c3f4e923241153d519493aea` |
| FFmpeg 1011 | `playwright-ffmpeg-1011-win64.zip` | 1,411,741 | `8d08827c019ad36e7b9d49d3648447d884534cb2acf200e71c715f6dd834cc50` |
| Winldd 1007 | `playwright-winldd-1007-win64.zip` | 128,684 | `0069f0d11d4ad6df068a068c003d22fe7dbec192a47bba64b2e115e9c8ce41d8` |

## 来源与重复下载

- 修订号和浏览器版本来自 [Playwright 1.61.0 browsers.json](https://github.com/microsoft/playwright/blob/v1.61.0/packages/playwright-core/browsers.json) 与 [Playwright 1.62.0 browsers.json](https://github.com/microsoft/playwright/blob/v1.62.0/packages/playwright-core/browsers.json)。
- 下载使用 `runtime-manifest.json` 中的 Playwright 官方 CDN URL。Chromium 最终响应来自 Chrome for Testing 官方存储，FFmpeg 与 Winldd 最终响应来自 Microsoft 的 Playwright 下载服务。
- 每个 URL 在两个独立临时目录各下载一次；同一制品两次的字节数与 SHA256 完全一致。

## 归档审计

- 6 个 ZIP 均通过全量 CRC 检查，未发现重复路径、绝对路径、盘符路径、反斜杠路径、`..` 路径穿越或符号链接。
- 已确认每个归档包含预期入口：`chrome-win64/chrome.exe`、`chrome-headless-shell-win64/chrome-headless-shell.exe`、`ffmpeg-win64.exe` 或 `PrintDeps.exe`。
- 归档条目数依次为完整 Chromium 308、headless shell 290、FFmpeg 2、Winldd 1；检查过程未解压或执行浏览器程序。
- 6 个预期可执行文件的 Authenticode 状态均为 `NotSigned`。因此不能把这些上游文件描述为“已签名”；当前可信边界是官方来源、重复下载一致和本地 SHA256 固定，最终安装器仍需独立完成签名策略与干净 Win11 验收。

## 边界

本轮没有安装浏览器、没有写入候选包、没有使用 API Key，也没有访问、删除、暂存或打包 `.codex_tmp/`、本机 `requirements/` 或 `data/`。
