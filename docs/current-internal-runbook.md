# JPT Sales Toolkit 当前内部试运行手册

当前内部基线：`v0.9.0-internal`

## 入口

- 本机访问：`http://127.0.0.1:8000`
- 局域网试运行：运行项目根目录的 `Start JPT LAN Test Server.command`
- 统一验证：`bash scripts/validate_v08.sh`
- 浏览器轻量 smoke：服务启动后运行 `bash scripts/browser_smoke_v09.sh`

`Start JPT LAN Test Server.command` 现在会同时准备两类账号：
- 固定演示账号：`leader01 / sales01 / sales02 / sales03 / tech01 / tech02`
- 当前 `data-test-server/` 里已经存在的真实团队账号：会自动刷新成可登录的 LAN 测试密码

启动后会生成账号清单：`data-test-server/lan_test_accounts.md`

## 当前能力

- 销售漏斗 7 步：询盘解析、处理、跟进、打样、成交、履行、售后。
- Data Review：经营复盘、风险 Lead、高价值 Lead、Owner/Region 维度统计。
- Trip Planner：候选客户、路线预览/保存、停留天数、周末/节假日避让、导出。
- Visit Execution：按天查看拜访客户、联系人、地址、Lead 摘要，填写拜访模板，自动生成 Follow-up Needed，上传拜访附件，按天导出拜访报告。
- Coordinate Review：坐标队列、地图选点、经纬度输入、邮件地址解析选点、坐标变更审计。
- Export / Import：数据包导出、导入预检、权限过滤合并、导入前后快照。
- Data Governance：国家/区域后端规范化、坐标审计、基础批量修复 API。

## 文档归档

- `docs/v0.6-internal-runbook.md`：历史试运行手册，保留作归档。
- `docs/v0.7-trial-runbook.md`：v0.7 数据复盘和出差规划阶段说明。
- `docs/v0.8-plus-module-roadmap.md`：后续模块规划和状态。
- `docs/v0.9.0-validation-result.md`：当前 v0.9 验证记录。
- `docs/v0.8.7-validation-result.md`：上一稳定基线验证记录。

后续 release 只新增对应的 validation result；日常入口统一看本文件。
