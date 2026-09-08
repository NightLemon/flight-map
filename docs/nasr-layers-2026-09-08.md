# NASR research-2 本机构建记录（2026-09-08）

本机已启用 FAA 2026-09-03 同版 NASR research-2，并完成真实 API、地图、机场通信及官方 PDF 的端到端验收。严格 d-TPP Current 保持原版本，CIFP 门禁保持原状。

## 构建结果

`.cache/nasr-layers-parser-check.json` 记录只读解析，`.cache/nasr-layers-build.json` 记录候选构建。两者的官方日期为 2026-09-03；构建结果为 `staged`，快照 ID 为 `nasr-research-2026-09-03-c6198d2904aabf8d15fe53fd`，`activation` 和 `promotion` 均为 `not-requested`。

之后单独执行 `activate-snapshot`，结果为 `active`，见 `.cache/nasr-layers-activation.json`。旧研究快照保留为历史版本。切换前 SQLite 在线备份及两类指针保存在 `.cache/before-nasr-layers-20260908T090040/`；原件未被覆盖，新增原件按 SHA 追加保存。d-TPP Current 仍为 `dtpp-2609-1c493184b1bc8a79edfc6a4c`。

| 项目 | 数量 |
| --- | ---: |
| 输入 | 174,220 |
| 成功 | 142,929 |
| 不支持 | 31,291 |
| 错误 | 0 |
| 机场 | 19,411 |
| 跑道 | 8,807 |
| 导航台 | 1,617 |
| 航点 | 70,089 |
| 航路 | 11,742 |
| 机场通信 | 31,263 |

核对样本：JFK 有 4 条跑道和 43 条频率记录；SEA 有 3 条跑道和 99 条频率记录。原始资产、完整 SHA 和官方 URL 见 [source-evidence.md](source-evidence.md)。

## 展示范围和限制

五个地图层是机场、跑道、导航台、航点、航路；机场通信在点击对应机场后显示。地图默认仅机场，每层最多 500 项；机场 Z8、跑道 Z10、导航台 Z6、航点 Z9、航路 Z5 后才按视野请求。

跑道几何只连接两个原始跑道端坐标。航路仅来自 AWY2 同序点，不跨显式 gap 或 dogleg，也不补上缺失点、坐标或未知顺序。FRQ 仅唯一关联 AIRPORT 设施；数值频率只接受 VHF 108–137 或 UHF 225–400，`R` 表示仅接收。用途、扇区、备注和原件溯源保持原字段。APT 标注 NAD83；其他层没有被赋予推断 datum。

## 实际验收

后端全套 326 项通过（`.cache/layers-python-final.log`）；随后修正覆盖接口回归测试的 spy 实例，4 项目标测试重新通过（`.cache/layers-coverage-test-verified.log`）。Web 共 78 项通过：本机两并发 fork 启动曾超时，46 项正常结束；对未启动的两个文件按单 worker 原断言复跑，32 项全部通过（`.cache/layers-web-final.log`、`.cache/layers-web-final-app.log`）。ruff、oxlint、生产构建通过。

合成浏览器 6 项原回归及 1 项新增图层/跑道点击测试通过。真实浏览器 4 项通过（`.cache/layers-e2e-live.log`）：纽约手动拖动和滚轮缩放自动加载；SEA/JFK 地图点重新打开、通信自动显示、官方 PDF 实际像素；纽约四个新增图层分别加载。截图保存在 `apps/web/test-results/live-new-york-all-layers.png`、`live-jfk-communications.png`、`live-sea-communications.png` 等本机文件。

真实 API 在纽约 bbox `-74.4,40.4,-73.5,41` 返回机场 66、跑道 15、导航台 6、航点 374、航路 52，全部为对应 kind 与有效几何。JFK 地面 `121.9 MHz`、SEA 地面 `121.7 MHz` 与原件一致；通信全部关联本快照机场且无地图几何。证据为 `.cache/nasr-layers-api-check.json`。

发现并修正多快照互相逐出校验缓存的问题，保留同一 DB/WAL revision 已验证的所有快照，原件仍逐次哈希。一次实测热状态从约 22 秒降至 0.238 秒；各层查询约 1.9–3.6 秒，时延随本机负载变化。`/coverage` 不再重复其不使用的研究校验。新实例三并发冷启动实测 `/status` 18.093 秒、`/coverage` 0.278 秒、`/sources` 0.038 秒，均 200（`.cache/layers-bootstrap-cold.json`）；页面仅给首次状态检查 60 秒时限，普通请求仍为 20 秒。

缺少坐标、不可确认的航路连续关系、机场关联或频率单位继续留在 unsupported 报告，不作为地图或通信记录展示。日期级研究不等于精确有效期已得到验证。
