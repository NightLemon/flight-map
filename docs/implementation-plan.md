# Flight Map 实施台账（A01–H10）

本文件保留批准计划的全部独立任务编号，记录代码已做到哪里，以及下一位实现者仍需什么。目标为美国 FAA 资料的本机研究平台：SQLite、本地原件、只读 API、MapLibre、官方 PDF 对照；所有导入仅生成候选，Current 通过显式 CLI 提升。

截至 2026-09-07，真实 d-TPP 2609 已自动获取、构建并由主任务显式提升为 Current，支持独立机场搜索与航图目录。NASR 已完成真实 19,411 条机场解析，但精确 UTC 产品有效期没有得到官方证据支持；CIFP 协议、完整语义及真实程序验证仍阻断。不能将纯几何引擎或合成样本标记为真实航空程序闭环完成。

## 状态与验证约定

- **tested（已实现并验证）**：所列范围已有明确执行过的验证；不扩大到本行未覆盖的真实数据能力。
- **implemented（已实现）**：代码或文档已具备；本行完整验收尚未确认。
- **partial（部分完成）**：已交付一部分，剩余项在最后一列明确列出。
- **blocked（被前置条件阻断）**：缺少必要证据或输入；不得猜测后继续，也不得标完成。

表内命令别名均从仓库根目录执行。测试使用合成小样本，真实原件不提交 Git。这里列出每张卡的检查入口；已经确认的范围以各行状态为准，最终全量结果、浏览器实测及代码快照由主任务的最终验证记录统一给出，避免将一条命令的存在等同于验收通过。

| 别名 | 检查命令 / 验收方式 |
| --- | --- |
| BASE | `uv run pytest tests/test_registry.py tests/test_models.py tests/test_airac.py tests/test_pipeline.py` |
| STORE | `uv run pytest tests/test_storage.py` |
| API | `uv run pytest tests/test_api.py tests/test_research_api.py` |
| AUDIT | `uv run pytest tests/test_release_audit.py`；检查发布持久化、读取结束二次门禁、原始腿顺序；本表不代替最终运行报告。 |
| ACQUIRE | `uv run pytest tests/test_acquisition_build.py tests/test_acquisition_discovery.py tests/test_acquisition_download.py tests/test_faa_discovery.py tests/test_download.py` |
| PARSE | `uv run pytest tests/test_parsers_faa.py` |
| CIFP | `uv run pytest tests/test_cifp.py`；结构读取/阻断边界，不是正式 CIFP 发布验收。 |
| GEO | `uv run pytest tests/test_geometry.py`；纯 WGS84 IF/TF 引擎、断线与原始顺序规则。 |
| WEB | `npm run test:web`；Vitest 行为断言。 |
| E2E | `npm run test:e2e`；默认隔离合成数据浏览器验收。 |
| LIVE-DTPP | `uv run flightmap-ingest update --product dtpp`；真实首次 staged、重复 unchanged；`uv run flightmap-ingest report --release-id <update返回的release_id>` 给出 27,428 输入 / 27,416 成功 / 12 不支持 / 0 错误。 |
| LIVE-NASR | `uv run flightmap-ingest update --product nasr`；真实获取与解析成功，随后 needs-user-action；原件及 19,411 / 19,411 / 0 / 0 报告已保留，不生成猜测时刻发布。 |

发布 2609 的已核实区间是 d-TPP XML 给出的 `[2026-09-03T09:01Z, 2026-10-01T09:01Z)`。它不适用于推断 NASR。12 条 DAU 类别在目录中保留为不支持警告。3197 个机场目录节点没有坐标，能力名为 `airport-catalog`；不会冒充机场地图图层。

代码入口采用以下目录简称：`schema/` 表示 `packages/schema/src/flightmap_schema/`；`storage/` 表示 `packages/storage/src/flightmap_storage/`；`ingestion/` 表示 `services/ingestion/src/flightmap_ingestion/`；`web/` 表示 `apps/web/`。界面组件单文件名均位于 `apps/web/src/`。API 的完整路由前缀为 `/api/v1`，函数和字段名以 [接口契约](interface-contract.md) 与实际模型为准。

## A：依据与执行基线

