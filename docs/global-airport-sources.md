# 全球机场覆盖与来源扩展

核对日期：2026-09-08。区分已经导入的公开参考资料与待接入的国家官方产品；
社区目录和政府历史地理资料均不是当前 AIRAC 导航数据库。

## 已接入

- **OurAirports**：2026-09-08 固定上游版本，Public Domain。72,550 个有有效坐标、
  未标记关闭的航空设施，覆盖 247 个国家和地区。包含小机场、水上机场和直升机场，
  不是民航运输机场数量。坐标、跑道、导航台和频率保留该来源原值。
- **Wikidata**：2026-09-08 获取的 CC0 结构化名称快照。完整 P239 查询含
  20,578 个实体、22,825 行，规范化后保留 22,425 行供关联。
  为 209 个国家和地区的 **7,690 个机场**附加名称、中文别名和来源记录链接。
  这不是新增 7,690 个机场点，也没有增加或认证无线电频率。

许可和原件哈希在 [冻结清单](../reference-sources/catalog.json) 与
[Wikidata 快照说明](../reference-sources/wikidata/README.md)。构建复核全部 SHA-256，
不在浏览器或 CI 中实时查询 Wikidata。

只有两边 `(国家代码, ICAO)` 均唯一且坐标距离不超过 3 km 才关联名称参考。
4,378 行存在歧义、10,120 行未匹配、237 行坐标相距过远，均未附加。
关闭和缺坐标设施不参与关联。冲突不平均、不凭名称猜测、不覆盖主记录。

## 主要国家实际覆盖

“有频率”表示至少有一项来源记录，不证明完整、有效或适合运行；“补充名称”是本轮
成功附加 Wikidata 的机场数。全部计数来自固定源文件。

| 国家 | 可显示设施 | 有频率记录 | 补充名称 |
|---|---:|---:|---:|
| 中国 CN | 711 | 57 | 251 |
| 加拿大 CA | 2,481 | 642 | 364 |
| 英国 GB | 1,223 | 257 | 145 |
| 澳大利亚 AU | 2,683 | 1,439 | 444 |
| 法国 FR | 1,669 | 208 | 150 |
| 德国 DE | 1,318 | 510 | 235 |
| 巴西 BR | 7,712 | 165 | 265 |
| 印度 IN | 620 | 133 | 154 |
| 日本 JP | 3,328 | 111 | 93 |
| 俄罗斯 RU | 1,499 | 91 | 206 |
| 印度尼西亚 ID | 686 | 110 | 127 |
| 墨西哥 MX | 2,087 | 81 | 94 |
| 南非 ZA | 637 | 103 | 70 |

完整 247 个国家和地区的计数随 `reference/manifest.json` 发布，含设施、有频率设施、
关联跑道记录、导航台和补充名称数。国家下拉只限定机场搜索，选择机场后才定位地图。
默认概览不预加载图钉或搜索索引；国家浏览只读 `search/{ISO2}.json`。
检索支持原始 keywords 和补充名称，例如“北京大兴”，精确代码优先。

## 官方候选核查

以下尚未导入 Pages。须核对具体产品、适用许可、时间和字段，再完成解析与验收。
它们不改变 FAA 本机准入状态。

| 国家 / 范围 | 已确认入口与证据 | 当前处理 |
|---|---|---|
| 日本 / 全国历史资料 | [MLIT C28 空港データ](https://nlftp.mlit.go.jp/ksj/gml/datalist/KsjTmplt-C28-v3_0.html)，[GML/GeoJSON](https://nlftp.mlit.go.jp/ksj/gml/data/C28/C28-21/C28-21_GML.zip)。108 个机场、97 个标点，参考日 2021-12-31。产品标“商用可”，[条款](https://nlftp.mlit.go.jp/ksj/other/agreement.html)要求出处及加工说明。 | 优先作为明确标注 2021 年的独立参考；没有 ICAO/频率，不能凭距离静默并入机场。 |
| 法国 / Occitanie 区域 | [政府元数据](https://www.data.gouv.fr/api/1/datasets/5bd89db106e3e738f68c0ed2)，[GeoJSON](https://data.laregion.fr/api/explore/v2.1/catalog/datasets/aerodrome-occitanie/exports/geojson)。47 个场地；Etalab Licence Ouverte v2.0，目录修改 2026-09-01。 | 区域参考候选；没有 ICAO/频率，不能声称覆盖全法国。 |
| 澳大利亚 / 维多利亚州 | [Vicmap Lite Airport Point](https://www.data.gov.au/data/dataset/vicmap-lite-airport-point-1-250000-to-1-5000000)，[WFS](https://opendata.maps.vic.gov.au/geoserver/wfs?service=WFS&request=GetCapabilities)。203 个简化点；[CC BY 3.0 AU](https://creativecommons.org/licenses/by/3.0/au/)，数据日期 2021-09。 | 区域历史候选，不用目录 2026 年更新时间代替数据时点。 |
| 加拿大 / 历史地图 | [NRCan Airports (2006)](https://open.canada.ca/data/en/dataset/d6aae94f-8893-11e0-8646-6cf049291510)，[开放政府许可](https://open.canada.ca/en/open-government-licence-canada)。约 1,775 个设施的 2006 年栅格地图。 | 不转换为当前机场点；继续找结构化产品。 |
| 巴西 | [ANAC 机场登记](https://www.anac.gov.br/assuntos/setor-regulado/aerodromos/cadastro-de-aerodromos-civis)有公用/私用设施 CSV 的公开说明。 | 下载不稳定，原件与具体再分发条款未核实，保持仅链接。 |
| 印度 | [AAI AIM](https://aim-india.aai.aero/) 提供 eAIP；[OGD India](https://data.gov.in/search?query=airport) 门户有开放政府许可/API。 | 未锁定具体开放机场资源，不以门户许可替代产品证据。 |
| 中国 | [中国民航局](https://www.caac.gov.cn/) | 本轮未取得稳定下载且明确允许再分发的全国结构化机场/频率产品，不镜像。 |
| 俄罗斯 | [Росавиация](https://favt.gov.ru/) | 本轮访问超时，产品与许可证据不足，保持未知。 |

## 版本和验收

`source.revision` 保留 OurAirports 上游提交；`dataset_revision` 由导出语义版本、
主输入哈希与补充源清单共同计算，全部瓦片/国家索引/详情都位于此版本目录。
补充源更新也会切换版本，取消旧请求并清除旧详情，避免混版。

验证覆盖国家与全局索引一致、频率缺项计数、跨源唯一性、国家与坐标差异、许可拒绝和
输入篡改；浏览器覆盖国家分片、中国/印度机场、中文别名、排序、版本更新、图层与手机布局。
