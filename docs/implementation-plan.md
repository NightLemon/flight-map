# Flight Map 实施台账（A01–H10）

本文件保留批准计划的全部独立任务编号，记录代码已做到哪里，以及下一位实现者仍需什么。目标为美国 FAA 资料的本机研究平台：SQLite、本地原件、只读 API、MapLibre、官方 PDF 对照；所有导入仅生成候选，Current 通过显式 CLI 提升。

截至 2026-09-08，批准的 R01–R21 日期级研究方案已接通真实机场地图、搜索定位、来源资料和页面内官方航图阅读。已激活 2026-09-03 NASR 快照，19,411 条机场记录、0 解析错误；原 d-TPP 2609 Current 保留。SEA/JFK 真实浏览器流程已通过，完整证据见 [09-08 验收记录](verification-2026-09-08.md)。

机场默认按日期级研究使用，精确 UTC 有效期仍为 unknown；研究指针与严格 Current 独立。下面 A01–H10 保留原精确有效期资料计划的范围，日期级研究的替代交付以 R01–R21 台账为准。CIFP 协议、完整语义及真实程序验证仍待独立推进，不能将纯几何引擎或合成样本标记为真实航空程序闭环完成。

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
| LIFECYCLE | `uv run pytest tests/test_lifecycle_acceptance.py`；固定差异样本、完整目录恢复、原件校验和周期/撤销演练。 |
| ACQUIRE | `uv run pytest tests/test_acquisition_build.py tests/test_acquisition_discovery.py tests/test_acquisition_download.py tests/test_faa_discovery.py tests/test_download.py` |
| PARSE | `uv run pytest tests/test_parsers_faa.py` |
| CIFP | `uv run pytest tests/test_cifp.py`；结构读取/阻断边界，不是正式 CIFP 发布验收。 |
| GEO | `uv run pytest tests/test_geometry.py`；纯 WGS84 IF/TF 引擎、断线与原始顺序规则。 |
| WEB | `npm run test:web`；Vitest 行为断言。 |
| E2E | `npm run test:e2e`；默认隔离合成数据浏览器验收。 |
| LIVE-DTPP | `uv run flightmap-ingest update --product dtpp`；真实首次 staged、重复 unchanged；`uv run flightmap-ingest report --release-id <update返回的release_id>` 给出 27,428 输入 / 27,416 成功 / 12 不支持 / 0 错误。 |
| LIVE-NASR | `uv run flightmap-ingest update --product nasr`；真实获取与解析成功，随后 needs-user-action；原件及 19,411 / 19,411 / 0 / 0 报告已保留，不生成猜测时刻发布。 |
| RESEARCH | `.venv/Scripts/python.exe -m pytest tests/test_research_snapshots.py tests/test_research_acquisition.py tests/test_research_online.py tests/test_research_cli.py tests/test_snapshot_migration.py tests/test_snapshot_api.py tests/test_snapshot_review.py`；研究快照、命令、迁移、读取门禁与并发。 |
| PDF | `.venv/Scripts/python.exe -m pytest tests/test_chart_pdf.py`；限定发布图纸、20 MiB/20 秒上限、类型/文件头与返回前复查。 |

发布 2609 的已核实区间是 d-TPP XML 给出的 `[2026-09-03T09:01Z, 2026-10-01T09:01Z)`。它不适用于推断 NASR。12 条 DAU 类别在目录中保留为不支持警告。3197 个机场目录节点没有坐标，能力名为 `airport-catalog`；不会冒充机场地图图层。

代码入口采用以下目录简称：`schema/` 表示 `packages/schema/src/flightmap_schema/`；`storage/` 表示 `packages/storage/src/flightmap_storage/`；`ingestion/` 表示 `services/ingestion/src/flightmap_ingestion/`；`web/` 表示 `apps/web/`。界面组件单文件名均位于 `apps/web/src/`。API 的完整路由前缀为 `/api/v1`，函数和字段名以 [接口契约](interface-contract.md) 与实际模型为准。

## R：真实机场与航图阅读

本轮遵循 [冻结契约](research-contract.md)。构建不自动激活，旧版/未来查询必须显式选择；严格 Current 的有效期门禁继续独立执行。真实 NASR 原件复用已登记 SHA，未重复下载或伪造获取事件。

