# Flight Map 项目约定

- [x] 项目需求已确认。
- [x] Monorepo 脚手架已创建。
- [x] FAA 来源、采集门禁、API 与地图界面已完成首阶段定制。
- [x] 本阶段不需要安装额外 VS Code 扩展。
- [x] Python 检查、测试和 Web 构建已通过。
- [x] VS Code Web Build 任务已创建并成功运行。
- [x] 开发环境已启动并完成浏览器验证。
- [x] README 和架构、数据治理、来源目录文档已完成。

当前实现状态以 docs/implementation-plan.md 为准。完整研究平台的证据阻断项不得计入已完成；本机使用权限与再分发权限分开核实。

## 持续开发规则

- 跟用户使用中文交流，代码标识符和技术术语可保留英文。
- 所有航空数据必须可追溯到真实来源；禁止编造、OCR 推导或无依据补全航路。
- 默认 API 只返回已验证且处于有效期的发布集。
- Preview 不进入 Current；旧周期到期必须下线。
- 未支持的 ARINC Path Terminator 不得生成 fallback 直线。
- 社区数据必须作为独立参考层，不能静默覆盖官方数据。
- 许可不明确时采用 fail-closed；本地获取/处理与再分发分别依据注册表政策判断。
- 代码、数据与航图许可分开管理；不要把大文件或原始航图提交到 Git。
- 修改后运行 `uv run ruff check .`、`uv run pytest`、`npm run lint` 和 `npm run build`。
