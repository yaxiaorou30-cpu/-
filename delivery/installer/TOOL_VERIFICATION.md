# D2 工具归档核验记录（2026-09-01）

## 结论

以下三个官方归档已在新建系统临时目录中下载并复算 SHA256；临时目录不属于仓库，也不作为交付来源。Inno Setup 安装程序只做文件和签名检查，没有运行或安装。

| 用途 | 版本 | 文件大小 | SHA256 |
|---|---|---:|---|
| 私有 CPython | 3.13.9 Windows x64 | 21638637 | `f4c22b31ddbf8d7824cbcba2d8707621c2c8fab1fb6d2c1810c2bb0304d8e9a8` |
| uv | 0.10.8 Windows x64 | 22159808 | `2e70ecd22196cbd9d14eefb700814bcafc5b75a0d8275b52e8402e5fe256d928` |
| Inno Setup | 7.1.0 x64 | 14304168 | `0362a383ed217d4c4239b5933866dd96d3eb2102737da92f80f6057a4b40df2f` |

精确文件名、不可变下载 URL、sidecar/签名文件哈希和内部文件哈希记录在 `runtime-manifest.json`。

## 内部验证

- uv ZIP 中的 `uv.exe`：`uv 0.10.8 (c021be36a 2026-03-03)`；SHA256 为 `067CF5D81A2DC006C1C76FA160B4DA96A35BC80900C22FAED7ACFC52510FCDF5`。
- uv 官方 `.sha256` sidecar 的文件哈希和内容均匹配；其文件名前的 `*` 是标准 `sha256sum` 二进制模式标记。
- CPython 归档解压后探针为 `3.13.9|64|CPython|win32|win-amd64`；内部 `python.exe` SHA256 为 `30557F6B49FC4B6574CA3EF91EDB8D148CFC989DD75C846F5639B76DB800E7E2`。
- Inno Setup 安装程序的 Authenticode 状态为 `Valid`；签名主体为 `Pyrsys B.V.`，证书指纹为 `E0AB19C8D38CBF9C44709925122A7A02F8C70CB7`。

## 官方来源

- [uv 0.10.8 Release](https://github.com/astral-sh/uv/releases/tag/0.10.8)
- [python-build-standalone 20251120 Release](https://github.com/astral-sh/python-build-standalone/releases/tag/20251120)
- [Inno Setup 7.1.0 Release](https://github.com/jrsoftware/issrc/releases/tag/is-7_1_0)
- [Inno Setup 下载验证说明](https://jrsoftware.org/isdl-verify.php)

## 状态更新（2026-09-05）

- 本文件最初记录的“wheel 和浏览器尚未锁定”是 2026-09-01 的历史快照，现已由 `WHEEL_VERIFICATION.md`、`BROWSER_VERIFICATION.md` 和当前 `runtime-manifest.json` 完成更新；只读合同结果为 `PENDING_ARTIFACTS=0`。
- 用户已改选自包含便携目录，Inno Setup 不再是当前交付链输入；其归档与签名证据保留，但不会因此进入候选。
- 当前仍有 `UNAPPROVED_DISTRIBUTION_GATES=2`：Bilibili API 的 GPL 传递依赖审查，以及 newspaper4k 内嵌 Apache-2.0 资源的许可证文本义务。
- 尚未生成、压缩、发送或发布任何正式候选。当前技术原型状态见 `../portable/README.md`。
