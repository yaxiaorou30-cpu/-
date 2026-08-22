# 第三方开源项目与运行边界

本文件记录当前仓库中已下载或由程序调用的第三方项目。交付打包时应保留实际运行依赖的许可证文本和本文件。

| 项目 | 固定提交 | 许可证 | 当前用途 |
|---|---|---|---|
| [bilibili-cli](https://github.com/public-clis/bilibili-cli) | `dbe28551930df43b633baa52e9639832aeada967` | Apache-2.0，仓库含 `LICENSE` | 默认启用的 B站隔离只读搜索适配器 |
| [newspaper4k](https://github.com/AndyTheFactory/newspaper4k) | `b53a81fc01ff54601faaeae68d6b4a6d2f18efcb` | MIT，仓库含 `LICENSE` | 政府官网正文的可选只读提取器 |
| [aiotieba](https://github.com/lumina37/aiotieba) | `bae68256fd250d5178e1447899ffa155c77eda38` | Unlicense，仓库含 `LICENSE` | 贴吧详情可选增强；失败时回退授权浏览器 |
| [crawl4weibo](https://github.com/Praeviso/crawl4weibo) | `1bc21e0e9d5fc1311b3016a8894c2c4edeb3d8c7` | MIT，仓库含 `LICENSE` | 已安装的微博替换候选；当前桌面会话不能直接复用为移动端会话，默认停用 |
| [xhs-cli](https://github.com/jackwener/xhs-cli) | `3ce71415dc0816ebb4c3f547baf6c08fb3d5cb5a` | Apache-2.0，仓库含 `LICENSE` | 仅参考数据结构；运行路径依赖浏览器指纹改写，默认停用 |
| [MediaCrawler](https://github.com/NanmiCoder/MediaCrawler) | `17f66121e0fcc40fc23958b995bec873d422667d` | 非商业学习许可证 | 仅作架构参考，不复制代码、不作为交付运行依赖 |
| [xiaohongshu-cli](https://github.com/jackwener/xiaohongshu-cli) | `4d63f3c0c85ccd9054fa8e96d7f761aaf2507449` | 当前检出的仓库缺少独立许可证文件 | 仅作行为参考，不复制代码、不运行 |
| [weibo-cli](https://github.com/jackwener/weibo-cli) | `ea2e86e0b3c9fb4120660529a60ed7a44b2b90bb` | 当前检出的仓库缺少独立许可证文件 | 仅作行为参考，不复制代码、不运行 |

共同运行边界：

- 只执行搜索、页面读取和结构化解析，不调用点赞、评论、发布、关注等写操作。
- 凭据只从本机加密存储读取，并通过子进程标准输入传递；不得放入命令行参数、日志或输出。
- 不破解验证码，不启用浏览器指纹改写，不自动注册账号，不使用代理池轮换规避平台限制。
- 出现验证码、401/403/429、账号风控或平台权限限制时停止或退避，并明确提示人工恢复。

