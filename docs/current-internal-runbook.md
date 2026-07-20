# JPT Sales Toolkit 当前内部试运行手册

当前团队稳定候选基线：`v0.11.4-internal`。它仍是 `UNSIGNED-INTERNAL` 内部版本；是否可分发以源码回归、三个目标平台安装包烟测和团队 Gate 验收结果为准。

## 入口

- 本机访问：`http://127.0.0.1:8000`
- 局域网试运行：运行项目根目录的 `Start JPT LAN Test Server.command`
- 统一验证：`bash scripts/validate_v08.sh`
- 浏览器轻量 smoke：服务启动后运行 `bash scripts/browser_smoke_v09.sh`
- Windows / macOS 安装与授权：`docs/deployment/`
- 团队离线 HTML 指南：`docs/guides/00-开始这里.html`

`Start JPT LAN Test Server.command` 现在会同时准备两类账号：
- 固定演示账号：`leader01 / sales01 / sales02 / sales03 / tech01 / tech02`
- 当前 `data-test-server/` 里已经存在的真实团队账号：会自动刷新成可登录的 LAN 测试密码

启动后会生成账号清单：`data-test-server/lan_test_accounts.md`

## 当前能力

- Offline Authorization：Leader / Sales / Tech 三角色、单成员单设备、固定 90 天、签名包和 Leader 恢复闭环。

- 销售漏斗 7 步：询盘解析、处理、跟进、打样、成交、履行、售后。
- Data Review：经营复盘、风险 Lead、高价值 Lead、Owner/Region 维度统计。
- Trip Planner：候选客户、路线预览/保存、停留天数、周末/节假日避让、导出。
- Visit Execution：按天查看拜访客户、联系人、地址、Lead 摘要，填写拜访模板，自动生成 Follow-up Needed，上传拜访附件，按天导出拜访报告。
- Coordinate Review：坐标队列、地图选点、经纬度输入、邮件地址解析选点、坐标变更审计。
- External XLSX Import：Leader 使用独立四步向导完成备份、工作簿选择、固定窗口预检/修正和原子提交；人员映射、客户匹配和问题采用折叠分组，标准模板与源文件不进入安装包。
- Account Mapping：来源姓名按 owner / collaborator / actor / task_assignee 等用途映射到已有 Leader / Sales / Tech 账号；同名跨销售与技术职责可分别选择账号，XLSX 不创建账号，角色错配阻断提交。
- Data Package Sync：成员终端使用 JSON 数据包导出/导入，执行权限过滤、冲突合并和导入前后快照；该链路不以 XLSX 作为同步协议。
- Data Governance：国家/区域后端规范化、坐标审计、基础批量修复 API。
- Business Region：按 Lead 负责人账号筛选 `GLOBAL / 欧洲 / 北美/加拿大/澳洲 / 俄罗斯/土耳其/中东 / 东南亚`；`GLOBAL` 是真实归属，“全部地区”才是清空地区条件。地区与负责人、技术、搜索和时间条件取交集，不能用客户地址代替负责人业务归属。
- Follow-up Time：`已逾期 / 今日到期 / 未来 7 天` 只判断计划的下一次跟进日期；长期未跟进时间按“最近正式跟进 → 询盘日期 → 创建日期”回退计算，可与业务地区及成员条件组合。未设置计划日期的记录不会被错误算入到期页，空页面会说明具体原因。
- Customer Merge：Leader 使用客户名称和别名模糊候选、匹配分数与只读迁移预览核对联系人、Lead、域名和别名后执行一次安全合并；来源客户归档并保留审计。
- Map Quality：地图明确区分精确、近似和缺失坐标；近似位置不得解释为客户准确地址。底图离线或加载失败时显示状态提示，列表、筛选和坐标修正仍可继续使用。

## 文档归档

- `docs/v0.11.4-validation-result.md`：当前本地候选的 Sampling/Excel 字段同步、真实数据修复、冻结 App 和本地验证记录；跨平台构建待用户确认。
- `docs/v0.6-internal-runbook.md`：历史试运行手册，保留作归档。
- `docs/v0.7-trial-runbook.md`：v0.7 数据复盘和出差规划阶段说明。
- `docs/v0.8-plus-module-roadmap.md`：后续模块规划和状态。
- `docs/v0.11.0-validation-result.md`：当前安装、XLSX 导入、权限映射和数据包同步验证记录。
- `docs/v0.10.0-validation-result.md`：上一版权限授权与跨平台安装包验证记录。
- `docs/v0.9.0-validation-result.md`：上一版 v0.9 验证记录。
- `docs/deployment/`：当前桌面安装、账号签发、试运行和发布说明。
- `docs/v0.8.7-validation-result.md`：上一稳定基线验证记录。

后续 release 只新增对应的 validation result；日常入口统一看本文件。
