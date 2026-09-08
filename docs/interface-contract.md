# 本机接口契约

API 是只读接口，所有航空数据响应携带非运行用途声明，并使用 Cache-Control: no-store。字段模型以 flightmap_schema 和 FastAPI /openapi.json 为准。

2026-09-08 新增独立日期级机场研究快照与本机受限 PDF 读取，完整字段和行为见 [研究浏览契约](research-contract.md)。严格发布接口继续使用本文件的精确有效期规则。

## 状态与覆盖

- GET /health：进程存活状态。
- GET /api/v1/status：current_time、airac（日历）、current_releases（product_id → 发布）、releases（可选择版本）、attempts、storage_errors、disclaimer。
- GET /api/v1/sources：机器可读来源和产品本地使用/再分发政策。
- GET /api/v1/coverage：每个产品的状态、精确有效期、最近获取结果、计数和官方入口。

覆盖状态独立表达 not-imported、failed、blocked、current、expired 等情况。已存在有效 Current 时，获取失败保留 current，latest_attempt 与 note 说明失败；没有候选时缺少证据显示 blocked。

last_successful_release 提供该产品最近一个已到生效时刻、门禁检查通过的版本（id、airac、valid_from、valid_to、state），可以已过期，不代表当前可用。新失败候选不覆盖这项记录；没有成功版本时为 null。notices_url 来自同来源的官方更正公告入口，没有登记时为 null。

Release 使用 id、source_id、product_id、airac、valid_from、valid_to、retrieved_at、sha256、input_sha256、parser_version、quality_status、license_status、local_access、validity_evidence、capabilities 和 issues。状态接口另有 state、reason 和 counts。

state 包含 current、staged、preview、history、quarantined、revoked、blocked。没有可用发布时 publication_state=empty。

## 固定版本的数据请求

以下接口要求 release_id，mode 默认为 current，可显式指定 preview/history。来源与产品从发布读取；不能靠请求参数更换发布身份。

| GET 路径 | 参数/结果 |
|---|---|
| /api/v1/search | q，limit≤500；按标识、名称及显式 properties.icao_id 搜索，精确标识优先；返回 items: ResearchRecord[]，排除原始腿和航图记录；包含 d-TPP 无坐标机场目录 |
| /api/v1/features | layer=airports/runways/navaids/waypoints/airways，bbox=西,南,东,北，limit≤10000；返回 GeoJSON FeatureCollection 和 truncated |
| /api/v1/airports/{id}/charts | id 使用 d-TPP 官方 FAA 机场标识；返回航图 items |
| /api/v1/airports/{id}/procedures | id 使用 CIFP 官方机场标识；不推造 ICAO 前缀 |
| /api/v1/procedures/{id} | 返回 record、完整 legs、branches |
| /api/v1/procedures/{id}/geometry | 必须指定 branch_id；返回 FeatureCollection、gaps、notice |
| /api/v1/releases/{id}/report | 返回 release、report、diff；用于审查候选，允许查看阻断报告 |

数据响应包含 release_id、mode、disclaimer。地图 bbox 可横跨180度，西经度大于东经度时按跨日期变更线范围查询。超限显式 truncated，不声称返回全部。

ResearchRecord 固定字段：id、kind、name、identifier、airport_id、airport_ident、parent_id、branch_id、sequence、geometry、properties、provenance。kind 使用单数。geometry 可以为 null；缺坐标不能生成推测坐标。

provenance 包含 asset_sha256、member、line、locator；资产/发布元数据提供其他来源信息。properties 保留产品原始字段；NASR airport 保留 icao_id、datum，d-TPP chart 提供 chart_code、pdf_url、chart_name，程序提供 procedure_type，程序腿使用 path_terminator。

## 错误

- 400：缺少发布 ID、无效参数或非法模式。
- 403：权限、来源、质量或已保存的报告不允许访问。
- 404：指定发布/记录/分支不存在。
- 409：Current 指针已变化，或版本不属于请求的模式；前端刷新完整快照。
- 410：默认发布过期/未生效，或发布被撤销。
- 422：FastAPI 请求类型校验失败。

PDF 使用受限本机读取接口 `/api/v1/charts/{chart_id}/pdf?release_id=...&mode=...`：仅所选 d-TPP 周期登记的 FAA PDF，无任意 URL、重定向或浏览器凭据转发。20 MiB / 20 秒上限，内存读取，返回前复检发布，附发布/航图 ID 与文件 SHA。前端使用本地 PDF.js 渲染，始终保留官方链接。上游失败返回 502/504，仅影响航图面板；本地 403/409/410 执行整组版本清理。

## CLI

discover-faa 只发现并分类，支持 --product、--dry-run、--output；网络失败退出1且保存报告。update 构建到候选，import-local 需要符合 import-manifest.schema.json 的证据清单。report 展示计数与前一候选的差异；promote 重新执行门禁；revoke 需要原因。

所有写操作由 CLI 执行。数据库和原件默认在 data，可用 FLIGHTMAP_DATA_DIR 覆盖；CLI 的 --data-dir 与 API 必须指向同一位置。
