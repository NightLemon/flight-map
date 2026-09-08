# 本机操作与恢复

在仓库根目录使用 PowerShell，需要 Python 3.12、uv 和 Node.js 22.13.0+。首次安装运行 `uv sync --all-packages --dev --locked` 和 `npm ci`；更新 Python 依赖前先停止 API。以下命令直接调用已安装环境，不触发依赖自动同步。

API 默认使用 `data`，构造仓库时自动执行编号迁移。可以设置 `$env:FLIGHTMAP_DATA_DIR = "C:\绝对路径\flightmap-data"`；CLI 和 API 必须指向同一目录。CLI 也支持 `--data-dir "C:\绝对路径\flightmap-data"`。来源配置默认是 `sources/us/faa.yml`。

## NASR 机场研究

在线获取当前日期所属的 NASR 机场资料并构建候选：

```powershell
.\.venv\Scripts\flightmap-ingest.exe update --product nasr --research
```

命令返回 `snapshot_id`、完整报告及 `activation: not-requested`。保存并检查它，再显式切换研究快照：

```powershell
$snapshotId = "<update 输出的 snapshot_id>"
.\.venv\Scripts\flightmap-ingest.exe report --snapshot-id $snapshotId
.\.venv\Scripts\flightmap-ingest.exe activate-snapshot --snapshot-id $snapshotId
```

未来版使用 `update --product nasr --research --preview`。预览只供显式查看，未来官方日期不能激活。`--research` 当前只支持 NASR，并且与 `--manifest` 互斥。

已登记原件可以直接重建。下面使用本机已经校验的 2026-09-03 官方 ZIP，不访问网络、不新增获取事件：

```powershell
.\.venv\Scripts\flightmap-ingest.exe update --product nasr --research --asset-sha256 d5e4c999d4c96ab4d66d8ce9a387de8ea59b5226a6144ea1ba58758ff29bbbd9
```

SHA 必须完整。原件要存在于所选数据目录，并已登记为 FAA NASR 获取记录；任意本地文件路径不能代替这个身份。相同原件、解析器、模型和证据再次构建返回同一 ID 与 `unchanged`。在线更新每次重新获取官方文件，避免相同 URL 的更正被旧缓存掩盖；同一内容仍只存一份原件，每次真实获取分别登记。

撤销研究快照：

```powershell
.\.venv\Scripts\flightmap-ingest.exe revoke-snapshot --snapshot-id $snapshotId --reason "<具体撤销原因>"
```

撤销清除对应研究指针，之后包括历史模式在内的记录读取都被拒绝，报告仍可查询。它不自动改选另一个快照，也不改变 d-TPP Current。新候选构建、激活失败同样不能替换已有研究指针。

## 日期和版本的含义

机场快照保留 NASR `EFF_DATE` 的官方日期。NASR 精确 UTC 生效和失效时刻尚未确认，字段保持 `exact_validity_status=unknown`。页面用 UTC 日历日期区分未来、可研究和预计更新日期已到；这种分类不赋予产品精确时间。

NASR 自身的 28 天发行说明用于计算预计更新日期。到这一天显示 `update-due` 提醒，已选择的研究快照仍可浏览，不宣称它具有已核实的当前有效期。陈旧快照可以显式激活用于研究。历史只能选择非活动且非未来的快照；未来版本须显式进入预览。

页面请求固定快照 ID。另一操作切换活动快照后，旧活动请求返回 409，页面刷新整组选择；撤销返回 410；权限、验证或原件完整性失败返回 403。所有研究 API 响应使用 `Cache-Control: no-store`。

航图使用独立 d-TPP release ID 和精确有效期。自动对照要求机场快照的官方日期与航图版本的生效日期一致；没有同日期资料时显示缺失状态，不能换用最新 PDF。PDF 面板提供逐页查看、翻页、缩放与官方链接，失败只影响该航图查看。

