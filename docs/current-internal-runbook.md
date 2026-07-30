# JPT Sales Toolkit 当前内部试运行手册

当前团队内部稳定基线：`v0.11.7-internal`。它仍是 `UNSIGNED-INTERNAL` 内部版本；可分发范围以源码回归、三个目标平台安装包烟测和团队 Gate 验收结果为准。

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
- Trip Planner：候选客户、路线预览/保存、计划归档、停留天数、周末/节假日避让、导出。
- Visit Execution：按天查看拜访客户、联系人、地址、Lead 摘要，填写拜访模板，自动生成 Follow-up Needed，上传拜访附件，按天导出拜访报告。
- Coordinate Review：坐标队列、地图选点、经纬度输入、邮件地址解析选点、坐标变更审计。
- External XLSX Import：Leader 使用独立四步向导完成备份、工作簿选择、固定窗口预检/修正和原子提交；人员映射、客户匹配和问题采用折叠分组，标准模板与源文件不进入安装包。
- Account Mapping：来源姓名按 owner / collaborator / actor / task_assignee 等用途映射到已有 Leader / Sales / Tech 账号；同名跨销售与技术职责可分别选择账号，XLSX 不创建账号，角色错配阻断提交。
- Data Package Sync：成员终端使用 JSON 数据包导出/导入，执行权限过滤、冲突合并和导入前后快照；Leader 向 Sales 分发时必须先选择接收成员，导出包只包含该成员作为负责人的 Lead，并在导入端校验接收账号。JSON 只有在同一文件预检 `errors=0` 且权限跳过数为 0 时才允许提交；结果明确区分成功、部分完成和失败。Leader→Sales→Leader 往返按来源 Lead ID 回写原记录，联系人源 ID 会映射为本地联系人 ID，单条异常不会留下半写入客户或 Lead。该链路不以 XLSX 作为同步协议。
- Data Governance：国家/区域后端规范化、坐标审计、基础批量修复 API。
- Business Region：按 Lead 负责人账号筛选 `GLOBAL / 欧洲 / 北美/加拿大/澳洲 / 俄罗斯/土耳其/中东 / 东南亚`；`GLOBAL` 是真实归属，“全部地区”才是清空地区条件。地区与负责人、技术、搜索和时间条件取交集，不能用客户地址代替负责人业务归属。
- Follow-up Time：`已逾期 / 今日到期 / 未来 7 天` 只判断计划的下一次跟进日期；长期未跟进时间按“最近正式跟进 → 询盘日期 → 创建日期”回退计算，可与业务地区及成员条件组合。未设置计划日期的记录不会被错误算入到期页，空页面会说明具体原因。
- Worklist Order：各工作页使用固定业务排序，而不是数据库偶然返回顺序。处理页按询盘日期由早到晚；跟进页按下一次跟进日期由近到远；售前/样品页优先进行中且按到期日；成交、履约、售后分别按阶段与关键业务日期排列。缺失或无效日期排在有效日期之后，同值再按询盘编号与内部 ID 稳定排序。
- Customer Merge：Leader 使用客户名称和别名模糊候选、匹配分数与只读迁移预览核对联系人、Lead、域名和别名后执行一次安全合并；来源客户归档并保留审计。
- Map Quality：地图明确区分精确、近似和缺失坐标；自动候选保持待复核，越界或不完整旧坐标降级为近似/缺失。Leader、owner、collaborator 可修正，watcher 与 Tech 只读；并发版本冲突要求刷新，不会静默覆盖。地址搜索和批量地理编码会把地址字段发送给一个或多个外部服务；默认公共 Nominatim，高德显式启用后为首选，但空结果、网络、超时、配额或无效响应会回退 Nominatim，Key/权限错误不回退。高德结果本地转为 WGS84；高德不替换 CARTO/OpenStreetMap 底图，打开地图仍会产生外部瓦片请求。公共 Nominatim 只用于小规模一次性查询。Windows 开始菜单启动需重新登录系统，macOS Finder 启动需由 `launchd`/MDM 注入 GUI 会话。Key 不进入前端、GitHub、安装包、启动脚本或日志；禁止外发的地址使用人工经纬度或地图选点。
- Safe Upgrade：旧数据库在首次 schema 迁移前自动生成并验证完整 `pre_upgrade` 备份；迁移使用独立版本账本，失败自动恢复原数据库，第二次启动不重复写入。Windows/macOS 内测构建分别使用旧版夹具检查数据库、附件、授权和卸载保留。离线恢复入口只接受自动生成且清单标记为 `pre_upgrade` 的 ZIP；恢复前还会先把当前数据库保存为 `data/backups/pre_recovery_current_*.sqlite`，保存或校验失败时不会开始恢复。

## 文档归档

- `docs/v0.11.7-validation-result.md`：当前内部稳定版的全面审计、修补、源码门禁和原生三平台发布验证记录。
- `docs/v0.11.6-validation-result.md`：上一候选的 JSON 定向分发、卡片排序、升级保护和三平台本地构建验证记录。
- `docs/v0.11.5-validation-result.md`：历史候选的体验、地图、升级保护和冻结 App 验证记录。
- `docs/v0.6-internal-runbook.md`：历史试运行手册，保留作归档。
- `docs/v0.7-trial-runbook.md`：v0.7 数据复盘和出差规划阶段说明。
- `docs/v0.8-plus-module-roadmap.md`：后续模块规划和状态。
- `docs/v0.11.0-validation-result.md`：当前安装、XLSX 导入、权限映射和数据包同步验证记录。
- `docs/v0.10.0-validation-result.md`：上一版权限授权与跨平台安装包验证记录。
- `docs/v0.9.0-validation-result.md`：上一版 v0.9 验证记录。
- `docs/deployment/`：当前桌面安装、账号签发、试运行和发布说明。
- `docs/v0.8.7-validation-result.md`：上一稳定基线验证记录。

后续 release 只新增对应的 validation result；日常入口统一看本文件。