| 编号 | 状态 | 实际交付 / 实现入口 | 验证与未完成前置 |
| --- | --- | --- | --- |
| A01 | tested | Git 基线与 `codex/local-research-platform`；`.gitignore` 排除 data/.cache/原始 ZIP/PDF。 | 已形成可回退的小提交；只提交源码、文档和合成样本。 |
| A02 | implemented | 本台账、`docs/task-card-template.md`、共享 schema/research 契约。 | 每项按独立编号领取；接口变更必须先由主设计者冻结。 |
| A03 | partial | `docs/source-evidence.md` 固定 NASR 页面、免费获取依据、CSV layout、哈希、字段和真实预期。 | PARSE、LIVE-NASR；仍缺 NASR 精确 UTC 起止依据。 |
| A04 | tested | d-TPP XML/Definitions、字段、类别、官方 PDF 地址、根属性有效期与真实样本。 | PARSE、LIVE-DTPP；已核对一张官方 PDF HTTP 200。 |
| A05 | partial | `docs/cifp-support.md` 固定官方 Readme、公开结构参考、版本例外和保守支持边界。 | CIFP；协议未处理，完整标准与真实样本仍缺。 |
| A06 | partial | `tests/fixtures` 仅 synthetic；真实 NASR/d-TPP 结果与 JFK 图纸样本记入 source-evidence。 | NASR/d-TPP 解析真实预期已验证；CIFP 真实 SID/STAR/进近黄金样本被阻断。 |

## B：底座

| 编号 | 状态 | 实际交付 / 实现入口 | 验证与未完成前置 |
| --- | --- | --- | --- |
| B01 | tested | `schema/registry.py`、`models.py`；注册表版本和来源/产品唯一性校验。 | BASE。 |
| B02 | tested | `LocalAccessPolicy` 独立于再分发；`sources/us/faa.yml` 保留来源证据。 | BASE、STORE；未知权限与 CIFP 协议不会自动允许。 |
| B03 | tested | AIRAC 仅作日历/标签；产品模型必须带时区，API/门禁可注入 clock。 | BASE、API；NASR 未知时刻依然阻断。 |
| B04 | tested | `schema/publication.py`、`ingestion/pipeline.py` 共用发布门禁。 | BASE、STORE；未来、过期、身份错配、两处 issues 均检查。 |
| B05 | tested | 每阶段 handler 必须产出真实必要字段，CLI 保存 `data/runs/*.json`。 | BASE、ACQUIRE；终态不可推进。 |
| B06 | tested | 下载器仅读取 512 字节文件头，流式哈希、大小上限、ZIP 校验、失败清理。 | ACQUIRE；大文件不整体 read_bytes。 |
| B07 | tested | `storage/migrations/001_initial.sql` 和 SQLite 迁移入口。 | STORE；重复初始化不破坏，未知版本拒绝。 |
| B08 | tested | SHA-256 原件仓库、独立 acquisitions 获取事件和 final_url。 | STORE、ACQUIRE；相同内容去重，事件保留。 |
| B09 | tested | 多输入发布、记录、验证报告、输入身份与溯源完整性持久化。 | STORE、ACQUIRE；当前 d-TPP 的目录 XML 是唯一解析原件。 |
| B10 | tested | SQLite 事务提升/撤销、Current 指针和读取时复核。 | STORE；失败不替换指针，重启可恢复。 |

## C：产品获取

| 编号 | 状态 | 实际交付 / 实现入口 | 验证与未完成前置 |
| --- | --- | --- | --- |
| C01 | tested | `ingestion/faa.py` 的 candidate kind/role 区分资产、文档、产品页和协议。 | ACQUIRE。 |
| C02 | tested | NASR 当前/预览子页与单独 APT CSV ZIP；排除测试包及非官方链接。 | ACQUIRE、LIVE-NASR。 |
| C03 | tested | d-TPP Search 子页实际 XML 链接；不默认获取巨大 PDF ZIP。 | ACQUIRE、LIVE-DTPP。 |
| C04 | tested | CIFP I agree 标记 agreement/needs-user-action，不跟随。 | ACQUIRE；没有接受协议。 |
| C05 | tested | 下载内容进入 store_asset，记录官方/最终 URL、UTC 获取时间、哈希、大小。 | STORE、ACQUIRE、LIVE-DTPP。 |
| C06 | tested | `import-local` + `ImportManifest`；产品、来源、版本及原件校验共用构建路径。 | ACQUIRE；CIFP 仍先检查处理权限。 |
| C07a | blocked | NASR EFF_DATE 读取已实现，但只有日期不能创建精确 UTC 区间。 | 需要 NASR 官方起止时刻证据；禁止套用 CIFP/d-TPP 的 09:01。 |
| C07b | tested | `dtpp_validity` 从 XML root 读取周期、开始和结束时间。 | PARSE、ACQUIRE、LIVE-DTPP；manifest 冲突拒绝。 |
| C07c | partial | `parse_cifp_validity` 读取 Readme 的 Volume 与明确 HHMMZ 日期。 | CIFP；尚无已授权原件获取与官方证据绑定的真实候选闭环。 |