| 编号 | 状态 | 实际交付 | 验收依据 |
| --- | --- | --- | --- |
| R01 | tested | 冻结 ResearchSnapshot、API、JFK 官方坐标与两页合成 PDF。 | schema、research-contract 与独立样本。 |
| R02 | tested | 编号迁移 002；研究表独立于原发布表。 | 旧库升级测试；真实升级前后原六张数据表逐表相等。 |
| R03 | tested | 快照、报告、输入获取记录与机场记录不可变保存；内容决定 ID。 | RESEARCH；真实重复构建 ID 不变、获取事件数不变。 |
| R04 | tested | 来源、报告、权限、撤销与原件完整性门禁。 | RESEARCH；独立并发评审与真实原件副本损坏检查。 |
| R05 | tested | 事务激活；未来/坏候选拒绝，失败保留旧指针。 | RESEARCH；真实快照显式激活成功。 |
| R06 | tested | 撤销与活动指针清理持久化。 | RESEARCH；真实资料副本撤销/重启演练。 |
| R07 | tested | `update --product nasr --research --asset-sha256 ...` 复用已登记原件。 | 真实 SHA 零下载构建；19,411 / 19,411 / 0 / 0。 |
| R08 | tested | 在线发现、获取、构建候选与研究获取尝试日志。 | `test_research_online.py` 固定网络样本；本轮真实构建使用 R07，不额外获取同一原件。 |
| R09 | tested | CLI 快照报告、激活/撤销入口；HTTP 完整报告与输入依据。 | CLI 互斥参数、完整计数/溯源测试；真实报告读回。 |
| R10 | tested | 活动/候选/未来/旧版/撤销状态与 28 天更新提醒。 | API 测试；真实副本日期边界演练，提醒不作失效时刻。 |
| R11 | tested | 指定 snapshot_id 搜索 FAA、显式 ICAO、名称。 | RESEARCH；真实 SEA/KSEA、JFK/KJFK 查询。 |
| R12 | tested | 指定快照的范围与跨 180° 机场 GeoJSON。 | 范围/跨界测试；真实地图查询与渲染，SQLite 先筛选范围。 |
| R13 | tested | 单次状态响应固定 NASR 快照与各发布；切换清空旧数据。 | WEB、E2E、409 与版本清理行为断言。 |
| R14 | tested | 真实机场点可点击；资料含官方日期、NAD83、原件及记录位置。 | SEA/JFK 实际机场点点击和来源人工核对。 |
| R15 | tested | 搜索机场后中心定位至真实坐标。 | JFK、KJFK、SEA 浏览器流程；Z10 和经纬度断言。 |
| R16 | tested | 使用明确 FAA 标识和相同官方日期查询航图目录。 | 日期不符不自动搭配；SEA 64 条、JFK 38 条。 |
| R17 | tested | 指定 d-TPP 图纸的内存 PDF 读取；无任意 URL/重定向。 | PDF 测试；两张真实 PDF 身份、文件头与 SHA 检查。 |
| R18 | tested | 固定本地 PDF.js 核心/worker/资源；页面渲染后才成功。 | WEB/E2E；SEA/JFK 非空 canvas、页数、标题人工核对。 |
| R19 | tested | 适应宽度、缩放、页码、翻页；切换立即清除旧画面。 | 两页合成 PDF 行为；真实航图缩放及适应宽度。 |
| R20 | tested | 桌面地图/航图可调分栏；窄屏地图和资料顺序排列，工作区可滚动。 | 桌面分栏通过；519×642 鼠标滚轮、PageDown、Tab/Enter 可到达并操作 PDF，缩放/翻页可读。 |
| R21 | tested | 完整升级备份、真实机场/航图浏览器与生命周期副本演练。 | 真实浏览器 2/2、生命周期 10/10；239 项 Python、56 项前端、3 项隔离浏览器及静态检查/构建通过，见 09-08 验收记录。 |

原件、本机截图及生命周期报告留在 data/.cache/test-results，不提交 Git。升级与回退步骤见 [本机操作](local-operations.md)；回退必须恢复升级前完整 data，旧程序不能直接读取 schema 2。

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
| B03 | tested | AIRAC 仅作日历/标签；严格产品模型必须带时区，API/门禁可注入 clock。 | BASE、API；NASR 未知时刻仍阻断严格 Current，独立日期级研究见 R。 |
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
| D04 | partial | 严格发布可通过 manifest 构建候选；日期级研究构建已通过 R07/R08。 | ACQUIRE、RESEARCH；真实 NASR 严格 Current 仍等 C07a。 |
| D05 | tested | API `/status` 从 SQLite 返回真实发布、精确区间和状态。 | API、实际 d-TPP Current；NASR 不伪装可用。 |
| D06 | tested | `/coverage` 返回来源、状态、验证计数、最近尝试及具体阻断原因。 | API、`uv run pytest tests/test_coverage_states.py`；区分未导入、失败、阻断和过期；有效 Current 不被单次更新失败隐藏。 |
| D07 | tested | 严格发布有界查询与独立 `/research/features` 均已实现。 | 严格接口用持久化合成机场；真实日期级机场地图验收见 R12/R14。 |
| D08 | tested | 按官方标识/显式 ICAO/名称搜索，返回来源作用域 ID。 | API、`uv run pytest tests/test_airport_ident_search.py`；不添加推测前缀，精确标识优先；d-TPP 无坐标目录已可搜索。 |
| D09 | tested | `web/src/App.tsx` 接真实状态、覆盖、加载/空/离线状态。 | WEB、E2E；最终真实浏览器结果由总验收记录。 |
| D10 | tested | `AviationMap.tsx` 显示真实 NASR 日期级研究机场点与来源/官方日期。 | WEB、真实 E2E；严格 NASR 有效期另等 C07a。 |
| D11 | tested | 搜索结果定位真实机场；无坐标目录机场明确显示资料。 | WEB、SEA/JFK 真实 E2E；日期级研究版本固定。 |

