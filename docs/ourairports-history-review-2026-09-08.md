# OurAirports 中国机场频率历史沿用审查（2026-09-08）

## 结论

无法用该库证明五年前沿用：指定的 GitHub Commit API 正常返回 HTTP 200，但在 `2021-09-08T23:59:59Z` 截止点前返回 `[]`。按授权执行的唯一回退（`until=2024-09-08T23:59:59Z`）则选出 `2024-09-07T07:53:31Z` 的提交 `3f60dc5657bc11bea69e865be4fb2e56a7fb490a`。比较这个近两年前的源码快照与固定 2026 快照，191/192 条历史行保持稳定频率 ID、稳定机场 ID 和规范三元组不变（99.48%）；按完整频率集合，55/58 个机场不变（94.83%，或历史有记录机场 55/56 = 98.21%）。

这只证明这 191 条频率**在两份源码快照中已存在且字段未变**，不是资料录入时间、某行最后核实时间或失效证据；同一机场行的更新也不能认证通信频率是否新鲜。未访问本机 FAA 数据库，未改公开数据或 UI。

## 可复现检索记录

| 项目 | 实际结果 |
|---|---|
| 核对日期 | 2026-09-08 |
| 五年前指定检索 URL | <https://api.github.com/repos/davidmegginson/ourairports-data/commits?path=airport-frequencies.csv&until=2021-09-08T23:59:59Z&per_page=1> |
| 五年前 HTTP 结果 / 响应 | 200 / `[]`（2 bytes）；只说明该库的该路径在此截止点无 API 可选提交，**不**说明所有历史 CSV 都不存在。 |
| 五年前 API 缓存与 SHA-256 | `.cache/mainland-review/ourairports-history/commits-airport-frequencies-until-2021-09-08.json` / `4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945` |
| 唯一回退检索 URL | <https://api.github.com/repos/davidmegginson/ourairports-data/commits?path=airport-frequencies.csv&until=2024-09-08T23:59:59Z&per_page=1> |
| 回退 API 选出提交 | `3f60dc5657bc11bea69e865be4fb2e56a7fb490a`，author/committer 日期均为 `2024-09-07T07:53:31Z`，message `data update`。 |
| 回退 API 缓存与 SHA-256 | `.cache/mainland-review/ourairports-history/commits-airport-frequencies-until-2024-09-08.json` / `58ecd16ecd91a1537f7ee09bdbf050a50fe199eb178995607ac12865a7f1bb84` |
| 回退历史频率 CSV | [airport-frequencies.csv](https://raw.githubusercontent.com/davidmegginson/ourairports-data/3f60dc5657bc11bea69e865be4fb2e56a7fb490a/airport-frequencies.csv)，缓存为 `.cache/mainland-review/ourairports-history/airport-frequencies-3f60dc5657bc11bea69e865be4fb2e56a7fb490a.csv`，1,244,582 bytes，SHA-256 `d24524b1092fa1a67d57c733f21fe9a99b4b0064102fe1ced0301ad4188e4b45`。 |
| 当前固定频率输入 | 上游 `269b3557e2c784cc41673b77c7fae211d3f61668` 的 [airport-frequencies.csv](https://raw.githubusercontent.com/davidmegginson/ourairports-data/269b3557e2c784cc41673b77c7fae211d3f61668/airport-frequencies.csv)，SHA-256 `785871bae512cd3d183288b4ba4639108cd4a8e8ab634d5fe3e491e4e516c740` |
| 当前固定机场输入 | [airports.csv](https://raw.githubusercontent.com/davidmegginson/ourairports-data/269b3557e2c784cc41673b77c7fae211d3f61668/airports.csv)，SHA-256 `ca72a3404144b9478f51ff145910f2533c18b02a2c77c4a59e8f2274674a26c0` |

回退仅此一次。没有请求更多日期、遍历提交历史或下载不由这两次 API 选出的原件。它不能补足五年前基线，只提供一个可核实的近两年前源码存在点。

## 比较范围与既定方法

“中国大陆”在本审查中只能机械地实现为固定 `airports.csv` 的 `iso_country=CN`；它不是行政地理判定。当前共有 779 个 `CN` 机场行，其中按公开版现有可显示条件（非 `type=closed` 且有坐标）为 711 个。频率范围使用前者的稳定机场内部 ID：`airport-frequencies.csv.airport_ref = airports.csv.id`。当前有 196 条频率行、关联 58 个 `CN` 机场；其中公开版可显示子集为 192 条、57 个机场。

本次以 2024 回退 CSV 实际执行如下判据：

1. 同一稳定频率 `id`、同一稳定机场 `airport_ref`；并以 `airport_ref` 加入当前 `airports.id` 的 `CN` 集合。
2. 三元组 `(type, description, frequency_mhz)` 相同，其中 `type`、`description` 去首尾空白、内部连续空白压缩为一个并 Unicode casefold；`frequency_mhz` 以 Decimal 规范为不带无意义尾零的十进制字符串。原值仍须保留用于展示和审计。
3. 频率行比例同时报告历史分母、当前分母和共同稳定 ID 分母；分子为上述三元组也相同的行。机场“完整集合未变”的分母为两个快照有记录机场的并集；只有该机场的稳定频率 ID 集合相同且每行均完全相同才计入。新增、删除、跨范围或不匹配 ID 分开列报，不能偷算为“相同”。

2024 历史范围有 192 条行、56 个机场；2026 当前范围有 196 条、58 个机场。192 个稳定频率 ID 共同存在，其中 191 条三元组未变、1 条变化：ZPJH（airport_ref `27213`）的 `51189` 从 `TWR | BANNA TWR | 130` 变为 `TWR | BANNA TWR | 118.6`。历史独有行 0；当前新增 4 行：ZPJH `597868`/`597869`、ZSJG `609756`、CN-0354 `610431`。因此未变行占历史 191/192 = **99.48%**、共同 ID 191/192 = **99.48%**、当前 191/196 = **97.45%**。55 个机场的完整频率集合未变，占机场并集 55/58 = **94.83%**、历史有记录机场 55/56 = **98.21%**、当前有记录机场 55/58 = **94.83%**。当前 196 条 `CN` 行也都是唯一 `(airport_ref, type, description, frequency)` 元组。

OurAirports 数据字典称机场和频率内部 `id` 会保持不变，即使机场代码或频率/描述改变；因此稳定 ID 可将“同一来源行”与“碰巧相同的文本”区分开来。字典同时说明频率 `type` 目前不是受控词表，且同一频率可在一个机场以不同功能重复，故三元组不能被简化为只比较 MHz。

## 指定实例：当前原值与历史值

五年前历史值仍为 `—（API 返回 []）`。下表改列实际取得的 2024 历史 CSV；每一项格式为 `type | description | frequency_mhz`，保留源 CSV 的原始大小写与空白。四个指定实例的所有稳定行均逐项相同。

| 机场（稳定 airport_ref） | 2024 历史 CSV 原值 | 2026 固定 CSV 原值 |
|---|---|---|
| ZBAA（27188） | `APP | BEIJING APP AREA 1 | 119.6`; `APP | BEIJING APP AREA 2 | 126.1`; `APP | BEIJING APP AREA 3 | 120.6`; `APP | BEIJING APP AREA 4 | 119.7`; `APP | BEIJING APP AREA 5 | 127.75`; `APP | BEIJING APP AREA 6 | 121.1`; `ATIS | BEIJING ATIS | 127.6`; `CLD | BEIJING DEL | 121.6`; `GND | BEIJING GND | 121.7`; `GND | GND EAST | 121.7`; `GND | GND WEST | 121.9`; `TWR | BEIJING EAST TWR | 118.5`; `TWR | BEIJING  WEST TWR | 124.3`; `TWR | RWY 01/19 TWR | 118.6` | 同左（14/14 行、稳定 ID 与规范三元组均相同） |
| ZGGG（27194） | `APP | GUANGZHOU | 120.4`; `ATIS | ATIS | 128.6`; `CLD | CLD | 121.95`; `GND | GND | 121.75`; `TWR | TWR | 118.1` | 同左（5/5） |
| ZWWW（27236） | `ATIS | ATIS | 126.7`; `GND | GND | 121.65`; `TWR | TWR | 118.1` | 同左（3/3） |
| ZUUU（27230） | `APP | CHENGDU APP AREA 1 | 125.6`; `APP | CHENGDU APP AREA 2 | 119.7`; `ATIS | ATIS | 128.6`; `GND | CHENGDU GND | 121.85`; `TWR | CHENGDU TWR | 123` | 同左（5/5） |

## 解释限制与后续条件

- [OurAirports 数据页](https://ourairports.com/data/)称下载文件每日生成，但 GitHub 只有内容变化才更新；这描述导出节奏，不给每条频率录入、核实或有效期。
- 本仓库当前导出把频率作为社区参考的 `service`、`frequency`、`remarks`，且 UI 已提示可能不完整；它没有逐行更新时间字段。机场网页的 “Last updated” 或 `airports.csv` 变更不能替代 `airport-frequencies.csv` 的行级证据。
- 频率记录是静态语音通信目录，非实时 AIS、ATIS 内容、NOTAM、ATC 状态或运行可用性。即使未来取得“完全相同”的跨年行，也只证明该两个源码快照的字符串和稳定 ID 未变，不能认证当前适航/运行有效。
- 本次百分比只对应 2024-09-07 与 2026 固定快照；要得到五年前比例，仍必须取得一个可验证、早于或等于 2021-09-08 的该文件提交 SHA 和其原始 CSV。没有该原件前，任何“五年前”百分比都是杜撰。

## 依据

- [GitHub Commit API（本次指定请求）](https://api.github.com/repos/davidmegginson/ourairports-data/commits?path=airport-frequencies.csv&until=2021-09-08T23:59:59Z&per_page=1)
- [GitHub Commit API（唯一 2024 回退）](https://api.github.com/repos/davidmegginson/ourairports-data/commits?path=airport-frequencies.csv&until=2024-09-08T23:59:59Z&per_page=1)
- [OurAirports 数据字典：机场频率](https://ourairports.com/help/data-dictionary.html#airport-frequencies)
- [OurAirports 数据页](https://ourairports.com/data/)
- [固定上游版本 README](https://github.com/davidmegginson/ourairports-data/tree/269b3557e2c784cc41673b77c7fae211d3f61668)
- 本仓库 `scripts/build_pages_data.py`、`apps/web/src/AirportCommunications.tsx`、`docs/github-pages.md`：当前公开导出与非运行用途边界。