## 严格 Current 继续独立管理

```powershell
.\.venv\Scripts\flightmap-ingest.exe update --product dtpp
$releaseId = "<update 输出的 release_id>"
.\.venv\Scripts\flightmap-ingest.exe report --release-id $releaseId
.\.venv\Scripts\flightmap-ingest.exe promote --release-id $releaseId
```

需要撤销该严格版本时执行：

```powershell
.\.venv\Scripts\flightmap-ingest.exe revoke --release-id $releaseId --reason "<具体撤销原因>"
```

`report` 的 `--release-id` 与 `--snapshot-id` 必须且只能选一个。`promote` 只接受具有精确产品时间证据的严格发布；研究快照会明确被拒绝。

不加 `--research` 的 `update --product nasr` 仍因缺少精确 UTC 依据返回退出码 2，保留原件和解析报告。只有取得 NASR 自身的官方时刻依据后，才使用 `--manifest "<文件>"` 或 `import-local --product nasr --file "<官方文件>" --manifest "<文件>"`。

CLI 退出码 0 表示成功或内容未变化；1 表示获取、校验、构建或管理操作失败；2 表示需要人工操作、缺少依据或参数组合不合法。研究尝试与严格发布尝试分别保存，研究成功不会覆盖 NASR 严格发布仍缺时间依据的状态。

## 备份、恢复与 schema 2 回退

普通备份前停止 API、CLI 和其他数据写入进程。完整复制数据目录，不能只复制 SQLite 而遗漏 SHA 原件：

```powershell
$backupRoot = ".cache/backups/manual-$(Get-Date -Format yyyyMMdd-HHmmss)"
New-Item -ItemType Directory -Path $backupRoot
Copy-Item -LiteralPath ".\data" -Destination (Join-Path $backupRoot "data") -Recurse
```

使用自定义数据目录时，将命令中的 `.\data` 改为实际目录。恢复到一个尚不存在的新目录，确认复制成功后指向它启动；保留原目录便于回退：

```powershell
Copy-Item -LiteralPath (Join-Path $backupRoot "data") -Destination ".cache/data-restored" -Recurse
$env:FLIGHTMAP_DATA_DIR = (Resolve-Path ".cache/data-restored").Path
.\.venv\Scripts\flightmap-api.exe
```

获取事件保留原始元数据，实际原件定位采用当前仓库的数据目录，恢复后不会依赖旧目录仍然存在。恢复后检查报告、研究选择与 Current 状态；严格资料的到期检查仍按实际时间执行。

日期级快照使用数据库 schema 2。旧代码不能直接打开升级后的数据库。回退旧版本时应同时恢复升级前的完整数据备份，并使用对应源码和来源配置；不要手动降 `user_version` 或删除新表。本次升级前备份位于 `.cache/backups/pre-research-20260908/data`。

## 真实副本生命周期演练

前置数据为已导入的 NASR 2026-09-03 ZIP（上文完整 SHA，19,411 条机场）和 d-TPP 2609 Current。执行：

```powershell
.\.venv\Scripts\python.exe scripts/verify_research_lifecycle.py --source-data-dir data --output .cache/research-lifecycle-report.json
```

脚本通过只读 SQLite 连接建立一致副本，复制已登记原件，只在 `.cache/research-lifecycle` 的唯一临时子目录中操作；API 可继续运行。它禁止发现和下载，检查重复构建、获取计数、重启、未来预览、日期分类变化、更新提醒、版本切换的 409、撤销的 410 及原件损坏的 403，并确认真实源数据库和原件未变。演练完成后删除已核实路径的临时副本，保留 JSON 报告；失败退出码为 1。

版本切换使用“解析器版本变化”的临时重建，官方原件和机场记录保持不变。这证明更正版本的切换机制，不表示 FAA 实际发布了另一份更正 ZIP。脚本不替代浏览器对地图点、搜索定位和真实 PDF 页面的验收。
