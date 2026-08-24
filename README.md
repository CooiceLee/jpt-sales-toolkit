# JPT Sales Toolkit

面向 JPT 海外销售团队的全流程效率工具集。

当前待测候选：`v0.12.0-internal`。它包含 Trip Planner v2 的路线、交通、半天日程、拜访准备和正式行程导出，是 `UNSIGNED-INTERNAL` 团队测试 / Draft Pre-release，不等同于已签名的公开正式版。本次只发布 Windows 10/11 x64 与 macOS Apple Silicon arm64 两个原生安装包。覆盖升级以 `v0.11.9-internal` 为直接基线；程序会在任何 schema 写入前自动生成并验证本机 `pre_upgrade` 备份，再把 schema 3 升级到 schema 6。两平台构建和团队实测全部完成前，不得把本候选标记为 Stable / Latest。当前启动、账号授权、备份、业务地区、客户合并、地图、出差规划、Sales 定向数据分发和 Tech 任务包入口见 [docs/current-internal-runbook.md](docs/current-internal-runbook.md)。面向团队成员的离线 HTML 指南入口见 [docs/guides/00-开始这里.html](docs/guides/00-开始这里.html)。

## 功能概览

| Step | 模块 | 功能 |
|------|------|------|
| 1 | Inquiry Parser | 解析询盘邮件，自动提取客户和需求信息 |
| 2 | Inquiry Handler | 管理询盘记录，编辑客户信息和需求评估 |
| 3 | Follow-up Tracker | 计划到期、长期未跟进和跟进记录管理 |
| 4 | Sample Manager | 打样流程管理 |
| 5 | Deal Closer | 报价和成交管理 |
| 6 | Order Fulfillment | 订单履行跟踪 |
| 7 | After-sales Support | 售后问题管理 |
| Data | Data Review | 经营复盘、风险 Lead、高价值 Lead 和权限隔离分析 |
| Data | Trip Planner | 硬日期窗、手工/自动顺序、逐段交通、自由停靠、半天日程、拜访准备和 XLSX/HTML/ICS/Markdown/CSV 导出 |
| Data | Coordinate Review | 精确/近似/缺失坐标质量队列、地图选点、经纬度录入和地址解析选点 |
| Ops | Export / Import | Sales JSON 定向交换、Tech 任务包往返、导入预检、Leader 汇总合并和数据治理 |
| Ops | Customer Merge | 名称/别名模糊候选、只读迁移预览和 Leader 安全合并 |

## 快速开始

### 团队桌面安装包

Windows 与 macOS 的内部测试安装包由 `.github/workflows/build-installers.yml` 在原生系统上构建。成员安装和设备激活见 [成员安装指南](docs/deployment/member-install-guide.md)，Leader 创建账号、签发、续期和恢复见 [Leader 授权指南](docs/deployment/leader-authorization-guide.md)。

当前安装包为 `UNSIGNED-INTERNAL` 试运行版；完整签名和发布门槛见 [发布手册](docs/deployment/release-runbook.md)。

### 环境要求

- 安装包支持 Windows 10/11 x64
- 本次可下载安装包支持 macOS Apple Silicon arm64；不生成 Intel 安装资产
- Linux 不属于产品支持和发布范围

### 启动应用

```bash
# 进入项目目录
cd jpt-sales-toolkit

# 首次运行前安装完整依赖
python3 -m pip install -r requirements.txt

# 运行
python3 run.py
```

浏览器会自动打开 `http://127.0.0.1:8000`

### 命令行参数

```bash
# 指定端口
python3 run.py --port 8080

# 指定隔离数据目录（仅用于测试、迁移或单机恢复）
python3 run.py --data-dir "/path/to/isolated/data"

# 不自动打开浏览器
python3 run.py --no-browser
```

`run.py` 当前启动的是 v2 单机版入口：`backend.app_v2:app`。

`--data-dir` 不得指向网络盘供多台电脑并发使用；当前 SQLite 单机架构不支持多个终端同时写同一目录。团队成员各自使用本机数据目录；Sales 使用定向 JSON，Tech 使用独立 `.jpttask / .jptresult` 任务包同步。未来集中部署时应由单一服务器进程管理数据库，成员通过浏览器访问。

### 局域网试运行

macOS 可直接运行项目根目录的：

```text
Start JPT LAN Test Server.command
```

