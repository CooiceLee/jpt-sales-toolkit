# 桌面安装包发布手册

当前团队测试 / Pre-release 候选：`v0.11.9-internal`。本次只发布 Windows 10/11 x64 与 macOS Apple Silicon arm64 两个原生安装包。源码和两项原生 CI 门禁完成前，GitHub Release 保持 Draft；门禁通过后可转为非 Draft 的 Pre-release 供团队下载。覆盖升级以 `v0.11.8-internal` 为直接基线；团队实测通过前，本候选不得标记为 Stable / Latest。

## 构建入口

GitHub Actions 工作流：`.github/workflows/build-installers.yml`。

- 手动运行：完成源码回归，构建两个内部测试安装包及 `SHA256SUMS.txt` 并保存在 Actions Artifacts。
- 只接受与 `VERSION` 完全一致的 `v*-internal` 标签：完成同样构建后创建标记为 Pre-release 的 Draft Release，并生成 `SHA256SUMS.txt`。普通 `v*` 或非 internal 版本会在构建前被拒绝。
- Windows 与 Apple Silicon Mac 必须在对应原生 Runner 上分别冻结；不接受 macOS 交叉生成 Windows 作为验证证据。本次工作流和 Release 不生成 Intel 安装资产。
- Linux 不构建、不分发，也不属于产品支持范围。Ubuntu Runner 仅用于内部源码预检。

## 产物

- Windows x64 Inno Setup EXE。
- macOS arm64 DMG。
- SHA-256 校验文件。

安装包只含统一程序，不按角色编译不同二进制。成员、角色、设备和到期时间只由 Leader 签发的 `.jptauth` 决定。业务 XLSX、标准导入模板、业务数据库和终端同步数据包必须作为独立文件分发。

## 发版门槛

1. `bash scripts/validate_v08.sh` 全部通过。
2. 每个冻结程序通过版本一致性、`/api/health`、首次 Leader 初始化、登录、`.jptreq` 生成和经认证退出烟测。
3. CI 必须通过 Windows 静默安装后启动/卸载烟测，以及 macOS DMG 校验、挂载后启动烟测；产物中不得出现旧用户配置、浏览器回归页面、XLSX、`.jptauth`、`.jptreq` 或业务数据库。
4. 用实际 Windows 10/11 x64 与 Apple Silicon Mac 各完成一次安装、`Exit JPT`、重启和从 `v0.11.8-internal` 覆盖升级。
5. 验证数据库、附件、授权密钥和签发密钥在升级后不变。
6. 验证卸载不删除用户数据。
7. 安装通过后再独立验证 XLSX 预检、提交、幂等更新和回滚；不得用预装数据掩盖安装问题。
8. 独立验证来源人员映射、三角色权限边界，以及 JSON 数据包分发同步；验证 `.jptauth` 未进入 GitHub Artifact 或 Release。
   Leader 向 Sales 导出时必须选择明确接收成员，文件只含该 Sales 负责的 Lead；导入端必须拒绝写给其他成员的定向包。旧版未携带接收成员信息的 JSON 仍按记录权限逐条过滤。
9. 使用真实或等价数据验证五类负责人业务地区、组合筛选、计划到期与长期未跟进的独立口径、客户模糊候选/预览/合并，以及地图精确/近似/缺失和离线提示。
10. 检查 `docs/guides/` 四份 HTML 可离线打开、互相跳转、版本一致，且不包含真实客户、账号、密钥或本机路径。
11. 在处理、跟进、售前/样品、成交、履约和售后页核对固定业务排序；缺失/无效日期应落在有效日期之后，同值排序在刷新后保持稳定。Tech 还须确认左侧售前/售后数字按本人 `Open / In Progress`、未归档任务对应的去重 Lead 计数；“全部任务”含已完成/已取消任务时，任务总数可大于导航数字。
12. 正式版必须补齐 Windows 代码签名和 macOS Developer ID、Hardened Runtime、notarization、stapling；在此之前产物只能标记 `UNSIGNED-INTERNAL`。

## 覆盖升级的数据保护门

新版第一次打开需要 schema 迁移的旧数据库时，必须按以下固定顺序执行，不能跳步：

1. 只读识别当前 `app_schema_migrations` 版本；若数据库比程序更新，拒绝降级启动。
2. 在任何 schema 写入前，在本地 `data/backups/` 创建 `pre_upgrade_schema<旧>_to_schema<新>_<时间>.zip`。
3. 备份包含 SQLite 一致性快照、附件和运行授权配置；不包含 `desktop.lock`、`desktop_instance.json` 等瞬时运行文件。
4. 成品备份必须通过 ZIP CRC、逐文件 SHA-256、SQLite `integrity_check`、外键检查和表行数清单校验。
5. 迁移在事务中完成并写入应用 schema 账本；迁移后再次检查数据库完整性和目标版本。
6. 任一步失败，自动从刚生成的备份恢复原数据库并停止启动；不得带病进入业务页面。
7. 同一版本第二次启动不得重复迁移、重复创建升级备份或改写业务数据库。

