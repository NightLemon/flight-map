# Wikidata 机场名称参考快照

2026-09-08 从 Wikidata Query Service 获取，范围是具有 ICAO 属性 P239 的实体。
`airports.rq` 查询没有 LIMIT；22,825 个结果行对应 20,578 个实体。
`countries.rq` 查询国家 ISO 3166-1 alpha-2 属性 P297，用于关联而非自行推断国家。
保留原始 JSON 响应的 gzip 和 SHA-256，未抓取 Wikipedia 文章。

许可依据：<https://www.wikidata.org/wiki/Wikidata:Licensing>，同日核对：

> All structured data in the main, property and lexeme namespaces is made available under the Creative Commons CC0 License (Public domain).

CC0 法律文本：<https://creativecommons.org/publicdomain/zero/1.0/>。
本目录的结构化数据为 CC0；项目代码的许可不改变来源数据许可。

`records.json.gz` 是确定性规范化结果：丢弃缺少唯一国家代码、有效坐标或四位 ICAO 的行，
按完整记录去重，保留冲突行供关联器拒绝，得到 22,425 行。
规范化脚本：`scripts/prepare_wikidata_reference.py`。
机场和国家原件分别来自 <https://query.wikidata.org/sparql> 上述查询；重现方法是将
`airports.json.gz`、`countries.json.gz` 解压为 `airports-complete.json`、`country-codes.json`，
将查询另存为 `query-complete.rq`、`country-query.rq`，再运行：

```powershell
python scripts/prepare_wikidata_reference.py --input <input-directory> --output <output-directory>
```

Pages 构建只读取已冻结文件，校验压缩文件哈希，不实时调用 SPARQL。
导出时只有两边 `(ISO 国家代码, ICAO)` 均唯一、两边坐标相距不超过 3 km 才附加名称参考。
未匹配、歧义和距离差异单独计数。名称、坐标、频率不覆盖 OurAirports 原记录。
这里只补充名称与记录出处，不把 Wikidata 的 ICAO 属性当作在用机场证明，也不增加推测的机场点。

快照时间是获取时间，既不是上游每条记录的修改时间，也不是 AIRAC 有效时间。
