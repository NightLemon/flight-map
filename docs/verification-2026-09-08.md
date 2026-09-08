# 真实机场与航图研究验收

## 验收清单

用户流程：真实机场点 → FAA/显式 ICAO/名称搜索 → 地图定位 → 日期/NAD83/原件来源 → 同日期官方目录 → PDF 实际渲染。桌面并排宽度调整、缩放、适应宽度、页码、翻页、关闭/换图清空均需要行为检查。

异常流程：版本切换/撤销/权限或原件损坏拒绝读取；未来预览必须显式选择；预计更新日仅提醒；网络失败保留官方链接；切换图纸不能显示旧图；窄屏仍可操作。

## 已执行的数据升级与后端检查

- 升级前停止 API，将完整 data 备份至 `.cache/backups/pre-research-20260908/data`。
- 编号迁移 002 保留原表。真实升级后对 assets、acquisitions、releases、release_assets、records、current_releases 逐表与备份比较，相等。
- 用已登记 SHA `d5e4c999d4c96ab4d66d8ce9a387de8ea59b5226a6144ea1ba58758ff29bbbd9` 零下载构建，并检查报告后显式激活 `nasr-research-2026-09-03-0e09b035f1a6e72624e1d018`。
- NASR：官方日期 2026-09-03；19,411 输入/成功，0 不支持/错误。JFK/KJFK 坐标经度 -73.77869222、纬度 40.63992805，NAD83，APT_BASE.csv 行 10622（数据记录 10621）。
- d-TPP Current 保留 `dtpp-2609-1c493184b1bc8a79edfc6a4c`，精确有效区间 `[2026-09-03T09:01Z, 2026-10-01T09:01Z)`。NASR 快照无虚构时刻。
- PDF 集成接口真实读取 SEA `00582IL16C.PDF`（478,810 bytes，1 页，SHA `a0c671963cb97d9592bfece78a1d2c1503fb87224e091f33f00172a539ad0513`）和 JFK `00610VG13LR.PDF`（316,389 bytes，1 页，SHA `cb1932723f989bf4b0f6859af7a40880f54252b5d3dfe00aa6cf1aacfe91e5b4`）。正文找到冻结标题，身份/哈希头、no-store 均正确；PDF 未落盘。
- 独立评审发现并修复非法坐标导致状态 500/布尔坐标放行、并发 WAL 写入导致旧事务校验结果误缓存；16 项独立回归通过。
- 真实负载发现全量记录校验内存放大，改为流式校验并修正空 WAL 缓存签名；恢复目录后按当前内容仓库定位原件，保留历史获取事件原文。

## 浏览器与最终回归

真实浏览器在运行中的本机 API/Web 上完成 SEA、JFK 两项验收，未替换官方记录或 PDF：

| 机场 | 搜索与地图 | 航图阅读 |
| --- | --- | --- |
| SEA / KSEA | FAA 与显式 ICAO 搜索；中心移至纬度 47.44988888、经度 -122.31177777，Z10；点击实际机场点重新打开资料。 | 64 条目录记录；选择 ILS OR LOC RWY 16C，PDF.js 显示 1 页；核对实际画面与标题。 |
| JFK / KJFK | 中心移至纬度 40.63992805、经度 -73.77869222，Z10；实际机场点可点击；来源显示 NAD83。 | 38 条目录记录；选择 VOR OR GPS RWY 13L/R，PDF.js 显示 1 页；核对实际画面与标题。 |

两项真实浏览器测试均通过（38.2 秒）。测试断言实际 canvas 中有非背景像素，检查发布/航图身份及 SHA 响应头，未发现页面控制台错误。主任务另在用户现有页面中完成 SEA → KJFK 切换，确认旧 PDF 清除、地图中心变化、官方标题正确；缩放 100% → 125%、适应宽度与桌面分栏键盘调整可操作。官方新窗口链接保留。

截图保存在本机 `apps/web/test-results/`：`live-sea.png`、`live-sea-pdf.png`、`live-jfk.png`、`live-jfk-pdf.png`。它们是验收输出，不进入 Git。合成两页 PDF 单独用于验证翻页、错误状态及旧图清除，不代替真实航图验收。