发布 Gate 必须同时跑 `test_safe_upgrade.py`，并保留 Windows 0.11.3、macOS 0.11.4 与 v0.11.7 schema 1 历史夹具作为旧版本兼容回归。本次 Windows x64、macOS Apple Silicon arm64 还必须执行实际 `v0.11.8 schema 3 → v0.11.9 schema 3` 原位覆盖升级：先做完整备份，再核对核心表数量、Tech 任务包表、附件哈希、授权配置、设备授权、完整性、外键及二次启动数据库哈希。由于 schema 版本不变，此直接升级不应伪造新的 `pre_upgrade` 迁移包；Windows 卸载后数据目录仍必须存在。

自动升级失败时，先保留弹窗或 `launcher.log` 证据，不要删除数据目录。完全退出 JPT 后，管理员可直接使用已安装程序的离线恢复入口，不依赖源码环境：

```text
Windows:
"%LOCALAPPDATA%\Programs\JPT Sales Toolkit\JPT Sales Toolkit.exe" --recover-backup "<pre_upgrade...zip>"

macOS:
"/Applications/JPT Sales Toolkit.app/Contents/MacOS/JPT Sales Toolkit" --recover-backup "<pre_upgrade...zip>"
```

该入口会先取得正常的单实例锁，确认 JPT 没有占用数据目录，再验证备份并只恢复数据库。它只接受自动升级门生成、且清单中 `backup_kind` 为 `pre_upgrade` 的 ZIP；普通完整备份必须走完整恢复流程。替换数据库前，程序会先创建并校验 `data/backups/pre_recovery_current_<时间>.sqlite`，若当前数据库无法安全保存则恢复不会开始。附件和授权配置在 schema 迁移中不会被修改，因此保持原位。恢复完成前不要再次启动新版。源码维护环境也可使用等价的 `python scripts/recover_pre_upgrade.py` 工具。

## 地理编码服务与 Key 边界

- 地址搜索与批量地理编码会把地址、城市、邮编和国家通过 HTTPS 发送给一个或多个外部服务商；默认使用公共 Nominatim。发布说明、界面确认和团队测试必须明确这不是纯本地处理，禁止外发的数据只能使用人工经纬度或地图选点。
- 可选高德只使用服务端 Web Service Key。运行 JPT 前必须由管理员在受控终端为 JPT 启动进程同时提供 `JPT_GEOCODING_PROVIDER=amap` 与 `JPT_AMAP_WEB_SERVICE_KEY`；未同时配置时保持 Nominatim 默认路径。高德空结果、网络、超时、配额或无效响应会回退 Nominatim，所以同一地址可能依次发送给两者；鉴权/权限错误保持可见且不回退。界面必须显示实际返回候选的服务商。
- 高德返回坐标由后端从 GCJ-02 转成 WGS84 后才写入数据库。高德当前只替换可选地理编码，不替换 CARTO/OpenStreetMap 底图；打开地图会向瓦片服务发送终端网络地址以及视窗/瓦片坐标。自动候选保持待复核，不能直接标记为人工精确位置。
- 公共 Nominatim 请求必须保持单线程、每秒不超过 1 次并使用本地缓存；只允许小规模、单终端、一次性批处理。大规模、周期性或多终端任务必须改用明确获授权的服务或自建实例。
- Windows 开始菜单启动要求写入当前用户的受控系统环境并退出/重新登录 Windows；macOS Finder 启动要求由 `launchd` 或 MDM 注入当前 GUI 会话。普通 PowerShell、Terminal 临时变量不会自动传给已运行的 Explorer/Finder。当前版本没有 Key 输入界面，不满足这项部署条件时不得宣称已经启用高德。
- Key 不得写入 GitHub（包括仓库、Secrets 和 Actions）、前端 JavaScript、HTML 指南、安装包、截图、测试夹具或日志。构建产物不内置团队 Key；每台获授权终端由管理员单独配置并验证额度和权限。

## 地图验收口径

- 坐标存储与 Leaflet 显示统一使用 WGS84；纬度必须在 -90 至 90、经度必须在 -180 至 180，空值、非有限值、单边坐标和越界旧值必须进入复核而不是显示为精确点。
- Leader、Lead owner 和 collaborator 可修改有权访问客户的位置；watcher 与 Tech 只读。前端隐藏写入口不代替后端权限校验。
- 地址搜索与坐标保存互斥；切换客户、编辑地址或较新的 `row_version` 必须使旧结果/旧保存失效。出现 409 时加载最新数据并要求人工重试。
- 地图请求失败后清空旧 marker、旧 `State.mapData` 和批量状态；离线底图不阻塞列表、筛选、坐标质量与人工经纬度修正。

## 回滚

安装程序只替换应用目录，用户数据目录不会被安装或卸载流程删除。自动 `pre_upgrade` 包是发生 schema 迁移时数据库回滚的依据；无 schema 变化的直接升级应先使用 Leader/管理员创建的完整备份。不要手工复制正在运行的 SQLite 文件，也不要通过删除数据目录刷新界面。

`--recover-backup` 是数据库 schema 回滚入口，只接受 `pre_upgrade` 包，不恢复附件或授权配置。普通完整备份包含数据库、附件、账号凭据及授权/签发配置，只能由 Leader/管理员通过经认证的完整恢复接口处理；恢复期间独占维护门会阻止新业务请求。0.11.3 旧清单格式允许兼容恢复，但所有 ZIP 成员仍必须与旧清单完全一致并通过路径、类型、大小、CRC、哈希和 SQLite 完整性校验；旧锁与实例状态永不恢复。两类备份都按高敏感文件管理，不上传 GitHub、Release 或普通团队共享目录。