脚本只创建/刷新六个保留名称的演示账号、执行启动前备份，并输出本机和局域网访问地址。演示密码每次随机生成，只写入权限为 `0600` 的 `data-test-server/lan_test_accounts.md`；其他既有团队账号和密码不会被修改，也不会写入该清单。

### 验证回归

```bash
cd jpt-sales-toolkit
bash scripts/validate_v08.sh
```

该脚本会运行前端语法检查、后端编译检查和关键业务回归测试。

需要运行浏览器 smoke 时，必须显式使用隔离测试账号，脚本不再内置默认口令：

```bash
SMOKE_USER="leader01" SMOKE_PASSWORD="<账号清单中的一次性密码>" \
  bash scripts/browser_smoke_v09.sh "http://127.0.0.1:8000"
```

## 多终端数据共享

### 工作流程

1. **Sales 日常使用**：各自在本地运行工具，处理自己负责区域的询盘
2. **定期导出**：通过 Export / Import 导出 JSON 数据包
3. **发送给 Leader**：通过内部约定渠道发送导出的 JSON 文件
4. **Leader 合并**：Leader 导入各 Sales 的文件，系统按权限和匹配规则合并

Tech 不使用上述 Sales JSON 链路。Leader 在独立“Tech Task Packages / 技术任务包”页签选择精确 Tech 账号，导出该账号当前全部未归档分配任务的完整快照 `.jpttask`；Tech 预检、导入并在售前/样品或售后任务中保存结果，导出 `.jptresult` 回传，Leader 预检后合并。同一结果字段双方改成不同值时整包阻断，不同字段可合并；新完整快照只有在 Tech 没有未导出修改，或结果已导出且此后未再修改时，才可撤回其中缺失的旧任务。任务包不包含报价、金额、联系人或附件文件，首版没有设备数字签名，只能通过可信内部渠道点对点传递。

Tech 左侧“售前 / 样品管理”和“售后”的数字是本人当前有效工作量：分别统计状态为 `Open / In Progress`、任务/Lead/客户均未归档且当前仍分配给该 Tech 的去重 Lead 数。页面选择“全部任务”时还会展示已完成或已取消任务，因此卡片/任务总数可以大于左侧数字；这不是漏导入。

### 合并规则

- 新增记录：直接添加
- 已有记录：按 legacy/source lead、客户邮箱、公司名等规则匹配合并
- 权限限制：非 Leader 只能导入自己有权限的 leads
- 附件限制：JSON 导出只包含附件元数据，不包含附件文件本体

### Excel 历史数据导入

程序安装和 Excel 数据导入是两条独立链路。Leader 在程序安装、账号激活和基础功能验收完成后，使用单独分发的 `JPT-XLSX-1.0` 标准模板或外部工作簿，按“上传 → 预检 → 人工修正 → 正式提交”导入。安装包不内置 XLSX、业务数据或成员授权文件。XLSX 不创建账号；来源人员必须匹配到现有 Leader / Sales / Tech 成员。字段、外部键、客户别名和重复导入口径见 [标准导入格式](docs/import-workbook-standard.md)。

### 业务地区与跟进时间

- 负责人账号的业务地区固定为 `GLOBAL / 欧洲 / 北美/加拿大/澳洲 / 俄罗斯/土耳其/中东 / 东南亚`。`GLOBAL` 是真实业务归属，不等于“全部地区”；清除地区条件应选择“全部地区”。
- 业务地区按 Lead 负责人账号划分，不根据客户所在国家推断。地区、负责人、技术、搜索和时间条件同时生效。
- “已逾期 / 今日到期 / 未来 7 天”按计划的下一次跟进日期筛选；“长期未跟进”按最近正式跟进日期回退到询盘日期、再回退到创建日期计算。

### 地图与客户合并

- 地图将坐标区分为精确、近似和缺失。近似点只表示区域参考，不能替代实际地址；离线或底图不可用时仍可通过列表和坐标质量状态处理数据。
- 地址搜索和批量地理编码不是纯本地功能：地址、城市、邮编和国家会通过 HTTPS 发送给一个或多个外部服务。默认使用公共 Nominatim；只有在本机安全设置 `JPT_GEOCODING_PROVIDER=amap` 和服务端 Web Service Key `JPT_AMAP_WEB_SERVICE_KEY` 后才优先使用高德。高德发生空结果、网络、超时、配额或无效响应时会回退 Nominatim，因此同一地址可能依次发送给两者；Key/权限错误不会被回退掩盖。界面会显示实际返回候选的服务商。
- 高德只承担可选地理编码，不替换当前 CARTO/OpenStreetMap 底图；高德结果会在服务端从 GCJ-02 转为统一的 WGS84。打开地图还会向瓦片服务发送网络地址及当前视窗/瓦片坐标。公共 Nominatim 只适合小规模、单终端、一次性且缓存的查询，不用于经常性或大规模批处理。Key 不得写入前端、仓库、安装包或共享文档；不允许外发的客户地址请改用人工经纬度或地图选点。
- 自动候选始终保留为待人工复核；Leader、owner 和 collaborator 可修正坐标，watcher 与 Tech 只读。版本冲突会要求刷新重试，不会静默覆盖另一终端的新修改。
- Leader 可按客户名称或别名查看模糊候选与匹配分数。选择来源和保留目标后，必须先核对只读迁移预览，再执行一次合并；来源客户会归档而不是物理删除。