| 检查 | 命令（仓库根目录，PowerShell） | 结果 |
| --- | --- | --- |
| Python 全套 | `.venv/Scripts/python.exe -m pytest` | 239 passed |
| Python 静态检查 | `.venv/Scripts/python.exe -m ruff check .` | 通过 |
| 最终机场范围查询优化回归 | `.venv/Scripts/python.exe -m pytest tests/test_snapshot_api.py tests/test_snapshot_review.py` | 19 passed |
| 前端行为 | `npm run test:web` | 8 个文件，56 passed |
| 前端静态检查与构建 | `npm run lint`；`npm run build` | 通过 |
| 隔离浏览器验收 | `npm run test:e2e` | 最终 3 passed（30.7 秒）；本地两页 PDF 实际渲染、翻页、缩放、失败、版本清理与窄窗口真实滚动 |
| 真实浏览器验收 | `$env:FLIGHTMAP_LIVE='1'` 后执行 `npm run test:e2e`，完成后 `Remove-Item Env:FLIGHTMAP_LIVE` | SEA/JFK 2 passed |

API 运行时使用现有 `.venv` 执行检查，避免 `uv run` 在 Windows 上重装正在运行的入口可执行文件。官方网络检查独立于固定样本 CI。

最终窄窗口人工检查发现原滚动容器随内容增高，导致 519×642 窗口的资料面板难以通过鼠标到达。已将工作区限制在视口高度并提供自身滚动，窄屏地图随页面排列，鼠标滚轮用于页面滚动，地图缩放按钮继续可用。新增测试用鼠标在地图上滚动，断言工作区实际滚动且地图缩放不变；PageDown 到达目录，Tab/Enter 操作翻页并实际显示第二页。测试不使用 `scrollIntoView` 或写入 `scrollTop` 代替用户操作。截图为 `apps/web/test-results/research-narrow-519.png`，已核对页眉下的 PDF 控件和第二页内容；补修后 3 项隔离浏览器测试、lint 与 build 全部通过。

主任务重新加载用户现有 519×642 页面，使用 KJFK 搜索和实际鼠标滚动进入机场资料，再次读取并显示真实 `00610VG13LR.PDF`。已目视确认官方 VOR or GPS RWY 13L/R 标题、机场名称及航图内容；用户页保留在可继续阅读的位置。

## 真实资料副本生命周期演练

`scripts/verify_research_lifecycle.py` 使用完整真实数据副本演练，结果保存于 `.cache/research-lifecycle-report.json`，10/10 通过：

1. 重复构建返回同一快照 ID，输入数仍为 19,411，获取事件保持 3 条。
2. 关闭后重新打开仓库，活动快照及资料可读。
3. 未来日期只能显式预览，激活返回 409。
4. UTC 日历日期变化只改变研究分类，精确有效期仍 unknown；严格 d-TPP 在 09:01 前仍拒绝 Current 读取。
5. 到预计更新日显示提醒，研究快照仍可明确标注后读取。
6. 用解析器版本变化模拟更正版，切换后旧活动请求返回 409；这不是新获取的 FAA 官方更正，原件保持不变。
7. 撤销并重新打开仓库后，目标返回 410，活动指针不回退。
8. 副本原件损坏后，读取、激活及重建均被拒绝。
9. 原严格 d-TPP Current 保持不变。
10. 演练前后正式数据库表及原件哈希一致。

成功演练的临时副本已清理。较早一次运行遗留的 `.cache/research-lifecycle/audit-1kk51yi6` 清理被自动审批拒绝，给出的理由仅为 `blocked by policy`；已保留，没有改用其他删除方式，不影响正式数据。

## 负载与交付范围

机场地图查询先在 SQLite 按范围筛选，并从地图载荷中省略 `raw_fields`；完整原始字段仍由搜索/资料记录保留。真实 JFK 范围查询返回 33 个机场（含 JFK），耗时 0.91 秒；热状态读取 0.08 秒。这是本机单次观测，不是性能保证。

本轮完成的范围为 NASR 日期级研究机场与同日期 d-TPP 航图阅读。NASR 不被提升为精确有效 Current。跑道、导航点、航路及 CIFP 真实程序仍遵循各自独立的证据、实现和验收计划。
