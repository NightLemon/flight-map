# FAA 产品证据与解析边界

核对日期：2026-09-07。本文冻结本机研究解析依据；不授予产品再分发许可。测试仓库只包含明确命名的 synthetic 合成样本，真实 ZIP/XML/PDF 均在忽略的 `.cache/source-research/` 或 `data/` 中。

## NASR 机场

官方入口：<https://www.faa.gov/air_traffic/flight_info/aeronav/aero_data/NASR_Subscription/>。当前子页为 `2026-09-03`，预览子页为 `2026-10-01`；发现器只跟随页面实际列出的子页，不猜下载周期。

- 当前机场 CSV 包：<https://nfdc.faa.gov/webContent/28DaySub/extra/03_Sep_2026_APT_CSV.zip>，8,043,752 bytes，SHA-256 `d5e4c999d4c96ab4d66d8ce9a387de8ea59b5226a6144ea1ba58758ff29bbbd9`。
- README：<https://nfdc.faa.gov/webContent/28DaySub/2026-09-03/README.txt>，SHA-256 `b846654fd869ff98efaba45c30a5d39f2cb7c6237c843ab2f57c64500d062546`。原文：“All of the subscriber files are available free of charge ... It is not necessary to register in order to access or download the files.”
- 包内 `CSV_README.pdf`（SHA-256 `8f45dab9e7280456412f6a9cf70df5b6b886e78a4ddcbcb8d59e5626dcb555b2`）明确为内部和外部用户提供 CSV，并介绍数据使用方式。这是允许本地读取/处理的产品证据；`license_status` 的再分发审查状态保持不变。
- 包内 `APT DATA LAYOUT.pdf`（SHA-256 `c6c4240dd96864e854f76a0d0fd836ecf8bf137cf54518d37375f8287cc1318a`）与 `APT_CSV_DATA_STRUCTURE.csv` 冻结字段定义。PDF 明确 Ordered By 列表也是 Unique Record Key；APT_BASE 的键为 `SITE_NO, SITE_TYPE_CODE`。

| CSV 字段 | 解释与处理 |
| --- | --- |
| `EFF_DATE` | 官方订阅生效日期，格式 YYYY/MM/DD；必须与 manifest 日期一致。 |
| `SITE_NO`, `SITE_TYPE_CODE` | 官方设施身份；ID 使用来源、产品与这两个字段，不能只按名字合并。 |
| `ARPT_ID`, `ICAO_ID` | 官方位置标识和可空 ICAO；空 ICAO 不添加 K 前缀。 |
| `ARPT_NAME`, `CITY`, `STATE_CODE`, `COUNTRY_CODE` | 保留官方名称与覆盖元数据。 |
| `LAT_DECIMAL`, `LONG_DECIMAL` | 原始有符号十进制度，检查有限值与地理范围。 |
| 其余字段 | 在 `properties.raw_fields` 保留，尚未做运行意义解释。 |

官方 CSV README 明确 US coordinates reference **NAD83**。地图位置保留 `datum=NAD83`，不称其为测量级 WGS84 数据。FAA 目录还含境外设施；解析器保留官方全部记录及国家字段，不静默丢弃。

真实当前包解析预期：19,411 条机场，19,411 成功，0 不支持，0 错误。`JFK` 的 SITE_NO 为 `15793.`、TYPE 为 `A`、ICAO 为 `KJFK`、纬度 `40.63992805`、经度 `-73.77869222`。

**精确时刻仍被阻断。** 产品页、README、CSV_README 和 APT layout 确认 2026-09-03 生效以及 28 天发行周期，但未找到 NASR 产品的精确 UTC 生效/失效时刻。不能把 CIFP 或 d-TPP 的 09:01Z 套给 NASR，也不能把 AIRAC 日历零点冒充产品时间。

`update --product nasr` 自动发现、下载、校验、登记原件及完整解析报告后返回 `needs-user-action / validity-evidence-missing`，不构造具有猜测时间的发布集。取得 NASR 官方时刻依据后，可以给 `update --manifest ...` 或 `import-local --manifest ...` 提供 `ImportManifest`。必须填写 `source_id, product_id, source_url, airac, valid_from, valid_to, validity_evidence`；时间含时区，parser_version 为已安装版本 `0.2.0`。日期与 AIRAC 标签会交叉校验；产品有效期不能来自日历函数。

## d-TPP 航图目录

官方入口：<https://www.faa.gov/air_traffic/flight_info/aeronav/digital_products/dtpp/>。只跟随其实际列出的 Search 页面：<https://www.faa.gov/air_traffic/flight_info/aeronav/digital_products/dtpp/search/>。