## D：机场地图闭环

| 编号 | 状态 | 实际交付 / 实现入口 | 验证与未完成前置 |
| --- | --- | --- | --- |
| D01 | tested | `ingestion/nasr.py` 读取 APT_BASE CSV，保留所有原字段和记录位置。 | PARSE、真实 19,411 条。 |
| D02 | tested | SITE_NO+TYPE 身份、原始 FAA/ICAO 标识、有限坐标及 NAD83 属性。 | PARSE；不补造 ICAO，不删除 FAA 目录中的境外记录。 |
| D03 | tested | 坐标无效、身份冲突、必需字段与日期冲突明确报告。 | PARSE；计数覆盖成功与错误。 |
| D04 | partial | `acquisition.build_local` 可通过 manifest 构建候选；自动 NASR 获取保留解析报告。 | ACQUIRE；真实 NASR stage/Current 等 C07a。 |
| D05 | tested | API `/status` 从 SQLite 返回真实发布、精确区间和状态。 | API、实际 d-TPP Current；NASR 不伪装可用。 |
| D06 | tested | `/coverage` 返回来源、状态、验证计数、最近尝试及具体阻断原因。 | API；真实 NASR 时间缺失原因已记录。 |
| D07 | tested | `/features?layer=airports&release_id=...&bbox=...` 有界查询。 | API 的持久化合成机场；真实 NASR 图层验收等 C07a。 |
| D08 | tested | 按官方标识/ICAO/名称搜索，返回来源作用域 ID。 | API；d-TPP 的无坐标目录机场已可搜索。 |
| D09 | tested | `web/src/App.tsx` 接真实状态、覆盖、加载/空/离线状态。 | WEB、E2E；最终真实浏览器结果由总验收记录。 |
| D10 | partial | `AviationMap.tsx` 可显示 API 机场点与来源/有效期。 | WEB、E2E 合成数据；真实 NASR 坐标图层仍等 C07a。 |
| D11 | partial | 搜索结果可选择并定位有坐标的机场，无坐标目录机场明确显示资料。 | WEB、E2E；真实 NASR 搜索→定位验收仍等 C07a。 |

阶段 D 的工程接口已具备；“真实机场地图完整交付”仍未达到，不能用 d-TPP 无坐标目录替代该验收。

## E：航图研究流程

| 编号 | 状态 | 实际交付 / 实现入口 | 验证与未完成前置 |
| --- | --- | --- | --- |
| E01 | tested | `ingestion/dtpp.py` 解析 XML、机场目录、官方类别与图纸字段。 | PARSE、LIVE-DTPP；删除记录保留但无 PDF URL。 |
| E02 | tested | d-TPP 真实候选、输入 XML、所有目录记录与报告落入 SQLite。 | STORE、LIVE-DTPP。 |
| E03 | tested | `/airports/{faa_ident}/charts` 按指定 d-TPP release 返回机场图纸。 | API；实际 JFK 的目录含 38 条记录。 |
| E04 | tested | `ChartPanel.tsx` 按机场/类别列图纸、显示周期。 | WEB、E2E；含 SID/STAR/进近独立图纸。 |
| E05 | tested | 原生 iframe 并排对照与始终存在的 FAA 官方新窗口链接。 | WEB、E2E；官方 PDF 地址样本 HTTP 校验通过。 |
| E06 | tested | PDF 失败/加载超时/缺同周期资料给出明确状态，不猜最新版本。 | WEB、E2E；跨域 PDF 渲染仍取决于浏览器及 FAA 响应。 |

## F：CIFP 结构化资料

