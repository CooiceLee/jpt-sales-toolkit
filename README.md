# JPT Sales Toolkit

面向 JPT 海外销售团队的全流程效率工具集。

当前内部试运行基线：`v0.11.0-internal`。当前启动、账号授权、备份、回归、地图坐标、数据复盘、出差规划、拜访执行和数据治理入口见 [docs/current-internal-runbook.md](docs/current-internal-runbook.md)。

## 功能概览

| Step | 模块 | 功能 |
|------|------|------|
| 1 | Inquiry Parser | 解析询盘邮件，自动提取客户和需求信息 |
| 2 | Inquiry Handler | 管理询盘记录，编辑客户信息和需求评估 |
| 3 | Follow-up Tracker | 跟进记录管理 |
| 4 | Sample Manager | 打样流程管理 |
| 5 | Deal Closer | 报价和成交管理 |
| 6 | Order Fulfillment | 订单履行跟踪 |
| 7 | After-sales Support | 售后问题管理 |
| Data | Data Review | 经营复盘、风险 Lead、高价值 Lead 和权限隔离分析 |
| Data | Trip Planner | 候选客户、区域路线、停留时间、拜访执行、结果回填和导出 |
| Data | Coordinate Review | 坐标质量队列、地图选点、经纬度录入和地址解析选点 |
| Ops | Export / Import | 销售数据包导出、导入预检、Leader 汇总导入、权限过滤合并和数据治理 |

## 快速开始

### 团队桌面安装包

Windows 与 macOS 的内部测试安装包由 `.github/workflows/build-installers.yml` 在原生系统上构建。成员安装和设备激活见 [成员安装指南](docs/deployment/member-install-guide.md)，Leader 创建账号、签发、续期和恢复见 [Leader 授权指南](docs/deployment/leader-authorization-guide.md)。

当前安装包为 `UNSIGNED-INTERNAL` 试运行版；完整签名和发布门槛见 [发布手册](docs/deployment/release-runbook.md)。

### 环境要求

- 安装包支持 Windows 10/11 x64
- 安装包支持 macOS Apple Silicon arm64 与 Intel x86_64
- Linux 不属于产品支持和发布范围

### 启动应用

```bash
# 进入项目目录
cd jpt-sales-toolkit

# 运行（首次运行会自动安装依赖）
python3 run.py
```

浏览器会自动打开 `http://127.0.0.1:8000`

### 命令行参数

```bash
# 指定端口
python3 run.py --port 8080

# 指定数据目录（用于多终端共享）
python3 run.py --data-dir "/path/to/shared/data"

# 不自动打开浏览器
python3 run.py --no-browser
```

`run.py` 当前启动的是 v2 单机版入口：`backend.app_v2:app`。

### 局域网试运行

macOS 可直接运行项目根目录的：

```text
Start JPT LAN Test Server.command
```

脚本会创建/刷新测试账号、启动前备份，并输出本机和局域网访问地址。
如果 `data-test-server/` 里已经有你导入的真实团队用户，脚本也会把这些现有账号刷新成可登录的 LAN 测试密码，并生成 `data-test-server/lan_test_accounts.md` 账号清单。

### 验证回归

```bash
cd jpt-sales-toolkit
bash scripts/validate_v08.sh
```

该脚本会运行前端语法检查、后端编译检查和关键业务回归测试。

## 多终端数据共享

### 工作流程

1. **Sales 日常使用**：各自在本地运行工具，处理自己负责区域的询盘
2. **定期导出**：通过 Export / Import 导出 JSON 数据包
3. **发送给 Leader**：通过内部约定渠道发送导出的 JSON 文件
4. **Leader 合并**：Leader 导入各 Sales 的文件，系统按权限和匹配规则合并

### 合并规则

- 新增记录：直接添加
- 已有记录：按 legacy/source lead、客户邮箱、公司名等规则匹配合并
- 权限限制：非 Leader 只能导入自己有权限的 leads
- 附件限制：JSON 导出只包含附件元数据，不包含附件文件本体

### Excel 历史数据导入

程序安装和 Excel 数据导入是两条独立链路。Leader 在程序安装、账号激活和基础功能验收完成后，使用单独分发的 `JPT-XLSX-1.0` 标准模板或外部工作簿，按“上传 → 预检 → 人工修正 → 正式提交”导入。安装包不内置 XLSX、业务数据或成员授权文件。XLSX 不创建账号；来源人员必须匹配到现有 Leader / Sales / Tech 成员。字段、外部键、客户别名和重复导入口径见 [标准导入格式](docs/import-workbook-standard.md)。

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

A: 使用 `data/backups/` 中的全量备份恢复。JSON 导出主要用于数据交换，不等同于完整备份，因为它不包含附件文件本体。

**Q: 如何添加新的产品系列？**

A: 编辑 `config/products.json` 文件，添加新的产品信息。

---

*JPT Sales Toolkit v0.11.0-internal*
