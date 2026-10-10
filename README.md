# AI+舆情检测系统：项目文件入口

本目录是开发工作区。给甲方的 Windows 11 包在 [交付文件索引](delivery/README.md)，不要直接把整个文件夹复制给甲方。

| 位置 | 内容 |
| --- | --- |
| [delivery/](delivery/README.md) | 正式交付、累计更新、历史候选和依赖锁定资料 |
| `src/`、`web/`、`config/`、`web_app.py` | 当前程序源码、页面和配置 |
| `tests/` | 自动测试 |
| [tasks/plan.md](tasks/plan.md)、[tasks/todo.md](tasks/todo.md) | 历史计划和待办记录；以实际代码和交付索引核对当前状态 |
| `requirements/` | 历次需求讨论材料，仅用于内部管理 |
| `data/`、`output/` | 本机运行数据和报告，不纳入更新包 |
| `.venv/`、`.scrapling-venv/`、`opensource_candidates/` | 本机依赖与隔离运行环境，不纳入增量更新包 |
| `.codex_tmp/`、`.pytest_cache/`、`pytest-cache-files-*/`、`*.log` | 本机临时文件和日志，不纳入交付 |

天津当前使用 [2026-09-25 累计更新](delivery/portable/updates/2026-09-25/README.md)，廊坊使用 [2026-09-28 廊坊专用累计更新](delivery/portable/updates/2026-09-28-langfang/README.md)。开发源码仍保留天津来源，廊坊改动隔离在专用更新目录中。旧交付文件和本机材料先保留，避免整理目录时丢失验收与回退依据。