| 编号 | 状态 | 实际交付 / 实现入口 | 验证与未完成前置 |
| --- | --- | --- | --- |
| F01 | tested | `ingestion/cifp.py` 固定 132 字符读取，ZIP 成员唯一选择与原始行留存。 | CIFP；坏长度报错，缺失记录不静默丢弃。 |
| F02 | tested | ARINC 坐标结构转换、南北/东西、边界及非法格式。 | CIFP；不把坐标转换成功等同于记录语义验证。 |
| F03 | partial | PA 机场结构字段可读取；原始标识保留。 | CIFP；没有正式机场发布能力，等 A05/A06。 |
| F04 | partial | PG 跑道结构字段可读取。 | CIFP；尚未验证跑道语义与正式图层，等 A05/A06。 |
| F05 | partial | D/DB 导航台结构字段可读取。 | CIFP；尚未建立可发布的导航台引用与语义。 |
| F06 | partial | EA/PC 航点结构字段和作用域身份可读取。 | CIFP；尚未建立可发布的唯一引用。 |
| F07 | blocked | 保留作用域字段，不按同名点合并；缺乏完整唯一引用解析规则。 | 需官方/授权字段标准、歧义样本及独立预期。 |
| F08 | partial | ER 航路原始顺序、方向和引用字段可读取。 | CIFP；未验证真正归组/连续性，不能发布航路线。 |
| F09 | blocked | 未生成正式航路几何。 | 先完成 F07/F08 的语义和真实相邻关系样本；不能按名字串线。 |
| F10 | partial | PD/PE/PF primary 与 continuation 原字段保留。 | CIFP；continuation 语义与归并仍待完整依据。 |
| F11 | blocked | 未把原始字段升级为可信 transition/主程序/复飞分支。 | Readme 明确 final/missed 可能共享 route type；必须补标准与黄金分支样本。 |
| F12 | partial | PD/SID 结构读取与合成测试存在。 | 真实 SID 分支、腿、唯一引用验收等 F07/F11/A06。 |
| F13 | partial | PE/STAR 结构读取与合成测试存在。 | 真实 STAR 分支、腿、唯一引用验收等 F07/F11/A06。 |
| F14 | partial | PF/进近结构读取与版本例外字段保留。 | 真实进近及复飞归组验收等 F07/F11/A06。 |
| F15 | tested | 每一原始帧记成功/不支持/错误；当前成功数为 0，并保留 evidence-incomplete 阻断。 | CIFP；结构可读帧计 unsupported，不能误标支持。 |
| F16 | partial | CLI 分派函数与持久化契约已接通，未授权处理先阻断。 | ACQUIRE；当前无可提升的真实 CIFP 候选。 |
| F17 | blocked | 航图保存 faanfd18 并始终可显示关联未确认。 | 自动精确程序关联尚无经过验证的规则；不得用名称相似代替。 |
| F18 | tested | 机场程序列表 API 已按发布 ID 和类别契约实现。 | API 合成记录；真实 CIFP 列表能力仍等 F12–F14。 |
| F19 | tested | 程序详情返回原字段、分支、腿与问题，独立于几何成败。 | API 合成记录；正式真实语义未完成。 |
| F20 | partial | API 图层查询支持 runway/navaid/waypoint/airway 类型。 | API；正式 CIFP 规范化记录与真实图层仍被阻断。 |

## G：有限几何与程序界面

| 编号 | 状态 | 实际交付 / 实现入口 | 验证与未完成前置 |
| --- | --- | --- | --- |
| G01 | tested | `geometry.py` 仅显示明确 unique 引用的 IF 点。 | GEO；纯引擎已验证，正式 CIFP 输入等 F07/F11。 |
| G02 | tested | TF 使用 GeographicLib WGS84；间隔≤1海里，跨 180° 精确拆段。 | GEO 独立赤道长度、跨日界线和边界样本；不声称包含飞行转弯预测。 |
| G03 | tested | 未支持腿、失败引用、不同分支/原件/程序均断线，不能跳腿连接。 | GEO；错误顺序不自行排序“修好”。 |
| G04 | tested | 几何 API 要求一个明确 branch_id，按原件位置保持原始邻接。 | API、GEO；AUDIT 增补读取/排序边界由最终报告确认。 |
| G05 | tested | `ResearchPanel.tsx` 单程序单分支选择；切换不混 transition。 | WEB、E2E 合成程序。 |
| G06 | tested | 程序腿表显示原字段、解析状态和问题。 | WEB、E2E 合成腿；真实程序仍被阻断。 |
| G07 | tested | 所选分支几何和缺口分别展示，切换清除旧内容。 | WEB、E2E；不将合成几何当航空验证。 |
| G08a | partial | 跑道图层开关和覆盖状态已接接口。 | WEB；等待正式跑道数据能力与真实验收。 |
| G08b | partial | 导航点/航点图层开关和覆盖状态已接接口。 | WEB；等待 F05–F07。 |
| G08c | partial | 航路图层开关和覆盖状态已接接口。 | WEB；等待 F08/F09。 |
| G09 | partial | 同周期航图选择与未确认时退回机场目录已实现。 | WEB、E2E；自动确定的程序→图纸关联等 F17。 |

