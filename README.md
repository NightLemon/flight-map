# Flight Map

FAA 航空资料的本机研究平台：官方原件、可追溯记录、独立产品版本、地图和在线航图对照。

在线访问：[GitHub Pages 公开参考版](https://nightlemon.github.io/flight-map/) · [源代码](https://github.com/NightLemon/flight-map)

公开版使用标明来源的 **OurAirports Public Domain** 数据，提供全球机场、机场频率、已知两端坐标的跑道和导航台，按视野加载。它是独立社区参考层；本机 FAA 研究版的航点、航路、版本管理与 PDF 核对不在 Pages 上运行。两套资料不会混合，也不把社区数据标为 FAA 官方记录。构建与数据边界见 [GitHub Pages 部署说明](docs/github-pages.md)。

> 仅供研究与学习，不得用于航空器导航、签派放行或替代官方 AIP、NOTAM 与飞行前简报。

## 已实现与实际覆盖

- SQLite 保存原件获取记录、发布输入、结构化记录、验证报告和事务化 Current 指针；原件按 SHA-256 保存在本地。
- d-TPP 支持自动发现、下载目录 XML、验证精确有效期、建立机场/航图目录、检索和官方 PDF 并排查看。机场目录没有坐标，不会伪造地图点。
- NASR 支持机场小包自动下载和 CSV 解析，保存官方标识、NAD83 坐标和字段溯源。使用 `--research` 构建独立的日期级研究快照，显式激活后供机场地图和搜索使用。**精确 UTC 有效区间仍缺证据，研究快照不能提升为 Current。**
- CIFP 支持公开字段依据下的结构读取和独立 IF/TF 名义几何引擎。**官方协议、真实程序黄金样本、字段例外与完整分支语义尚未核实；当前 CIFP 解析报告始终阻断发布，不宣称已交付真实程序矢量覆盖。**
- API 和前端分别固定机场快照与航图发布版本，检查撤销和权限；严格发布继续检查精确有效期。历史/预览需要显式选择。跑道、导航点、航路及程序图层仍受各自解析依据和实现范围限制。

2026-09-08 的本机真实数据：d-TPP 2609 为 Current，含 3,197 个机场目录项、24,231 条航图记录；12 条尚无充分类别依据的记录保留为不支持项。NASR 2026-09-03 的 19,411 条机场记录全部通过已实现的解析验证，并已激活为独立研究快照；它们不计入严格 Current。原件、数据库和本机版本不会提交 Git。

## 启动

需要 Python 3.12、uv、Node.js 22.13.0+。不需要 Docker、PostGIS 或 MinIO。

```powershell
uv sync --all-packages --dev --locked
npm ci
./scripts/dev.ps1
```

安装依赖后也可以分别运行 `.\.venv\Scripts\flightmap-api.exe` 和 `npm run dev`。前端默认 [127.0.0.1:5173](http://127.0.0.1:5173)，API 文档在 [127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)。依赖变化时先停止 API，再执行 `uv sync`，避免 Windows 锁定正在运行的启动器。

默认数据目录为仓库下的 `data`。可通过环境变量 `FLIGHTMAP_DATA_DIR` 或 CLI 的 `--data-dir` 指定另一个目录；API 和 CLI 必须使用同一目录。CLI 的 `--registry`、API 的 `FLIGHTMAP_SOURCE_REGISTRY` 可覆盖来源配置。环境文件是示例，应用不会自动把其中的值导入当前 PowerShell。

## 机场研究快照

```powershell
.\.venv\Scripts\flightmap-ingest.exe update --product nasr --research
$snapshotId = "<上一步输出的 snapshot_id>"
.\.venv\Scripts\flightmap-ingest.exe report --snapshot-id $snapshotId
.\.venv\Scripts\flightmap-ingest.exe activate-snapshot --snapshot-id $snapshotId
```

`update --research` 只保存候选，`activate-snapshot` 才切换研究选择。已有原件可加 `--asset-sha256 <完整SHA>` 离线构建，不重复下载或增加获取事件。预览版加 `--preview`，未来日期不能激活。达到 NASR 预计更新日期后显示更新提醒，仍可明确按研究模式浏览；这不表示已知官方失效时刻。详见 [本机操作说明](docs/local-operations.md)。

### NASR research-2 图层候选

research-2 把同一官方日期的 NASR 原件组成五个地图层：机场、跑道、导航台、航点、航路；点击机场还会读取机场通信频率。构建命令只建立候选，不会激活研究指针或改变严格 Current：

```powershell
.\.venv\Scripts\flightmap-ingest.exe update --product nasr --research --all-layers
.\.venv\Scripts\flightmap-ingest.exe update --product nasr --research --all-layers --bundle-manifest .cache/nasr-bundle.json
```

第二条命令只使用本机已登记的七项 SHA-256 原件，不下载数据。`--bundle-manifest` 必须与 `--all-layers` 一起使用，`--all-layers` 必须使用 `--research`，且两者不能和 `--asset-sha256` 混用。七项原件和解析边界见 [NASR 图层记录](docs/nasr-layers-2026-09-08.md)。旧 research-1 快照仍是机场模式，严格 Current 和 CIFP 的现有门禁不因 research-2 改变。

地图默认只开启机场；每个已开启层按视野最多 500 项。最小缩放级别为机场 Z8、跑道 Z10、导航台 Z6、航点 Z9、航路 Z5。图例颜色为机场青色、跑道橙色、导航台蓝色、航点洋红、航路紫色；点击机场会显示用途、扇区、备注、仅接收标记和原件来源。本机 research-2 已激活，纽约四个新增图层及 JFK/SEA 自动通信展示已通过真实浏览器验收，详见 [多图层验收记录](docs/nasr-layers-2026-09-08.md)。

## 严格更新和发布

```powershell
.\.venv\Scripts\flightmap-ingest.exe discover-faa --product dtpp --dry-run
.\.venv\Scripts\flightmap-ingest.exe update --product dtpp
$releaseId = "<上一步输出的 release_id>"
.\.venv\Scripts\flightmap-ingest.exe report --release-id $releaseId
.\.venv\Scripts\flightmap-ingest.exe promote --release-id $releaseId
```

`update` 只构建候选；`promote` 才切换 Current，并重新检查权限、有效期、报告和原件哈希。同一输入重复更新会返回 `unchanged`。发布 ID 包含内容身份，同周期更正也会生成独立版本。

- 不带 `--research` 的 NASR 更新仍走严格路径：缺少精确时间依据时退出码为 2，保留原件和报告。补充官方依据后可提供 `--manifest "<JSON文件>"`，不能照搬其他产品的 09:01 UTC。
- CIFP 更新当前返回 `needs-user-action`。不会接受协议或绕过下载流程；处理协议也不会自动解除解析证据阻断。
- 本地严格导入使用 `import-local --product nasr --file "<官方文件>" --manifest "<JSON文件>"`。清单契约见 [import-manifest.schema.json](docs/import-manifest.schema.json)。
- 严格发布撤销使用 `revoke --release-id "<id>" --reason "<原因>"`；研究快照使用 `revoke-snapshot --snapshot-id "<id>" --reason "<原因>"`。撤销后各自的数据入口拒绝读取，报告仍可查看。

退出码：0 为成功/未变化，1 为获取或验证失败，2 为需要人工操作或缺少证据。失败和阶段产物保存在数据目录；更新命令不发送外部消息、不自动发布。

## 使用

左侧默认只显示一行资料日期和图层开关。点击“数据管理”可展开版本切换、覆盖状态、来源和验证报告；历史/预览及待更新状态会在收起时保留简短提醒。

地图使用 MapLibre GL 与 OpenStreetMap 底图，默认概览不请求或绘制机场点。放大到局部（Z8 起）才按当前视野查询机场，每层每次最多 500 条；密集机场以数字聚合，点击展开，Z10 起显示机场标识。也可搜索机场直接定位。拖动地图会取消旧视野请求，停止移动后再加载。底图需要访问 `tile.openstreetmap.org`，瓦片失败会单独提示。

窄窗口使用右下角 ＋ / − 或 Ctrl＋滚轮缩放地图（Mac 为 ⌘＋滚轮）；普通滚轮滚动页面，触屏使用双指。尝试普通滚轮缩放时会显示操作提示。

选择机场研究快照，搜索并定位地图，再从机场资料面板选择航图。航图目录和 PDF 固定使用所选 d-TPP 发布版本。PDF 面板逐页渲染，支持翻页与缩放；网络或渲染失败会说明原因，并始终保留官方 PDF 链接。

不同产品的同名记录分别保留。自动提供机场航图目录要求 NASR 官方日期与 d-TPP 生效日期一致，不会给旧机场快照悄悄配上最新图纸。CIFP 与航图的精确关联尚未获足够依据，不能按相似名称猜选程序航图。

## 验证

```powershell
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m pytest
npm run lint
npm run test:web
npm run build
npx playwright install chromium
npm run test:e2e
```

单元与浏览器集成测试使用明确标识的合成数据，并与普通数据目录隔离。官方网络探测是单独工作流，失败会报告，不用来决定数据发布。

已导入冻结的真实 NASR/d-TPP 数据后，可运行 `.\.venv\Scripts\python.exe scripts/verify_research_lifecycle.py`。脚本只在临时副本中演练，禁止网络获取，结束后清理副本并将报告写入 `.cache/research-lifecycle-report.json`。

## 资料与后续推进

- [接手分析与后续计划](docs/takeover-2026-09-08.md)：当前复核、首批可靠性修复及 NASR 跑道研究的分阶段建议。
- [执行台账](docs/implementation-plan.md)：批准计划的全部任务编号、完成情况和阻断项。
- [任务卡模板](docs/task-card-template.md)：为后续小模型任务固定输入、输出和验收。
- [本机验收记录](docs/verification-2026-09-08.md)：真实产品结果、测试范围和未完成能力。
- [日期级研究契约](docs/research-contract.md)、[本机操作与恢复](docs/local-operations.md)：本轮快照模型、命令、日期状态及 schema 2 的回退方式。
- [架构与生命周期](docs/architecture.md)、[接口契约](docs/interface-contract.md)。
- [官方来源证据](docs/source-evidence.md)、[CIFP 支持矩阵](docs/cifp-support.md)、[数据政策](docs/data-policy.md)。

完整备份需在停止 API/CLI 后同时复制整个数据目录，包含 SQLite 和原件；恢复到新目录后用同一来源配置启动。不要只复制数据库而遗漏原件。代码使用 Apache-2.0，数据和参考字段表遵守各自条款。
