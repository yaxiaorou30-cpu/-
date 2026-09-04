# D2 wheel 制品验证记录（更新至 2026-09-04）

## 结论

首批 5 个运行时 wheel 已具备固定来源、文件名、大小和 SHA256。其中 Jieba 与 qrcode-terminal 由官方 PyPI sdist 在本机构建，newspaper4k 由固定 Git 提交在本机构建，Bilibili API 直接采用 PyPI 官方 wheel，aiotieba 由固定 Git 提交在 GitHub Actions 的 Windows 环境构建。它们已经通过结构审计和完整依赖环境导入验证，但当前仍只是 D2 内部制品证据，不是候选安装包，也不代表允许发布。

## 选定制品

| 包 | 来源 | 文件名 | 大小 | SHA256 |
|---|---|---|---:|---|
| Jieba 0.42.1 | [PyPI sdist](https://files.pythonhosted.org/packages/c6/cb/18eeb235f833b726522d7ebed54f2278ce28ba9438e3135ab0278d9792a2/jieba-0.42.1.tar.gz) | `jieba-0.42.1-py3-none-any.whl` | 19,314,527 | `6db280488a8989695b450928a302fd81a6e35a46449fd58c54f2ff5ae06ce866` |
| qrcode-terminal 0.8 | [PyPI sdist](https://files.pythonhosted.org/packages/96/62/2422c088b7219db9f78c912418254db9896d1b20ab15e83aae2821419a65/qrcode-terminal-0.8.tar.gz) | `qrcode_terminal-0.8-py3-none-any.whl` | 2,661 | `8cd9b4e146051633b39b734d692c2f1cf4d6d85e0694e093546416c63aca2714` |
| bilibili-api-python 17.4.2 | [PyPI wheel](https://files.pythonhosted.org/packages/8e/41/c12f4c52cecd6ca6c4bee49a8949ed3df3561e5dd12b891aba96dcdc4502/bilibili_api_python-17.4.2-py3-none-any.whl) | `bilibili_api_python-17.4.2-py3-none-any.whl` | 387,324 | `91e002b2e0bcd3eb50239e35ceb849133b574f407a92a06636e1de1031b6d09d` |
| aiotieba 4.7.2a8 | [固定提交的 GitHub Actions 构建](https://github.com/yaxiaorou30-cpu/-/actions/runs/33826036726) | `aiotieba-4.7.2a8-cp313-cp313-win_amd64.whl` | 292,310 | `4d665c3b54116034505bd0baccbf149d90d89ea31242bc397d3d10bc7ae4ba42` |
| newspaper4k 0.9.6 | 固定 Git 提交 `b53a81fc01ff54601faaeae68d6b4a6d2f18efcb` | `newspaper4k-0.9.6-py3-none-any.whl` | 319,011 | `c82b9fc9d3686d776dc016bfad0ee0671ddcce13b5e7ed83c69eb1e740747168` |

Jieba sdist 为 19,214,172 字节，SHA256 为 `055ca12f62674fafed09427f176506079bc135638a14e23e25be909131928db2`。qrcode-terminal sdist 为 1,666 字节，SHA256 为 `1e2b69e662b9346e98dd95983033e9d43cff0643d8afda12605f515428e666c0`。

## 本地构建边界

- 构建解释器固定为 CPython 3.13.9 x64，`python.exe` SHA256 为 `30557F6B49FC4B6574CA3EF91EDB8D148CFC989DD75C846F5639B76DB800E7E2`。
- 构建工具固定为 uv 0.10.8，`uv.exe` SHA256 为 `067CF5D81A2DC006C1C76FA160B4DA96A35BC80900C22FAED7ACFC52510FCDF5`。
- 构建输入 SHA256 为 `d81a0bb625ea04dd183867f8193568633db73d37a94fd92b0bd8cb0db8f8d694`；构建依赖锁 SHA256 为 `ab9bb7dadd6e17eb89ed9b1a8b124da64009028fa7589c0f55e15f404c5e6598`。
- 两个独立临时虚拟环境只用带哈希的二进制构建依赖；目标 wheel 构建阶段启用离线模式，并固定 `SOURCE_DATE_EPOCH=1788019199`。
- 三个 sdist 验证构建均各执行两次，同包的两次输出 SHA256 一致。Bilibili sdist 重构结果为 387,374 字节、SHA256 `fd2c1c7de6fd957beff04a3ade779142faa14faeec520f29369dbf7d42d9564b`，仅作为比较证据，不进入交付选择。
- 这里证明的是本机相同条件下双次结果一致，不宣称已经证明跨机器可复现。
- aiotieba 固定源码提交为 `bae68256fd250d5178e1447899ffa155c77eda38`，源码树为 `0074b12c931b790d981f4403d3cee2f421d66472`。成功构建使用 CPython 3.13.9 x64、CMake 4.4.2 和 GitHub `windows-2025` 运行环境；目标 wheel 构建不解析或安装运行依赖。
- GitHub 制品 ZIP 为 249,562 字节，SHA256 为 `3be9af885db3ab8c32c1d8ca5c7480c41a3d8a9c7bb0757dabd6d86eb2a18d1c`。当前只有一次成功生成，不把它描述为跨运行器可复现构建。
- newspaper4k 固定源码树为 `6916249fa3b45eb44a5c3e7945b6607e99500225`；由 Git 提交导出的源码 ZIP 为 9,372,257 字节，SHA256 为 `cb2bcde50e3eee0feb62a77b29a743696dc35fd1815c7d9d12621b752948901c`。
- newspaper4k 使用 CPython 3.13.9 x64、uv 0.10.8、固定构建依赖和相同时间戳，从两个独立源码快照各构建一次；第二次构建完全离线，两份 wheel 的文件名、大小与 SHA256 完全一致。

## 内容审计

- 6 个本地验证 wheel 均为 `py3-none-any`、`Root-Is-Purelib: true`，ZIP CRC 正常。
- 未发现重复成员、绝对路径、盘符路径、反斜杠路径或 `..` 路径穿越。
- 6 个 wheel 的 `RECORD` 均覆盖全部成员，每项 SHA256 和大小一致。
- PyPI 官方 Bilibili wheel 的 `RECORD` 164/164 通过；它与 sdist 重构 wheel 的 164 个成员清单相同，161 个程序和数据成员逐字一致。
- 两个 Bilibili wheel 仅 `METADATA` 换行风格、`WHEEL` 构建器版本和相应 `RECORD` 不同；12 项 `Requires-Dist` 完全相同。因此正式交付选择更短、更可审计的 PyPI 官方 wheel 路径。
- aiotieba wheel 的 ZIP CRC、路径安全和 `RECORD` 353/353 全部通过；`aiotieba/helper/crypto/crypto.pyd` 的 PE 机器类型为 AMD64，wheel 标签为 `cp313-cp313-win_amd64`。
- newspaper4k wheel 的 ZIP CRC、路径安全和 `RECORD` 133/133 全部通过；未包含 `.pyd`、DLL 或其他原生库，标签为 `py3-none-any`。

## 运行时集成

- 在全新 CPython 3.13.9 环境中，先校验并安装自建 wheel，再用 D1 原始哈希锁严格同步其余依赖；同步使用 `only-binary`，未现场构建缺失包。
- 主运行时和 newspaper4k 运行时均通过 `uv pip check` 与 `import jieba`。
- Bilibili 最终组合为“自建 qrcode-terminal + PyPI 官方 bilibili-api-python + 完整运行锁”，离线同步 35 个包后 `uv pip check` 通过，`import qrcode_terminal, bilibili_api` 通过；安装后的 Bilibili `WHEEL` 生成器为官方产物的 `setuptools 82.0.1`。
- 修正策略后重新验证六份 D1 锁，六个全新隔离环境的严格同步、依赖检查和最小导入全部通过，锁文件 SHA256 均未变化。
- aiotieba 在 GitHub 构建环境和本机全新临时 CPython 3.13.9 x64 环境各完成一次完整运行锁安装。两处 `pip check` 均通过；本机环境共检查 18 个包，并通过 `import aiotieba` 与原生 `c3_aid` 函数导入。
- newspaper4k 在全新临时 CPython 3.13.9 x64 环境中先安装已锁定的 Jieba wheel，再按运行锁安装其余二进制依赖；`pip check` 检查 23 个包通过，`import newspaper` 与离线 `Article` 最小构造通过。

## 非阻断警告与门禁

- Jieba 在 Python 3.13 导入时仍产生上游 `invalid escape sequence` 的 `SyntaxWarning`；导入和依赖检查通过。
- bilibili-api-python 声明 `GPL-3.0-or-later`。技术制品就绪不等于许可放行，`distributionGate=pending-d4-license-review` 继续使严格发布门禁失败。
- newspaper4k 未安装可选的 NLTK 时会提示部分 NLP 功能不可用；当前适配器只调用文章解析，不使用这些可选功能。
- newspaper4k wheel 内的 `stopwords-fr.txt` 带 Apache-2.0 声明，而 wheel 只附带项目 MIT LICENSE。D4 需要确认完整 Apache 许可证文本和 NOTICE 义务后，才可解除 `pending-d4-bundled-apache-license-review` 门禁。
- 既有 wheel 和验证环境只保留在系统临时目录；aiotieba 的 GitHub 制品 ZIP 由用户下载到 `Downloads`，解压与安装复核位于系统临时目录。它们都没有写入候选包；没有读取或使用真实 API Key，也没有访问、删除、暂存或打包 `.codex_tmp/`、本机 `requirements/` 或 `data/`。
