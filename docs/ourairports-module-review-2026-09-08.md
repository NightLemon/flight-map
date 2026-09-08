# OurAirports 可加模块调研（2026-09-08）

## 结论与推荐第一批

公开版已经具备机场搜索、按视野加载的机场/跑道/导航台，以及点击机场后按桶读取的频率和跑道详情；它不预加载全球图钉，内存最多保留 32 个数据文件。第一批应只做 **机场概览事实卡、跑道概览（明确 `closed`）和数据完整度提示（快照不是逐条更新时间）**。三者只消费已加载的详情，不增加默认图层、全局请求或移动端地图负担。`scheduled_service` 检索/筛选在复核 `no` 的时效含义后列为第二批。

不要把社区目录包装成运行资料。OurAirports 数据页说明 CSV 每夜生成、GitHub 只在内容变化时更新，且数据为 Public Domain、没有准确性或适用性保证；当前公开版锁定的上游提交为 `269b3557e2c784cc41673b77c7fae211d3f61668`，构建清单时间为 `2026-09-08T01:53:12Z`。以下“可用”均指该固定快照，不代表 AIRAC、生效状态或实时性。

## 已核对的数据边界

| 类别 | 原始 CSV / 网页实际内容 | 当前导出 | 当前 UI | 不能据此声称的内容 |
|---|---|---|---|---|
| 机场 | `airports.csv` 有名称、坐标、海拔、国家/地区、城市、`scheduled_service`、ICAO/IATA/GPS/local code、`home_link`、`wikipedia_link`、`keywords`。 | 以上字段均保留在机场详情；搜索索引另保留标识、城市、类型、`scheduled_service`、别名。 | 右栏结构化展示名称、城市/国家、OurAirports 链接；通用地图属性最多显示 12 项，非面向机场的事实卡。 | 航班时刻表、承运人、航线、登机口、实时运行。 |
| 通信频率 | `airport-frequencies.csv` 仅是一条机场语音通信频率：关联机场、类型、描述、MHz。字典明确说类型尚非受控词表，同一频率可因功能重复。 | 导出为 `service`、`frequency`、`unit=MHz`、`remarks`，在机场详情按需读取。 | 已有“常用通信频率”模块和排序。 | **不是实时 AIS/航行情报服务，也不是实时 ATC 状态、NOTAM、ATIS 内容或可用性。** |
| 跑道 / 起降面 | `runways.csv` 包括长度、宽度、表面、灯光、`closed`、两端编号/坐标/真航向等；一行也可能是直升机坪或水道。 | `runway_properties` 保留长度、宽度、表面、灯光、`closed`、端编号/海拔/真航向/阈值；端点坐标只在两端齐全时写进 `geometry`，没有作为 properties 保留。 | 已列出跑道端名、长度和表面；地图 Z10 才加载。 | 仅凭长度/航向推断的端点、可用跑道、跑道方向、性能或净空结论。 |
| 导航台 | `navaids.csv` 有类型、频率、坐标、DME 字段、功率和可选 `associated_airport`。 | 已导出为独立导航台图层；`associated_airport` 仍是原始机场 `ident` 字符串。 | 已有 Z6 导航台图层和通用要素属性。 | 实时台站状态、航路/程序关系、运行可用性。 |
| 机场网页的更新时间与官网 | 逐机场网页确实会显示 “Last updated”；抽查 [ZBAA](https://ourairports.com/airports/ZBAA/) 为 `2026-02-23 15:25:18`，并显示 Web site `https://en.bcia.com.cn/`。CSV 的 `home_link` 是“官方主页 URL（若有）”。 | `home_link` 已导出；没有逐机场 `last_updated` CSV 字段，也未导出该网页值。 | 已有 OurAirports 机场页链接，未直接显示 `home_link`。 | 一个可批量、稳定的逐机场更新时间 API；除非先另行核实端点和许可，不能抓取网页来充当详情接口。 |

### `closed` 的实际核对

机场关闭状态属于 `airports.csv.type`，不是机场行中的布尔 `closed` 字段。数据字典目前列出 `closed_airport`，但固定 CSV 的中国行实际取值是 `closed`；现有生成器也以 `type != "closed"` 排除机场。实施时必须以锁定输入的实际枚举做校验，不能只照字典改成 `closed_airport`。跑道/起降面的 `closed` 则是独立的 `0/1` 字段，含义是该 surface 当前关闭；它不等价于整个机场关闭，也不构成实时状态。

## 中国（`iso_country=CN`）快照可用率

以下统计直接读取锁定快照的四个 CSV，按现有可显示条件（有效坐标且 `type != closed`）计 711 个设施；总中国行 779，其中 68 个 `type=closed`。这不是另一份主审计统计，只用于决定模块的降级显示。

| 字段 / 关联 | 可用量 | 模块含义 |
|---|---:|---|
| 名称、类型、`iso_region`、`scheduled_service` | 711/711；其中 `yes` 264、`no` 447 | 前三项可作为详情事实；`iso_region` 尚未写入 `AirportHit` 或 `search/{ISO2}.json`，不能直接做现有搜索结果分组。`scheduled_service` 不可解释为时刻表。 |
| 城市、海拔 | 692/711；452/711 | 城市缺失显示“未提供”，海拔做可选行。 |
| ICAO / IATA / GPS / local code | 294 / 319 / 315 / 14（各 /711） | 最多显示非空代码，不能假定 ICAO 或 GPS 必有、唯一或相同。 |
| 官网 / Wikipedia / keywords | 28 / 322 / 160（各 /711） | 官网是待核实的来源链接，仅在 `http`/`https` URL 解析成功时显示；名称搜索仍可用 keywords。 |
| 频率 | 192 条，涉及 57/711 个设施 | 已有模块应继续显示“来源未提供”而不是空白或实时标签。 |
| 跑道记录 / 两端坐标均全 | 342 条、292 个设施 / 118 条 | 跑道文本概览覆盖比地图线高；地图不能补画其余 224 条。 |
| 导航台 / 关联机场 | 277 条 / 113 条 | 可做按需关联列表，但关联是字符串，须先验证一对一。 |

## 按价值排序的具体模块

### 1. 机场概览事实卡（第一批）

**交互：** 选中机场后，在现有右栏名称下显示设施类型、服务城市（若有）、海拔（若有）、非空 ICAO/IATA/GPS/local code；官网存在时给出“机场官网”外链，Wikipedia 放入“更多参考”。手机端默认折叠为两到三行摘要，点击展开。`home_link` 与现有 OurAirports 详情页链接应明确区分：前者是来源记录中的机场官网，后者是目录条目。

**字段与成本：** 使用现有 `AirportDetail.airport.properties` 的 `type`、`municipality`、`elevation_ft`、各 code、`home_link`、`wikipedia_link`；不需要新 CSV、索引、图层或网络请求。空字段隐藏，绝不从名称猜官网或代码。官网必须先以 `new URL(value)` 解析并仅允许 `http:` 或 `https:`，外链使用 `noopener noreferrer`；其他协议或无效值不渲染。因官网覆盖仅 28/711，它只是待用户独立核实的来源链接，不应占据卡片主位。

### 2. 跑道概览与来源状态（第一批）

**交互：** 在已有跑道列表顶部按需计算“记录 N 条 / 有地图端点 N 条”，显示最长记录长度、表面集合、夜间灯光记录数，以及“来源标为关闭的起降面 N 条”；展开后显示每条的两端编号、宽度、真航向和关闭标志。只有完整 `geometry` 端点的条目可提供“在图上定位”。

**字段与成本：** 现有详情可复用 `length_ft`、`width_ft`、`surface`、`lighted`、`closed`、端编号/海拔/真航向/阈值，以及完整时的 `geometry`。计算只在详情内存中进行，不能默认打开跑道层。中国 342 条中只有 118 条端点完整，且 3 条 `closed=1`；无端点时显示“来源未提供地图端点”，**不能按长度和真航向凭空画线**。由于生成器会在缺任一端时令 `geometry=null`，也没有在 properties 中保留原始单端坐标，若要展示任一单端坐标或为缺端做质量提示，必须先新增并验证相应导出字段。`closed` 是快照属性，应标“来源状态”，不表述为实时关闭。

### 3. 数据完整度与来源抽屉（第一批）

**交互：** 在详情页底部给出简短、可展开的“此条目录含：官网/频率/跑道记录/完整跑道端点”与原始文件、行号、SHA-256；展示当前快照日期，并继续链接到 OurAirports 条目。不要把页面的逐条 “Last updated” 放入这里，除非未来有经过验证的、可批量取得来源字段。关联导航台仍是第二批，现有机场详情不足以据此给出完整度结论。

**字段与成本：** 现有记录已有 provenance，详情文件已按需加载。完整度仅由已导出字段是否非空计算，不发新请求；可减少把缺失误读为否定事实。时间只能显示生成清单的上游快照时间，明确标作“来源快照”，不能伪装为机场资料更新时间。跑道的“完整端点”只能从非空 geometry 得出，不能声称识别了丢弃的单端坐标。

### 4. “定期航班服务”检索标识（第二批，先复核 `no` 标志）

**交互：** 在搜索结果和详情摘要中以“目录标记：有/无定期航空服务”显示 `scheduled_service=yes/no`。默认结果不能因 `no` 而自动排除；它可能滞后，应在先复核来源边界后再提供用户主动选择的筛选。手机端仅显示短标识，筛选置于搜索抽屉。

**字段与成本：** 搜索索引已含 `scheduled_service`，详情也保留它。只有在已完整读取所选国家的 `search/{ISO2}.json` 后，才可按“用户查询 + 筛选”过滤，随后排序，最后截取 50 条；不得先取现有结果的 50 条再筛选。字段覆盖 711/711，但它的定义仅为“目前有 scheduled airline service”；不得显示班次、目的地、运营航司、航班状态或“今日有航班”。

### 5. 机场关联导航台清单（第二批）

**交互：** 在选中机场的“附近/关联导航台”折叠区列出 NDB/VOR/DME 的 ident、类型、频率和“在图上查看”；默认不在地图加图钉。若无关联或匹配不唯一，显示“来源未提供可确认关联”。

**字段与成本：** 原始 `navaids.csv.associated_airport` 可与 `airports.csv.ident` 关联；当前导出保存该字符串但没有把导航台写入机场详情。应在构建时建立经验证的关联数组（明确处理一个 ident 对多机场、缺失与关闭机场），详情桶按需读取即可。中国有 113/277 个导航台带此字段，故模块需可缺失；它不应扩展成航路、程序或实时台站状态。

### 6. 地区（`iso_region`）结果分组（第二批）

**交互：** 用户进入国家搜索后，待搜索索引包含地区码，才可按 ISO 地区码折叠分组/筛选；优先显示代码，只有接入并锁定 `regions.csv` 后才显示地区名称。手机端作为搜索结果的二级过滤，不影响地图视野。

**字段与成本：** `iso_region` 已在所有 711 个中国可显示设施中存在，也在详情导出，却不在 `AirportHit` 类型或现有 `search/{ISO2}.json` 条目中。实施必须把它加入搜索索引和前端类型并重建数据，不能对 711 个机场逐条读取详情来分组。读取所选国家完整索引后，必须按“用户查询 + 地区筛选”过滤，再排序，再 `limit 50`；不能先截取 50 条。若需要中文地区名，必须新增 `regions.csv` 到锁定输入、哈希、许可/来源说明与生成索引，不能把 `CN-xx` 猜成文字名称。

## 实施前验收重点

1. 保持机场、跑道、导航台图层默认行为和缩放阈值；新增模块不能预取 `search.json`、全球瓦片或全量详情。
2. 用含/不含官网、频率、完整跑道端点、`scheduled_service=yes/no` 的固定 fixture 覆盖空值和文案；官网外链必须经过 URL 解析且只允许 `http:`/`https:`，并使用 `noopener noreferrer`。
3. 对 `type` 和跑道 `closed` 按锁定 CSV 做枚举断言；升级上游时重新核对字典与实际取值的差异。
4. `scheduled_service` 和地区筛选覆盖完整国家索引中的“过滤 → 排序 → 截取 50 条”；默认列表不得因 `scheduled_service=no` 消失，地区索引字段必须来自重建后的搜索条目。
5. 所有状态写为“目录标记”“来源未提供”或“快照”，并保留现有非运行用途声明；不新增任何实时、航班时刻、AIS、NOTAM、ATIS 内容、跑道推算或运行适用性表述。

## 来源（核对日期 2026-09-08）

- [OurAirports 数据下载与许可说明](https://ourairports.com/data/)：每日生成、文件清单、Public Domain 与无准确性保证。
- [OurAirports 数据字典：机场](https://ourairports.com/help/data-dictionary.html#airports)、[机场频率](https://ourairports.com/help/data-dictionary.html#airport-frequencies)、[跑道](https://ourairports.com/help/data-dictionary.html#runways)、[导航台](https://ourairports.com/help/data-dictionary.html#navaids)：字段语义与非受控词表说明。
- [锁定上游仓库 README](https://github.com/davidmegginson/ourairports-data/tree/269b3557e2c784cc41673b77c7fae211d3f61668) 与 [锁定 airports.csv](https://raw.githubusercontent.com/davidmegginson/ourairports-data/269b3557e2c784cc41673b77c7fae211d3f61668/airports.csv)：每日生成及本调研使用的输入版本。
- 本仓库 `scripts/build_pages_data.py`、`apps/web/src/PublicApp.tsx`、`apps/web/src/public-data.ts`、`apps/web/src/AirportCommunications.tsx`、`docs/github-pages.md`：当前保留字段、请求路径、UI 与性能边界。