- 当前 XML 的页面直接链接：<https://aeronav.faa.gov/d-tpp/2609/xml_data/d-tpp_Metafile.xml>，16,300,175 bytes，SHA-256 `f8a1b2042e82658b7eea2159de3ef699c318fc87e95b88099d66955864a3aa45`。
- 官方定义：<https://aeronav.faa.gov/dtpp/Metafile_XML_Definitions.pdf>，SHA-256 `16e704f7434b1ce0c4f75b6cec6b16d489ce3cd69d6c08dd2770485b7df55351`。原文明确：“You can open the XML in excel to view all the fields.” 结合官方提供的直接下载链接，允许目录在本机读取与处理；不推导 PDF 镜像或再分发许可。
- XML 根节点给出 `cycle=2609`, `from_edate="0901Z  09/03/26"`, `to_edate="0901Z  10/01/26"`。解析结果严格为 `[2026-09-03T09:01:00Z, 2026-10-01T09:01:00Z)`，不使用通用周期计算代替。
- 定义确认 `apt_ident` 是 FAA 机场 ID、`icao_ident` 是 ICAO ID；`chartseq` 排序、`chart_code` 类别、`pdf_name` 文件名、`useraction` 的 A/C/D 标记及 `faanfd18` 的 SID/STAR computer code。
- `DP`, `STR`, `IAP`, `APD`, `MIN`, `ODP`, `HOT`, `LAH` 的已确认含义映射到研究类别。当前 12 条 `DAU` 缺少充分分类依据，保留原文并记不支持警告；不捏造类别。
- `useraction=D` 的删除记录保留但 `pdf_url=null`，不会链接到 `DELETED_JOB.PDF`。
- 每个 airport_name 也生成无几何的机场目录记录，能力为 `airport-catalog`，不冒充机场坐标图层。这样可在 NASR 时间阻断时独立搜索机场并查看航图。
- 图纸链接使用官方目录模式 `https://aeronav.faa.gov/d-tpp/{cycle}/{pdf_name}`；文件名只允许 basename。已对 `2609/01244JALEX.PDF` 做官方 HTTP 校验，返回 200、application/pdf。不会默认缓存全量 PDF。
- 航图与程序相互独立；即使 `faanfd18` 存在，也先保留 `association_status=unconfirmed`。跨源关联要由独立的已验证规则决定。

真实数据预期：3,197 个机场目录节点、24,231 条航图记录，合计输入 **27,428**；成功 **27,416**、不支持 **12**、错误 **0**。147 条删除航图作为目录元数据保留。计数单位明确包含 airport_name 与其 record 子节点，每条输入均有独立溯源位置。

JFK 目录给出 KJFK、JOHN F KENNEDY INTL，含 38 条航图记录。独立核对样本：

| 类别 | 官方名称 | PDF | procuid | faanfd18 |
| --- | --- | --- | --- | --- |
| DP | DEEZZ SIX (RNAV) | 00610DEEZZ.PDF | 31763 | DEEZZ6.DEEZZ |
| STR | CAMRN FIVE | 00610CAMRN.PDF | 2848 | SIE.CAMRN5 |
| IAP | ILS OR LOC RWY 04L | 00610IL4L.PDF | 2830 | 空 |

这些是真实航图目录样本，不能当成已解析或已验证的 CIFP 程序腿与几何样本。

## CIFP

官方页面 <https://www.faa.gov/air_traffic/flight_info/aeronav/digital_products/cifp/> 明确要求接受 CIFP Error Notification Process；发现器将“I agree”链接标记为 `agreement / needs-user-action`，不跟随，不提交协议，不自动下载。来源注册表 acquisition/processing 均保持 needs-user-action。

公开字段、版本例外、结构读取边界和仍缺失的真实 SID/STAR/进近样本依据见 `docs/cifp-support.md`。尚不能将此能力标记完成；即便语法解析成功也不能发布成 Verified。

## 固定验证方法

- 离线行为测试：`uv run pytest tests/test_acquisition_build.py tests/test_acquisition_discovery.py tests/test_acquisition_download.py tests/test_parsers_faa.py`。
- 网络探测：`uv run flightmap-ingest discover-faa --product dtpp --output .cache/dtpp-discovery.json`；网络失败仍保留报告且默认退出非零。
- 真实目录闭环：`uv run flightmap-ingest update --product dtpp`，检查 `report --release-id ...`；重复执行应得到同一个 release_id 和 unchanged，Current 不因 update 改变。
- 每次本地构建保存 `data/runs/*.json`，记录真实阶段产物；报告与发布集持久化于 SQLite。提升、撤销分别使用显式 `promote`、`revoke` 命令。
