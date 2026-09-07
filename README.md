# Flight Map

FAA 航空资料的本机研究平台：官方原件、可追溯记录、独立产品版本、地图和在线航图对照。

> 仅供研究与学习，不得用于航空器导航、签派放行或替代官方 AIP、NOTAM 与飞行前简报。

## 已实现与实际覆盖

- SQLite 保存原件获取记录、发布输入、结构化记录、验证报告和事务化 Current 指针；原件按 SHA-256 保存在本地。
- d-TPP 支持自动发现、下载目录 XML、验证精确有效期、建立机场/航图目录、检索和官方 PDF 并排查看。机场目录没有坐标，不会伪造地图点。
- NASR 支持机场小包自动下载和 CSV 解析，保存官方标识、NAD83 坐标和字段溯源。**当前公开产品资料仅确认生效日期，精确 UTC 有效区间尚缺证据，因此自动更新保留原件/报告并返回需要补充依据，不进入 Current。**
- CIFP 支持公开字段依据下的结构读取和独立 IF/TF 名义几何引擎。**官方协议、真实程序黄金样本、字段例外与完整分支语义尚未核实；当前 CIFP 解析报告始终阻断发布，不宣称已交付真实程序矢量覆盖。**
- API 和前端固定发布版本，检查过期、撤销和权限；历史/预览需要显式选择。

2026-09-07 的本机真实验证：d-TPP 2609 已建立并提升为 Current；3,197 个无坐标机场目录项、24,231 条航图记录。12 条尚无充分类别依据的记录保留为不支持项。NASR 19,411 条机场记录完成解析，发布因时间证据缺失而阻断。原件、数据库和本机发布不会提交 Git。

## 启动

需要 Python 3.12、uv、Node.js 22+。不需要 Docker、PostGIS 或 MinIO。

```powershell
uv sync --all-packages --dev --locked
npm ci
./scripts/dev.ps1
```

也可以分别运行 `uv run flightmap-api` 和 `npm run dev`。前端默认 [127.0.0.1:5173](http://127.0.0.1:5173)，API 文档在 [127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)。

默认数据目录为仓库下的 `data`。可通过环境变量 `FLIGHTMAP_DATA_DIR` 或 CLI 的 `--data-dir` 指定另一个目录；API 和 CLI 必须使用同一目录。CLI 的 `--registry`、API 的 `FLIGHTMAP_SOURCE_REGISTRY` 可覆盖来源配置。环境文件是示例，应用不会自动把其中的值导入当前 PowerShell。

## 更新和发布

```powershell
uv run flightmap-ingest discover-faa --product dtpp --dry-run
uv run flightmap-ingest update --product dtpp
uv run flightmap-ingest report --release-id <update输出的release_id>
uv run flightmap-ingest promote --release-id <通过报告检查的release_id>
```

`update` 只构建候选；`promote` 才切换 Current，并重新检查权限、有效期、报告和原件哈希。同一输入重复更新会返回 `unchanged`。发布 ID 包含内容身份，同周期更正也会生成独立版本。

- NASR：`uv run flightmap-ingest update --product nasr`。尚无精确时间依据时退出码为 2，原件和解析报告保留。补充官方依据后可提供 `--manifest <JSON文件>`。
- CIFP：`uv run flightmap-ingest update --product cifp` 当前返回 `needs-user-action`。不会接受协议或绕过下载流程；处理协议也不会自动解除解析证据阻断。
- 本地文件：`uv run flightmap-ingest import-local --product nasr --file <官方文件> --manifest <JSON文件>`。清单契约见 [import-manifest.schema.json](docs/import-manifest.schema.json)，时间必须有产品级证据，不能照搬其他产品的 09:01 UTC。
- 撤销：`uv run flightmap-ingest revoke --release-id <id> --reason "<原因>"`。撤销后默认及历史数据接口都停止返回该发布的记录。

退出码：0 为成功/未变化，1 为获取或验证失败，2 为需要人工操作或缺少证据。失败和阶段产物保存在数据目录；更新命令不发送外部消息、不自动发布。

## 使用

选择当前或显式历史/预览版本，搜索机场并打开资料面板。d-TPP 机场目录支持在 NASR 尚不可发布时独立搜索航图。官方 PDF 尝试使用浏览器原生查看器；不能嵌入时使用始终显示的“打开官方 PDF”链接。

不同产品的同名记录分别保留。CIFP 与航图的精确关联尚未获足够依据，界面只提供同机场、兼容周期的目录供选择，不自动按相似名称配图。地图只显示有效发布中的真实几何。

## 验证

```powershell
uv run ruff check .
uv run pytest
npm run lint
npm run test:web
npm run build
npx playwright install chromium
npm run test:e2e
```

单元与浏览器集成测试使用明确标识的合成数据，并与普通数据目录隔离。官方网络探测是单独工作流，失败会报告，不用来决定数据发布。

## 资料与后续推进

- [执行台账](docs/implementation-plan.md)：批准计划的全部任务编号、完成情况和阻断项。
- [任务卡模板](docs/task-card-template.md)：为后续小模型任务固定输入、输出和验收。
- [本机验收记录](docs/verification-2026-09-07.md)：真实产品结果、测试范围和未完成能力。
- [架构与生命周期](docs/architecture.md)、[接口契约](docs/interface-contract.md)。
- [官方来源证据](docs/source-evidence.md)、[CIFP 支持矩阵](docs/cifp-support.md)、[数据政策](docs/data-policy.md)。

完整备份需在停止 API/CLI 后同时复制整个数据目录，包含 SQLite 和原件；恢复到新目录后用同一来源配置启动。不要只复制数据库而遗漏原件。代码使用 Apache-2.0，数据和参考字段表遵守各自条款。
