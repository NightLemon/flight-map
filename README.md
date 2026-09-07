# Flight Map

Flight Map 是一个**非运行用途**的航空资料收集、版本管理与地图展示平台。首期以 FAA 为权威来源实现美国端到端数据链，再按国家逐步扩展。

> **安全提示：** 本项目不得用于航空器导航、签派放行或替代官方 AIP、NOTAM 与飞行前简报。地图显示“当前 AIRAC”不代表已包含临时限制。

## 当前状态

项目已建立第一阶段骨架：

- FAA CIFP、NASR、d-TPP、IFR 航图和安全公告来源注册表；
- 28 天 AIRAC 周期及左闭右开有效区间；
- `discover → acquire → verify → parse → normalize → validate → stage → promote` 失败关闭状态机；
- 带 SHA-256、HTML/ZIP 完整性检查和内容寻址缓存的下载器；
- FastAPI 状态、来源与覆盖 API；
- MapLibre 前端研究界面，目前有意不展示任何未经验证的航空数据；
- 许可未确认、验证失败或已经过期的数据不能发布。

原始航图、压缩包、数据库和瓦片不会提交 Git。

## 本地开发

需要 Python 3.12、uv、Node.js 22+ 和 npm。

1. 运行 `uv sync --all-packages --dev` 安装 Python 工作区。
2. 运行 `npm install` 安装前端工作区。
3. 分别运行 `uv run flightmap-api` 与 `npm run dev`。
4. 也可以在 PowerShell 中运行 `./scripts/dev.ps1` 同时启动两者。

默认 API 文档位于本地 `/docs`，前端开发服务器会把 `/api` 代理到 `127.0.0.1:8000`。

## 验证

- Python：`uv run ruff check .`、`uv run pytest`
- Web：`npm run lint`、`npm run build`
- FAA 只读发现：`uv run flightmap-ingest discover-faa --dry-run`

发现命令只扫描官方页面，不下载大文件，也不会自动发布数据。

## 数据原则

1. 官方来源优先，社区数据不能静默覆盖官方字段。
2. 每条发布记录必须包含来源、AIRAC、有效区间、抓取时间、原件 SHA-256、解析器版本、许可和质量状态。
3. Preview 数据不进入 Current；旧周期失效后必须下线。
4. 未支持的 ARINC Path Terminator 不生成 fallback 直线。
5. PDF OCR 只能帮助搜索，不得生成权威航路。
6. “公开可查看”不等于“允许抓取和再分发”；未知许可默认拒绝发布。

详细规则见项目文档目录。代码采用 Apache-2.0；数据继续服从各来源自己的许可与使用条款。
