# JPT Sales Toolkit 当前内部试运行手册

当前待测候选：`v0.12.0-internal`。它包含 Trip Planner v2 的完整路线与正式导出，是 `UNSIGNED-INTERNAL` 团队测试 / Draft Pre-release。本次只生成 Windows 10/11 x64 与 macOS Apple Silicon arm64 两个原生安装包。覆盖升级以 `v0.11.9-internal` 为直接基线；旧版 schema 3 会先生成并验证本机 `pre_upgrade` 备份，再升级到 schema 6。两平台构建和团队实测全部通过前，不得标记为 Stable / Latest。

## 入口

- 本机访问：`http://127.0.0.1:8000`
- 局域网试运行：运行项目根目录的 `Start JPT LAN Test Server.command`
- 统一验证：`bash scripts/validate_v08.sh`
- 浏览器轻量 smoke：服务启动后显式传入隔离测试账号，运行 `SMOKE_USER="..." SMOKE_PASSWORD="..." bash scripts/browser_smoke_v09.sh`
- Windows / macOS 安装与授权：`docs/deployment/`
- 团队离线 HTML 指南：`docs/guides/00-开始这里.html`

`Start JPT LAN Test Server.command` 只创建/刷新六个保留名称的演示账号：`leader01 / sales01 / sales02 / sales03 / tech01 / tech02`。密码每次随机生成，只写入权限为 `0600` 的 `data-test-server/lan_test_accounts.md`；其他既有团队账号和密码不会被修改或出现在清单中。

## 当前能力

- Offline Authorization：Leader / Sales / Tech 三角色、单成员单设备、固定 90 天、签名包和 Leader 恢复闭环。