### Trip Planner v2

- 先设置中国出发地、返程地、日期窗和可用交通方式，再选择自动顺序或手工顺序。路线不得超过结束日期；日期、地点、停留时长或顺序变化后，应重新预览并保存。
- 每段行程可使用航班、自驾、公共交通或其他方式，也可填写人工时长、距离和备注并锁定。交通建议不需要账号或 Token；应用会给出近似估算和外部查询链接，最终方式由使用者确认。
- 除客户拜访外，可加入酒店、休息、机场、中转和其他自由停靠点。日程按上午/下午排列，支持半天停留、多地点和同一客户多次拜访。
- 每次客户拜访可补充地址快照、客户人员、渠道代理公司陪同人员（如有）、JPT 内部参会人员、Demo/PO/其他设备、拜访议题和确认状态。路线日期或地点改变后，相关拜访会提示重新确认。
- 正式分发可下载 XLSX、离线 HTML 和 ICS；原 Markdown、CSV 仍可使用。导出前应保存当前路线，过期路线或未保存修改不会进入正式文件。

## 配置文件说明

```
config/
├── fields.json     # 字段定义（可自定义扩展）
├── regions.json    # 区域和国家配置
├── products.json   # 产品目录
├── user.json       # 仅用于旧版迁移的空白模板，不进入安装包
└── team.json       # 仅用于旧版迁移的三角色模板，不进入安装包
```

账号、角色和设备授权的当前数据源是 SQLite 授权目录与 `.jptauth`，不是 `user.json` / `team.json`。

### 字段配置

`config/fields.json` 负责已有业务字段的标签、控件类型和选项。修改显示配置不会自动创建数据库字段或后端 API 契约。

新增可持久化字段时，必须同时补齐存储口径、API 模型、详情读取/保存映射和回归测试；仅需保留但不参与筛选统计的字段，可按现有文档约定集中存入实体的 `extra_json`，不能只在界面配置中声明。

显示配置示例：

```json
{
  "field_groups": {
    "custom": {
      "label": "自定义字段组",
      "fields": {
        "my_field": {
          "type": "string",
          "label": "My Custom Field"
        }
      }
    }
  }
}
```

## 数据存储

```
data/
├── database.sqlite # v2 主数据库
├── attachments/    # 附件文件
├── backups/        # 全量备份 zip
├── config/         # JWT 密钥、授权时钟及 Leader 加密签发密钥
├── exports/        # 导出文件
└── imports/        # 导入暂存
```

## 技术栈

- **后端**: Python + FastAPI
- **前端**: HTML/CSS/JavaScript + Leaflet 地图
- **数据**: SQLite 本地数据库 + JSON 数据交换 + 受控 XLSX 导入

## 常见问题

**Q: 如何在多台电脑上使用？**

A: 每台电脑独立运行；Leader 创建成员，成员提交 `.jptreq`，Leader 返回设备绑定且固定 90 天的 `.jptauth`。业务数据仍通过导出/导入同步。

**Q: 数据丢失怎么办？**

A: 先完全退出 JPT 并保留现场。`pre_upgrade_...zip` 仅用于管理员执行 schema 数据库回滚；普通全量备份包含数据库、附件和授权配置，必须走经认证的完整恢复流程。两者都属于高敏感文件，不得上传 GitHub 或普通共享目录。JSON 导出只用于数据交换，不等同于完整备份，因为它不包含附件文件本体。

**Q: 如何添加新的产品系列？**

A: 编辑 `config/products.json` 文件，添加新的产品信息。

---

*JPT Sales Toolkit v0.12.0-internal · UNSIGNED-INTERNAL Draft Pre-release candidate*