阶段 G 的几何引擎和合成界面交互已实现；“真实一条 SID、STAR、进近几何与官方预期一致”的验收仍 blocked。

## H：生命周期与日常使用

| 编号 | 状态 | 实际交付 / 实现入口 | 验证与未完成前置 |
| --- | --- | --- | --- |
| H01 | tested | 页面固定各产品 release_id；发布切换清除并刷新整组资料。 | WEB、E2E、API；不会在请求中悄悄换新版本。 |
| H02 | tested | 所有默认数据入口验证到期、撤销、权限和 Current 指针。 | STORE、API；AUDIT 检查读取结束再次验证。 |
| H03 | tested | 前端到期定时、恢复前台与失败状态清理航空数据。 | WEB、E2E；保留参考地图及重试入口。 |
| H04 | tested | 显式 current/preview/history，状态标签醒目，不能用历史模式读取未经提升的当前候选。 | STORE、API、WEB；跨产品图纸不悄悄换成最新周期。 |
| H05 | tested | update 串联获取和构建、重复导入幂等、失败/需要人工输入保留原件/日志。 | ACQUIRE、LIVE-DTPP、LIVE-NASR；NASR/CIFP 阻断如实返回。 |
| H06 | implemented | `Repository.report` 与同来源、同产品中创建时间不晚于目标的最近另一候选比较，返回 previous_release_id 及 added/removed/changed；changed 比较同 ID 字段时忽略 provenance。 | STORE 已覆盖更正的新增/删除；完整差异用例以最终验收结果为准。无前一候选时以空集合比较，不依赖 Current 指针，不设猜测阈值。 |
| H07 | partial | API 显示最近尝试/最近发布，来源和官方更正入口可见。 | API、WEB；公告自动解析和紧急重建未纳入已完成能力。 |
| H08 | implemented | discovery CLI 网络失败默认非零，提供 --output 时保留 JSON；工作流 always 上传报告。 | ACQUIRE 验证本地失败报告；远程计划任务实际运行待 CI。 |
| H09 | implemented | README 已包含安装启动、数据/来源目录配置、更新、显式提升、撤销以及停止进程后复制整个数据目录的备份/恢复步骤；与 CLI 和接口契约已核对。 | 文档已完成；跨目录恢复是否通过以最终生命周期测试为准，未凭文档存在标 tested。 |
| H10 | partial | 持久化/重启/预览/边界/更正/撤销的合成测试，真实 d-TPP 重复获取及显式提升。 | 全产品真实周期演练未完成；NASR 等 C07a，CIFP 等 A05/A06/F07/F11。 |

## 下一轮的领取顺序和停止规则

1. 先解决 **C07a**：主设计者提供 NASR 产品官方精确 UTC 起止依据及明确可解析格式；在此之前只运行已有获取/解析，不添加时间常量。字段证据矛盾时保留文件哈希与引用，停止相关发布。
2. C07a 通过后，分别领取 **D04、D10、D11、H10 的 NASR 部分**。每张卡一个真实闭环动作，使用现有 Repository、API 和 UI，不扩展基础设施。
3. CIFP 必须先由用户按官方流程处理协议，随后主设计者冻结 **A05/A06/F07/F10/F11** 的合法资料、真实预期和分支判定；这些是解析前置，不能交给低能力模型自行推断。
4. 然后按 **F03→F04→F05→F06→F07→F08→F09→F10→F11→F12→F13→F14** 独立实现并测试。新标准与既有结构 reader 冲突时先更新支持文档和契约，不静默改原文。
5. 最后各自完成 **F16/F17/F20、G08a/G08b/G08c/G09、真实 G 验收、完整 H10**。几何必须保留已有 IF/TF 限制；任何新腿类型需新计划，不混入本轮。

每张任务卡按模板明确一个输出、1–3 个实现文件、固定输入和断言，执行后小提交。两轮修复仍失败交主设计者重新拆分。任何真实数据能力只在其真实验收通过后从 partial/blocked 改为 tested，不能因为 API、合成测试或界面存在就宣称完成。
