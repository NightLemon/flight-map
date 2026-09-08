# 日期级研究浏览：R01 冻结契约

本文件与 `flightmap_schema.ResearchSnapshot` 是本轮 R01–R21 的实现依据。严格发布契约保持独立。

## 快照与仓库

快照字段以模型为准。日期依据来自 NASR APT_BASE.csv 的 EFF_DATE；UTC 日历日期只用于页面分类，绝不声称是产品生效时刻。预计更新日为官方日期加 NASR 自身 28 天发行间隔，仅作提醒。

Repository 新方法：stage_snapshot(snapshot, records, report) -> id；get_snapshot(id)；resolve_snapshot(id, product, source_id=..., mode='active'|'history'|'preview', at=...)；activate_snapshot(id, product, source_id='faa-aeronav', at=...)；revoke_snapshot(id, reason)；snapshot_report(id)；list_snapshot_records(id, q=None, limit=100000, offset=0)；research_status(policies, at=...)；record_research_attempt(product_id, status, message, snapshot_id=None)；get_acquired_asset(sha, source_id=..., product_id=...)。

快照身份包含模型所有证据字段，排除 ID 自身；不包含构建时间、获取事件时间或本机路径。相同 ID 的内容不同返回 409。报告计数必须平衡，成功数必须等于记录数。候选可保留阻断报告；激活/读取时拒绝阻断、撤销、错来源、失效权限、原件损坏。未来日期不能激活。陈旧快照可明确标注研究使用，无额外许可确认。

## HTTP

研究模式参数 `mode=active|history|preview`，默认 active。旧请求遇活动指针改变返回 409。history 允许明确选择已生效的非活动候选/旧版，preview 仅未来日期。撤销返回 410，证据/权限/校验失败 403。

`GET /api/v1/research/snapshots` 返回 `{current_time, active_snapshots: {nasr: SnapshotStatus}, snapshots: SnapshotStatus[], attempts, storage_errors, disclaimer}`。`/api/v1/status` 增加 `research` 同形对象，在一次状态读取中固定机场快照及各产品发布。

SnapshotStatus 为模型字段加 `state=active|staged|history|preview|revoked|blocked`、`date_status=researchable|future|update-due|unavailable`、`expected_update_date`、`reason`、`counts`、`revoked_reason`。

`/api/v1/research/search`：必传 snapshot_id、q，limit 默认100最大500；按 FAA、显式 ICAO、名称搜索，精确标识优先。`/api/v1/research/features`：必传 snapshot_id；layer 仅 airports（默认）；bbox 和 limit 同原地图接口。两者分别返回 items 或 GeoJSON，附 `snapshot_id, mode, disclaimer, truncated`，每个 Feature 属性有 snapshot_id 与 provenance。

`/api/v1/research/snapshots/{id}/report` 返回 `{snapshot, report, inputs: RawAsset[], disclaimer}`，允许查看失败候选依据。所有响应 no-store。

图纸目录使用现有 `/api/v1/airports/{FAA-ID}/charts`，自动对照要求快照官方日期等于 d-TPP valid_from 的日期，固定 release_id，不能推造 ICAO 或猜图纸。

`/api/v1/charts/{chart_id}/pdf?release_id=...&mode=current|preview|history` 返回内存 PDF，响应头 `X-FlightMap-Release-Id`、`X-FlightMap-Chart-Id`、`X-FlightMap-Pdf-Sha256`。仅所选 d-TPP 周期官方 HTTPS PDF，无重定向或浏览器凭据；20 MiB/20秒上限，检查类型/文件头，返回前复检门禁。上游错误502、超时504只影响面板。前端固定 pdfjs-dist 6.3.289，本地 worker/资源，渲染完成才显示成功。

## 冻结验收样本

真实 NASR SHA d5e4c999d4c96ab4d66d8ce9a387de8ea59b5226a6144ea1ba58758ff29bbbd9：2026-09-03，19411输入/成功，0不支持/错误；JFK/KJFK，纬度40.63992805，经度-73.77869222，NAD83。原件保留本地，不入Git。

真实 d-TPP 2609：SEA `00582IL16C.PDF` 标题 ILS OR LOC RWY 16C；JFK `00610VG13LR.PDF` 标题 VOR OR GPS RWY 13L/R。浏览器须验证实际机场点、搜索地图移动、PDF页数和非空画面，截图核对标题。

合成 PDF 固定两页，第一页文本 `SYNTHETIC TEST ONLY - PAGE 1`，第二页 `SYNTHETIC TEST ONLY - PAGE 2`，页面612×792点。翻页应显示第二页，切换立即清除前图；它只用于测试，不能代替真实验收。

## 执行与升级

R01契约；R02迁移；R03保存；R04门禁；R05激活；R06撤销；R07复用原件；R08在线更新；R09报告；R10状态；R11搜索；R12范围；R13固定版本；R14机场点；R15定位；R16目录；R17读取PDF；R18渲染；R19控制；R20并排；R21真实验收。每项测试后单独提交，仅提交自己修改的路径。

2026-09-08 升级前已停止 API，并完整备份 data 到 `.cache/backups/pre-research-20260908/data`。回退须恢复完整备份，旧程序不能读取 schema 2。
