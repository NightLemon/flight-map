# GitHub Pages

源码仓库：<https://github.com/NightLemon/flight-map>

公开参考版：<https://nightlemon.github.io/flight-map/>

个人主页仓库 `nightlemon.github.io` 保留原内容。此项目使用 `flight-map` 仓库的独立 Pages 部署，路径为 `/flight-map/`。

## 公开版与本机版

GitHub Pages 只能托管静态文件，不能运行本项目的 Python API、SQLite 或 PDF 校验代理。Pages 构建以 `VITE_PUBLIC_REFERENCE=true` 选择独立的 `PublicApp`。普通 `npm run dev` 与 `npm run build` 继续使用 FAA 本机研究入口。

公开版包含 OurAirports 机场搜索、按视野加载的机场/跑道/导航台、点击机场自动读取频率和跑道详情。只有源文件中同时存在两端坐标的跑道才生成地图线；不按长度和方向推算缺失端点。源数据中的已关闭机场不进入公开机场层。

FAA 航点、航路、d-TPP PDF 和本机版本管理仍在本机版。公开界面持续标记社区来源、数据快照日期及非运行用途。上游提交时间不是 AIRAC 生效时间；30 天提示只是数据陈旧提醒，不声明官方有效期。

## 数据与许可依据

2026-09-08 核对 <https://ourairports.com/data/>，其 Terms of use 明确写明：

> All data is released to the Public Domain, and comes with no guarantee of accuracy or fitness for use.

上游仓库：<https://github.com/davidmegginson/ourairports-data>。当前构建固定为 `269b3557e2c784cc41673b77c7fae211d3f61668`（2026-09-08T01:53:12Z），只读取 `airports.csv`、`airport-frequencies.csv`、`runways.csv`、`navaids.csv` 和许可证。输入哈希、来源链接、版本与数量在生成的 `reference/manifest.json` 中公开。生成器不会打开 FAA 数据库，也不会上传本机原件或航图。

NASR/d-TPP 的已核实页面仅说明免费获取和下载，没有补足本项目所要求的再分发证据。因此 `sources/us/faa.yml` 和 FAA 门禁保持原有状态；本次没有将 `review-required` 数据打包进网站。公开版的社区资料不改变本机 FAA 记录。

## 构建与发布

需要 Python 3.12 和 Node.js 22.13.0+：

```powershell
npm ci
python scripts/build_pages_data.py
npm run build:pages
npm run test:pages
```

生成目录 `.cache/pages-public/reference/`、下载缓存 `.cache/pages-input/` 与 `apps/web/dist/` 均由 Git 忽略。生成过程位于开发服务器监视目录之外，避免本机文件监视器干扰目录替换。普通本机模式不加载这些静态资料；公开构建只复制指定的 `.cache/pages-public/`，并在发现未完成的生成临时目录时拒绝发布。源文件不写入 Git 历史。静态数据使用上游提交 SHA 作为实际目录名，浏览器不会跨版本拼接缓存文件。

前端默认只加载小型清单。搜索索引在搜索时加载；地图使用 5° 分块，仅在达到缩放门槛时请求相交视野，每层最多 500 个要素；详情按机场 ID 分桶，点击时加载。内存仅缓存最近 32 个数据文件。移动地图或切换机场会取消旧请求。

`.github/workflows/ci.yml` 在提交后运行 Python 与 Web 检查、原有浏览器回归、公开数据构建及 Pages 浏览器验证。只有 `main` 的推送或手动运行、且全部检查通过后才上传部署；Pull Request 不部署。GitHub Pages 使用 GitHub Actions 模式。

数据固定在已核对的上游版本，不会每次构建静默跟随最新资料。更新时应更改生成器固定版本及对应输入校验值、重新核对来源和数据、完成测试后提交。没有配置无人审核的数据自动更新。

上线复测可以指定真实 URL：

```powershell
$env:FLIGHTMAP_PAGES_URL = 'https://nightlemon.github.io/flight-map/'
npm run test:pages
Remove-Item Env:FLIGHTMAP_PAGES_URL
```