- 销售漏斗 7 步：询盘解析、处理、跟进、打样、成交、履行、售后。
- Data Review：经营复盘、风险 Lead、高价值 Lead、Owner/Region 维度统计。
- Trip Planner v2：硬日期窗、中国起返地点与时间窗、自动/手工顺序、四类逐段交通、人工锁定、自定义自由停靠、半天日程、多地点拜访、拜访准备、计划归档，以及 XLSX、离线 HTML、ICS、Markdown、CSV 导出。交通建议不要求账号或 Token，近似估算和外部查询链接由使用者复核后应用。
- Visit Execution：按天查看拜访客户、联系人、地址、Lead 摘要，填写拜访模板，自动生成 Follow-up Needed，上传拜访附件，按天导出拜访报告。
- Coordinate Review：坐标队列、地图选点、经纬度输入、邮件地址解析选点、坐标变更审计。
- External XLSX Import：Leader 使用独立四步向导完成备份、工作簿选择、固定窗口预检/修正和原子提交；人员映射、客户匹配和问题采用折叠分组，标准模板与源文件不进入安装包。
- Account Mapping：来源姓名按 owner / collaborator / actor / task_assignee 等用途映射到已有 Leader / Sales / Tech 账号；同名跨销售与技术职责可分别选择账号，XLSX 不创建账号，角色错配阻断提交。
- Sales Data Package Sync：成员终端使用定向 JSON 数据包导出/导入，执行权限过滤、冲突合并和导入前后快照；Leader 向 Sales 分发时必须先选择接收成员，导出包只包含该成员作为负责人的 Lead，并在导入端校验接收账号。JSON 只有在同一文件预检 `errors=0` 且权限跳过数为 0 时才允许提交；结果明确区分成功、部分完成和失败。Leader→Sales→Leader 往返按来源 Lead ID 回写原记录，联系人源 ID 会映射为本地联系人 ID，单条异常不会留下半写入客户或 Lead。该链路不以 XLSX 作为同步协议。
- Tech Task Packages：Leader 在独立页签选择精确 Tech 账号，导出该账号当前全部未归档分配任务的完整快照 `.jpttask`；Tech 预检、导入、更新本人售前/样品或售后任务，再导出 `.jptresult` 给原 Leader 预检合并。新完整快照中缺失的任务只在 Tech 没有未导出更改，或结果已导出且此后未再修改时才可撤回；否则整包阻断。同一结果字段被 Leader 与 Tech 改成不同值时阻断，不同字段可合并；旧快照、改派、归档、接收账号不符和同包 ID 异内容均拒绝，重复包保持幂等。包内不含报价、金额、联系人或附件文件，首版无设备数字签名，只能通过可信内部渠道点对点传递。该链路与 Sales JSON、XLSX 相互独立。
- Tech Navigation Counts：Tech 左侧“售前 / 样品管理”和“售后”分别显示本人当前有效工作的去重 Lead 数。计数只纳入当前 Tech 负责、状态为 `Open / In Progress`，且任务、Lead、客户均未归档的记录；“全部任务”页面还可展示已完成/已取消任务，所以页面任务总数可以大于左侧计数。任务包导入、状态更新和页面刷新后会按同一口径重新读取，不再依赖 Leader/Sales 仪表盘权限。
- Data Governance：国家/区域后端规范化、坐标审计、基础批量修复 API。
- Business Region：按 Lead 负责人账号筛选 `GLOBAL / 欧洲 / 北美/加拿大/澳洲 / 俄罗斯/土耳其/中东 / 东南亚`；`GLOBAL` 是真实归属，“全部地区”才是清空地区条件。地区与负责人、技术、搜索和时间条件取交集，不能用客户地址代替负责人业务归属。
- Follow-up Time：`已逾期 / 今日到期 / 未来 7 天` 只判断计划的下一次跟进日期；长期未跟进时间按“最近正式跟进 → 询盘日期 → 创建日期”回退计算，可与业务地区及成员条件组合。未设置计划日期的记录不会被错误算入到期页，空页面会说明具体原因。
- Worklist Order：各工作页使用固定业务排序，而不是数据库偶然返回顺序。处理页按询盘日期由早到晚；跟进页按下一次跟进日期由近到远；售前/样品页优先进行中且按到期日；成交、履约、售后分别按阶段与关键业务日期排列。缺失或无效日期排在有效日期之后，同值再按询盘编号与内部 ID 稳定排序。
- Customer Merge：Leader 使用客户名称和别名模糊候选、匹配分数与只读迁移预览核对联系人、Lead、域名和别名后执行一次安全合并；来源客户归档并保留审计。
- Map Quality：地图明确区分精确、近似和缺失坐标；自动候选保持待复核，越界或不完整旧坐标降级为近似/缺失。Leader、owner、collaborator 可修正，watcher 与 Tech 只读；并发版本冲突要求刷新，不会静默覆盖。地址搜索和批量地理编码会把地址字段发送给一个或多个外部服务；默认公共 Nominatim，高德显式启用后为首选，但空结果、网络、超时、配额或无效响应会回退 Nominatim，Key/权限错误不回退。高德结果本地转为 WGS84；高德不替换 CARTO/OpenStreetMap 底图，打开地图仍会产生外部瓦片请求。公共 Nominatim 只用于小规模一次性查询。Windows 开始菜单启动需重新登录系统，macOS Finder 启动需由 `launchd`/MDM 注入 GUI 会话。Key 不进入前端、GitHub、安装包、启动脚本或日志；禁止外发的地址使用人工经纬度或地图选点。
- Safe Upgrade：从 v0.11.9 schema 3 升级到 v0.12.0 schema 6 前，应用会在任何 schema 写入前生成并验证完整 `pre_upgrade` 备份。迁移使用独立版本账本；失败会恢复原数据库并停止启动，第二次启动不会重复迁移或重复创建备份。Windows/macOS 内测构建分别检查客户、Lead、任务、附件、授权、Tech 包状态和卸载保留。离线恢复入口只接受自动生成且清单标记为 `pre_upgrade` 的 ZIP；恢复前还会先把当前数据库保存为 `data/backups/pre_recovery_current_*.sqlite`，保存或校验失败时不会开始恢复。

## 文档归档

- `docs/v0.12.0-validation-result.md`：当前内测候选的验证证据账本；尚未完成的本地、CI 和原生安装门禁保持 Pending。
- `docs/v0.11.9-validation-result.md`：直接覆盖升级基线与 Tech 导航计数修复的历史验证记录。
- `docs/v0.11.8-validation-result.md`：Tech 任务包首版的历史验证记录。
- `docs/v0.11.7-validation-result.md`：更早版本的全面审计、修补、源码门禁和原生三平台发布历史记录。
- `docs/v0.11.6-validation-result.md`：更早候选的 JSON 定向分发、卡片排序、升级保护和三平台本地构建历史记录。
- `docs/v0.11.5-validation-result.md`：历史候选的体验、地图、升级保护和冻结 App 验证记录。
- `docs/v0.6-internal-runbook.md`：历史试运行手册，保留作归档。
- `docs/v0.7-trial-runbook.md`：v0.7 数据复盘和出差规划阶段说明。
- `docs/v0.8-plus-module-roadmap.md`：后续模块规划和状态。
- `docs/v0.11.0-validation-result.md`：历史安装、XLSX 导入、权限映射和数据包同步验证记录。
- `docs/v0.10.0-validation-result.md`：上一版权限授权与跨平台安装包验证记录。
- `docs/v0.9.0-validation-result.md`：上一版 v0.9 验证记录。
- `docs/deployment/`：当前桌面安装、账号签发、试运行和发布说明。
- `docs/v0.8.7-validation-result.md`：上一稳定基线验证记录。

后续 release 只新增对应的 validation result；日常入口统一看本文件。
