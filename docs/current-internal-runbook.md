# JPT Sales Toolkit 当前内部试运行手册

当前内部基线：`v0.11.0-internal`

## 入口

- 本机访问：`http://127.0.0.1:8000`
- 局域网试运行：运行项目根目录的 `Start JPT LAN Test Server.command`
- 统一验证：`bash scripts/validate_v08.sh`
- 浏览器轻量 smoke：服务启动后运行 `bash scripts/browser_smoke_v09.sh`
- Windows / macOS 安装与授权：`docs/deployment/`

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
- External XLSX Import：安装后独立上传、预检、人员/客户映射、原子提交、重复更新和质量问题队列；标准模板与源文件不进入安装包。
- Account Mapping：来源姓名只映射到已有 Leader / Sales / Tech 账号，XLSX 不创建账号，角色错配阻断提交。
- Data Package Sync：成员终端使用 JSON 数据包导出/导入，执行权限过滤、冲突合并和导入前后快照；该链路不以 XLSX 作为同步协议。
- Data Governance：国家/区域后端规范化、坐标审计、基础批量修复 API。

## 文档归档

- `docs/v0.6-internal-runbook.md`：历史试运行手册，保留作归档。
- `docs/v0.7-trial-runbook.md`：v0.7 数据复盘和出差规划阶段说明。
- `docs/v0.8-plus-module-roadmap.md`：后续模块规划和状态。
- `docs/v0.11.0-validation-result.md`：当前安装、XLSX 导入、权限映射和数据包同步验证记录。
- `docs/v0.10.0-validation-result.md`：上一版权限授权与跨平台安装包验证记录。
- `docs/v0.9.0-validation-result.md`：上一版 v0.9 验证记录。
- `docs/deployment/`：当前桌面安装、账号签发、试运行和发布说明。
- `docs/v0.8.7-validation-result.md`：上一稳定基线验证记录。

后续 release 只新增对应的 validation result；日常入口统一看本文件。