真实机场地图已按批准的日期级研究方案交付，使用 NASR 官方坐标；原严格 NASR Current 目标仍缺 C07a 的精确时间证据。

## E：航图研究流程

| 编号 | 状态 | 实际交付 / 实现入口 | 验证与未完成前置 |
| --- | --- | --- | --- |
| E01 | tested | `ingestion/dtpp.py` 解析 XML、机场目录、官方类别与图纸字段。 | PARSE、LIVE-DTPP；删除记录保留但无 PDF URL。 |
| E02 | tested | d-TPP 真实候选、输入 XML、所有目录记录与报告落入 SQLite。 | STORE、LIVE-DTPP。 |
| E03 | tested | `/airports/{faa_ident}/charts` 按指定 d-TPP release 返回机场图纸。 | API；实际 JFK 的目录含 38 条记录。 |
| E04 | tested | `ChartPanel.tsx` 按机场/类别列图纸、显示周期。 | WEB、E2E；含 SID/STAR/进近独立图纸。 |
| E05 | tested | 本机受限 PDF 读取与本地 PDF.js 实际渲染；FAA 官方新窗口链接保留。 | R17–R19；SEA/JFK 实际航图内容、页数与标题已验证。 |
| E06 | tested | PDF 失败/超时/缺同日期资料状态明确；切图取消旧请求并清空。 | WEB、E2E；FAA 跨域读取由受限本机接口处理。 |

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
| H05 | tested | update 串联获取和构建、重复导入幂等、失败/需要人工输入保留原件/日志。 | ACQUIRE、RESEARCH、LIVE-DTPP；日期级 NASR 可构建，严格 NASR/CIFP 门禁独立。 |
| H06 | tested | `Repository.report` 与同来源、同产品中创建时间不晚于目标的最近另一候选比较，返回 previous_release_id 及 added/removed/changed；changed 比较同 ID 字段时忽略 provenance。 | STORE、LIFECYCLE：固定新增/删除/变更分别为 1，只有溯源变化时为 0。无前一候选时以空集合比较，不依赖 Current 指针，不设猜测阈值。 |
| H07 | tested | API 和覆盖界面显示最近成功周期、精确有效期、获取失败原因及同来源官方更正公告入口。 | `test_coverage_states.py`、WEB：失败/隔离候选不覆盖最近验证通过的周期；过期成功记录不变成当前可用资料。 |
| H08 | implemented | discovery CLI 网络失败默认非零，提供 --output 时保留 JSON；工作流 always 上传报告。 | ACQUIRE 验证本地失败报告；远程计划任务实际运行待 CI。 |
| H09 | tested | README 包含安装启动、数据/来源目录配置、更新、提升、撤销、完整目录备份/恢复，与 CLI 和接口契约一致。 | CLI help、真实 API/Web 分别启动通过，dev.ps1 语法检查通过；LIFECYCLE 确认原目录不可用时仍可从新目录恢复并提升/撤销。 |
| H10 | partial | 持久化/重启/预览/边界/更正/撤销测试、真实 d-TPP 获取提升，以及真实资料副本的研究生命周期 10/10 检查。 | NASR 日期级研究部分通过 R21；全产品严格周期演练仍等 C07a 与 CIFP A05/A06/F07/F11。 |

## 下一轮的领取顺序和停止规则

2026-09-08 接手后的现状复核、S01–S04 可靠性工作及新增 NASR 跑道研究建议见 [接手分析与后续计划](takeover-2026-09-08.md)。新增路线仍须先完成字段依据与研究 schema 契约，不改变下述 CIFP 前置条件，也不把尚未验证的能力标记 tested。

1. 日期级机场与航图按 **R01–R21** 的独立契约维护，日常更新只生成候选，查看报告后显式激活。更新提醒不变成官方失效时间，失败不替换可读快照。
2. **C07a** 只阻断严格 NASR Current：主设计者提供官方精确 UTC 起止依据后，补足 D04 与 H10 的严格发布部分。它不再阻断已交付的日期级研究；不得添加猜测时间常量。
3. CIFP 必须先由用户按官方流程处理协议，随后主设计者冻结 **A05/A06/F07/F10/F11** 的合法资料、真实预期和分支判定；这些是解析前置，不能交给低能力模型自行推断。
4. 然后按 **F03→F04→F05→F06→F07→F08→F09→F10→F11→F12→F13→F14** 独立实现并测试。新标准与既有结构 reader 冲突时先更新支持文档和契约，不静默改原文。
5. 最后各自完成 **F16/F17/F20、G08a/G08b/G08c/G09、真实 G 验收、完整 H10**。几何必须保留已有 IF/TF 限制；任何新腿类型需新计划，不混入本轮。

每张任务卡按模板明确一个输出、1–3 个实现文件、固定输入和断言，执行后小提交。两轮修复仍失败交主设计者重新拆分。任何真实数据能力只在其真实验收通过后从 partial/blocked 改为 tested，不能因为 API、合成测试或界面存在就宣称完成。
