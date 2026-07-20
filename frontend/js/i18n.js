/** Centralized English / Simplified Chinese UI language layer. */
(function () {
    const STORAGE_KEY = 'jpt_ui_language';
    const pairs = [
        ['Sign in to continue', '登录后继续'], ['Username', '用户名'], ['Enter username', '请输入用户名'],
        ['Password', '密码'], ['Enter password', '请输入密码'], ['Sign In', '登录'],
        ['Activate JPT Sales Toolkit', '激活 JPT 销售工具包'],
        ['Create the first Leader on this computer. This one-time setup also creates the protected signing key used for all team authorizations.', '在这台电脑上创建首名 Leader。此一次性设置还会创建受保护的签名密钥，用于签发全部团队授权。'],
        ['Leader username', 'Leader 用户名'], ['Display name', '显示名称'], ['Region (optional)', '区域（可选）'],
        ['Login password (8+ characters)', '登录密码（至少 8 位）'], ['Confirm login password', '确认登录密码'],
        ['Issuer passphrase (12+ characters)', '签发口令（至少 12 位）'], ['Confirm issuer passphrase', '确认签发口令'],
        ['Store the issuer passphrase separately. It is required whenever you sign or renew a member authorization.', '请单独妥善保存签发口令。每次签发或续期成员授权时都需要使用。'],
        ['Create Leader & Initialize', '创建 Leader 并初始化'], ['Join an Existing Team', '加入现有团队'],
        ['← Set up a new team instead', '← 改为创建新团队'], ['Recover this Leader device', '恢复此 Leader 设备'],
        ['The local signing key is available. Use both Leader credentials to renew an expired authorization or bind a restored backup to this computer.', '本机已有签名密钥。请同时使用 Leader 登录凭据和签发口令，为过期授权续期或将恢复后的备份绑定到本机。'],
        ['Leader login password', 'Leader 登录密码'], ['Issuer passphrase', '签发口令'],
        ['Recover Leader Authorization', '恢复 Leader 授权'],
        ['This installation needs a device-bound authorization from your Leader before you can sign in.', '此安装需要先导入 Leader 签发的设备绑定授权，之后才能登录。'],
        ['Device', '设备'], ['Generated on request', '生成申请后显示'], ['Member', '成员'],
        ['No authorization imported', '尚未导入授权'], ['Send your device request', '发送设备申请'],
        ['Download the request and send the resulting', '下载申请，并将生成的'], ['file to your Leader.', '文件发送给 Leader。'],
        ['Download Device Request', '下载设备申请'], ['Import your authorization', '导入授权'], ['Select the', '选择 Leader 返回的'],
        ['file returned by your Leader, verify the code through a separate channel, then create your local password.', '文件，通过独立渠道核对验证码，然后创建本机密码。'],
        ['Leader verification code', 'Leader 验证码'], ['Create password', '创建密码'], ['Confirm password', '确认密码'],
        ['Activate This Device', '激活此设备'], ['Correct Location', '修正位置'], ['Address', '地址'],
        ['Paste an address from email, click on the map, or enter coordinates manually. Drag the marker to fine-tune.', '可粘贴邮件中的地址、点击地图或手动输入坐标；拖动标记可微调位置。'],
        ['Street, company park, building', '街道、园区、楼宇'], ['City', '城市'], ['Country', '国家'],
        ['Find on map', '在地图中查找'], ['Latitude', '纬度'], ['Longitude', '经度'], ['Cancel', '取消'], ['Save Location', '保存位置'],
        ['This will mark the location as manually verified and lock it from auto-geocoding.', '保存后将标记为已人工核验，并停止自动地理编码覆盖。'],
        ['Dashboard', '仪表盘'], ['Inquiry Parser', '询盘解析'], ['Inquiry Handler', '询盘处理'], ['Follow-up', '跟进'],
        ['Sampling', '样品'], ['Deal', '成交'], ['Fulfillment', '履约'], ['After-sales', '售后'],
        ['Data Review', '数据复盘'], ['Trip Planner', '出差规划'], ['Coordinate Review', '坐标复核'],
        ['Team & Authorization', '团队与授权'], ['Export/Import', '导出/导入'], ['Export / Import', '导出 / 导入'],
        ['Sales Toolkit', '销售工具包'], ['Jump to inquiry, country...', '跳转到询盘、国家……'],
        ['Overview', '概览'], ['Pipeline Funnel', '销售漏斗'], ['Parser', '解析'], ['Handler', '处理'],
        ['Data', '数据'], ['Administration', '管理'], ['User', '用户'], ['Sales', '销售'], ['Tech', '技术'], ['Leader', 'Leader'],
        ['👤 Switch Account', '👤 切换账号'], ['🚪 Logout', '🚪 退出登录'], ['⏹ Exit JPT', '⏹ 退出 JPT'],
        ['Finish installing JPT', '请完成 JPT 安装'],
        ['This app is running from the DMG. Quit JPT, drag it to Applications, eject the DMG, then open it from Applications.', '当前程序正从 DMG 磁盘映像运行。请退出 JPT，将程序拖入“应用程序”，推出 DMG，再从“应用程序”打开。'],
        ['Pipeline', '销售管线'], ['Total Inquiries', '询盘总数'], ['All time', '全部时间'], ['Last 7 Days', '最近 7 天'],
        ['New inquiries', '新增询盘'], ['Following', '跟进中'], ['Active follow-ups', '进行中的跟进'],
        ['Won Deals', '已赢单'], ['Closed won', '已成交'], ['Won Value', '成交金额'], ['Total deal amount', '成交总金额'],
        ['Review Map', '复盘地图'], ['Customer Location Map', '客户位置地图'],
        ['Loading map data...', '正在加载地图数据……'], ['Stage', '阶段'], ['All stages', '全部阶段'],
        ['New', '新建'], ['Assigned', '已分配'], ['Quoted', '已报价'], ['Won', '赢单'], ['Lost', '丢单'],
        ['Outcome', '结果'], ['All outcomes', '全部结果'], ['Open', '待处理'], ['Region', '区域'], ['All regions', '全部区域'],
        ['Europe', '欧洲'], ['Southeast Asia', '东南亚'], ['Americas', '美洲'], ['Russia/India/ME', '俄罗斯/印度/中东'],
        ['Customer geographic region', '客户地理区域'], ['All customer geographies', '全部客户地理区域'],
        ['Coordinate quality', '坐标质量'], ['All coordinates', '全部坐标'], ['All mapped coordinates', '全部已定位坐标'],
        ['Exact only', '仅精确坐标'], ['Needs geocode', '需要地理编码'], ['Approximate only', '仅近似坐标'],
        ['Precise customer location', '精确客户位置'], ['Auto approximate location', '自动近似位置'], ['verify', '待核验'],
        ['Country aggregate — not a precise customer location', '国家聚合点——不是精确客户位置'],
        ['{count} customers are grouped at the country center until precise coordinates are added.', '{count} 位客户暂按国家中心聚合显示，补充精确坐标后将分别显示。'],
        ['{customers} customers · {markers} visible markers · {exact} precise · {approximate} approximate · {missing} missing', '{customers} 位客户 · {markers} 个可见标记 · {exact} 个精确 · {approximate} 个近似 · {missing} 个缺失'],
        ['Coordinate quality legend', '坐标质量图例'], ['Precise', '精确'], ['Auto approximate', '自动近似'],
        ['Country aggregate', '国家聚合'], ['Missing — not mapped', '缺失——不在地图显示'],
        ['Unknown country', '未知国家'], ['Open Coordinate Review', '打开坐标复核'],
        ['Map data unavailable. Try again.', '地图数据不可用，请重试。'],
        ['Map background unavailable while offline. Points and lists still work.', '当前离线，地图底图不可用；点位和列表仍可使用。'],
        ['Map background could not load. Points and lists still work.', '地图底图加载失败；点位和列表仍可使用。'],
        ['Reconnecting map background...', '正在重新连接地图底图……'],
        ['Batch Geocode', '批量地理编码'],
        ['Re-geocode customers without precise coordinates', '为缺少精确坐标的客户重新编码'],
        ['Step 01 · Inquiry Parser', '步骤 01 · 询盘解析'], ['Raw Email', '原始邮件'], ['Paste', '粘贴'], ['Clear', '清空'],
        ['Paste the inquiry email content here...', '在此粘贴询盘邮件内容……'], ['chars', '字符'],
        ['⚡ Parse with AI', '⚡ 使用 AI 解析'], ['Extracted Fields', '提取字段'], ['Discard', '放弃'],
        ['✓ Save as new inquiry', '✓ 保存为新询盘'], ['Step 02 · Inquiry Handler', '步骤 02 · 询盘处理'],
        ['Search company, ID, country...', '搜索公司、编号、国家……'], ['+ New Inquiry', '+ 新建询盘'],
        ['Step 03 · Follow-up Tracker', '步骤 03 · 跟进管理'], ['All Active', '全部进行中'], ['Overdue', '已逾期'],
        ['Due today', '今日到期'], ['Next 7 days', '未来 7 天'], ['+ Log follow-up', '+ 记录跟进'],
        ['Last activity', '最近业务活动'], ['Any activity time', '不限活动时间'],
        ['Never formally followed up', '从未正式跟进'], ['Inactive 7+ days', '超过 7 天未跟进'],
        ['Inactive 14+ days', '超过 14 天未跟进'], ['Inactive 30+ days', '超过 30 天未跟进'],
        ['Inactive 60+ days', '超过 60 天未跟进'], ['Inactive 90+ days', '超过 90 天未跟进'],
        ['Custom activity dates', '自定义活动日期'], ['From', '起始'], ['Through', '截止'],
        ['Last activity from', '最近活动起始日期'], ['Last activity through', '最近活动截止日期'],
        ['Uses the latest formal follow-up; otherwise the inquiry or creation date.', '优先使用最近正式跟进日期；没有正式跟进时使用询盘日期或创建日期。'],
        ['Step 04 · Sample Manager', '步骤 04 · 样品管理'],
        ['Step 04 · Pre-sales / Sample Manager', '步骤 04 · 售前 / 样品管理'],
        ['Step 04 · Pre-sales / Sampling', '步骤 04 · 售前 / 样品管理'],
        ['Pre-sales / Sampling', '售前 / 样品管理'], ['Pre-sales / Sample', '售前 / 样品'],
        ['Pre-sales / Samples', '售前 / 样品'], ['All pre-sales / samples', '全部售前 / 样品'],
        ['Search customer, contact, country', '搜索客户、联系人、国家'],
        ['All sales', '全部销售'], ['All tech', '全部技术'],
        ['Business region', '业务地区'], ['Select business region', '选择业务地区'],
        ['Business region is required.', '请选择业务地区。'],
        ['All regions', '全部地区'], ['Europe', '欧洲'],
        ['North America / Canada / Australia', '北美/加拿大/澳洲'],
        ['Russia / Turkey / Middle East', '俄罗斯/土耳其/中东'],
        ['Southeast Asia', '东南亚'],
        ['All tasks', '全部任务'], ['+ New pre-sales task', '+ 新建售前任务'],
        ['All sampling', '全部样品'], ['In progress', '进行中'], ['In Progress', '进行中'],
        ['Completed', '已完成'], ['Cancelled', '已取消'], ['+ New sample request', '+ 新建样品申请'],
        ['Step 05 · Deal Closer', '步骤 05 · 成交管理'], ['Quoting', '报价中'], ['Closed Won', '已赢单'],
        ['Avg Cycle', '平均周期'], ['All deals', '全部交易'], ['+ Create quote', '+ 创建报价'],
        ['Step 06 · Order Fulfillment', '步骤 06 · 订单履约'], ['All orders', '全部订单'], ['Not started', '未开始'],
        ['+ Log status', '+ 记录状态'], ['Step 07 · After-sales', '步骤 07 · 售后'], ['All issues', '全部问题'],
        ['Resolved', '已解决'], ['+ Log issue', '+ 记录问题'], ['This month', '本月'], ['Last month', '上月'],
        ['This quarter', '本季度'], ['Custom', '自定义'], ['Refresh', '刷新'], ['Open Leads', '进行中商机'],
        ['Won Leads', '赢单商机'], ['Win Rate', '赢单率'], ['Stage Breakdown', '阶段分布'],
        ['Owner Performance', '负责人表现'], ['Region Performance', '区域表现'], ['Risk Leads', '风险商机'],
        ['High Value Open Leads', '高价值进行中商机'], ['New plan', '新建计划'], ['Candidate Customers', '候选客户'],
        ['Plan', '计划'], ['Plan title', '计划标题'], ['Origin', '出发地'], ['Destination', '目的地'],
        ['Origin lat', '出发地纬度'], ['Origin lng', '出发地经度'], ['Destination lat', '目的地纬度'], ['Destination lng', '目的地经度'],
        ['Auto transport', '自动选择交通'], ['Drive', '驾车'], ['Ground public', '地面公共交通'], ['Flight', '航班'],
        ['Skip weekends', '跳过周末'], ['Planning notes', '规划备注'], ['Preview route', '预览路线'], ['Save route', '保存路线'],
        ['Holidays: 2026-05-01, 2026-10-01', '节假日：2026-05-01, 2026-10-01'],
        ['Selected Stops', '已选停靠点'], ['Visit Execution', '拜访执行'], ['Needs Review', '需要复核'],
        ['Auto coordinates', '自动坐标'], ['Missing Coordinates', '缺少坐标'], ['No location data', '无位置数据'],
        ['Verified', '已核验'], ['Manually locked', '已人工锁定'], ['All Customers', '全部客户'], ['Missing', '缺失'],
        ['Search customer, city, country, address', '搜索客户、城市、国家、地址'],
        ['Create team identities, bind one device per member, and issue signed offline authorizations. Package roles are limited to Leader, Sales, and Tech.', '创建团队身份、为每名成员绑定一台设备并签发离线授权。全局角色仅限 Leader、Sales 和 Tech。'],
        ['Mode', '模式'], ['Active Members', '有效成员'], ['Bound Devices', '已绑定设备'], ['This Device', '本设备'],
        ['Issuer Security', '签发安全'], ['Initialize Issuer', '初始化签发器'], ['Issuer ready', '签发器已就绪'],
        ['Initialize this Leader device once. The signing key remains local and is protected by this passphrase.', '仅需初始化一次此 Leader 设备。签名密钥保留在本机并受签发口令保护。'],
        ['Renew This Leader Device · 90 Days', '续期此 Leader 设备 · 90 天'],
        ['Signing key not on this device', '本设备没有签名密钥'], ['Add member', '添加成员'],
        ['Restore the Leader backup containing the issuer key to sign packages here.', '请恢复包含签发密钥的 Leader 完整备份，之后才能在本机签发授权。'],
        ['Issue Device Authorization', '签发设备授权'], ['Select member', '选择成员'], ['Authorization days', '授权天数'],
        ["Import the member's device request. Reissuing for a replacement device supersedes the old device authorization.", '导入成员设备申请。为换机设备重新签发后，旧设备授权将被新授权取代。'],
        ['Issue & Download .jptauth', '签发并下载 .jptauth'], ['Team Members', '团队成员'], ['Loading members...', '正在加载成员……'],
        ['Authorization Audit', '授权审计'], ['Loading events...', '正在加载事件……'],
        ['Export Data', '导出数据'], ['Export your inquiries to share with your leader.', '导出本人询盘，用于与 Leader 交换数据。'],
        ['Note:', '注意：'], ['Attachment files are NOT included in JSON export (metadata only).', 'JSON 导出不包含附件文件本体，仅包含附件元数据。'],
        ['Export My Data', '导出我的数据'], ['Export successful!', '导出成功！'], ['Download File', '下载文件'],
        ['Export failed', '导出失败'],
        ['Excel import, JSON exchange and data governance are separated so each workflow can be tested independently.', 'Excel 导入、JSON 数据交换和数据治理相互独立，可分别完成验证。'],
        ['Data transfer workspace', '数据传输工作区'], ['Excel Import', 'Excel 导入'], ['JSON Exchange', 'JSON 数据交换'],
        ['Excel import progress', 'Excel 导入进度'], ['Full backup', '完整备份'], ['Select workbook', '选择工作簿'],
        ['Preflight & correct', '预检与修正'], ['Commit & verify', '提交与验证'],
        ['Preparation & workbook', '准备工作与工作簿'], ['Running version', '当前运行版本'],
        ['Full Backup Before Import', '导入前完整备份'],
        ['Includes the database, attachments and runtime authorization configuration. Keep the displayed backup path for rollback.', '完整备份包含数据库、附件和运行时授权配置。请保存页面显示的备份路径，以便回滚。'],
        ['Back up the database, attachments and authorization configuration before writing any workbook data.', '写入任何工作簿数据前，请先备份数据库、附件和授权配置。'],
        ['Create Full Backup', '创建完整备份'], ['Creating full backup...', '正在创建完整备份……'],
        ['Full backup created', '完整备份已创建'], ['Backup failed', '备份失败'], ['Unknown error', '未知错误'],
        ['Select JPT-XLSX-1.0 Workbook', '选择 JPT-XLSX-1.0 工作簿'],
        ['Leader-only · .xlsx · up to 25 MB. Preflight reads the file without writing business data.', '仅限 Leader · .xlsx · 最大 25 MB。预检只读取文件，不写入业务数据。'],
        ['Choose workbook', '选择工作簿'], ['No workbook selected', '尚未选择工作簿'], ['Run Preflight', '运行预检'],
        ['Preflight & Corrections', '预检与修正'],
        ['Mappings and issues stay inside this review window. Expand only the group you need.', '账号映射、客户匹配和问题均限制在此复核窗口中；仅展开需要处理的分组。'],
        ['Changes are not written until commit.', '提交前不会写入任何变更。'],
        ['Select a workbook and run preflight to review rows, account mappings, customer matches and issues.', '选择工作簿并运行预检，以复核数据行、账号映射、客户匹配和问题。'],
        ['Workbook selected. Run preflight to review its contents.', '工作簿已选择。请运行预检以复核内容。'],
        ['Run preflight before import', '请先运行预检'], ['Import complete', '导入完成'],
        ['Import & Merge', '导入并合并'], ['Importing...', '正在导入……'],
        ['Importing workbook...', '正在导入工作簿……'],
        ['blocking issues remain — resolve mappings or exclude invalid records, then recheck.', '个阻断项待处理——请完成账号映射或排除无效记录，然后重新预检。'],
        ['JSON keeps the existing member exchange flow. XLSX uses Leader-controlled preflight, correction and commit.', 'JSON 用于现有成员数据交换；XLSX 由 Leader 执行受控预检、修正和提交。'],
        ['JPT-XLSX-1.0 templates and source workbooks are distributed separately from the application installer.', 'JPT-XLSX-1.0 模板和源工作簿与应用安装程序分开分发。'],
        ['Import only merges data records. Attachment files must be transferred separately. For complete backup/restore, ask the administrator to use the server backup/restore procedure.', '导入只合并数据记录；附件文件必须单独传递。完整备份与恢复须由管理员使用服务端备份/恢复流程。'],
        ['JSON is for member-to-Leader record exchange. Attachment files are not included.', 'JSON 用于成员终端与 Leader 之间的数据交换，不包含附件文件本体。'],
        ['Import JSON Package', '导入 JSON 数据包'],
        ['Use JSON only for terminal data exchange. It is not the Excel history-import workflow.', 'JSON 仅用于终端数据交换，不属于 Excel 历史数据导入流程。'],
        ['Preflight JSON', '预检 JSON'], ['Import JSON', '导入 JSON'], ['Please select a JSON file first', '请先选择 JSON 文件'],
        ['Import Complete', '导入完成'], ['Total', '总数'], ['Customers created', '新增客户'],
        ['Customers updated', '更新客户'], ['Leads created', '新增商机'], ['Leads updated', '更新商机'],
        ['JSON Preflight Result', 'JSON 预检结果'], ['Allowed leads', '允许导入的商机'],
        ['Duplicates', '重复项'], ['Issues', '问题'], ['No field or enum issues found', '未发现字段或枚举问题'],
        ['Duplicate Signals', '重复信号'],
        ['Preflight Check', '预检'], ['Data Governance', '数据治理'], ['Normalize Countries / Regions', '规范化国家/区域'],
        ['Load Coordinate Audit', '加载坐标审计'], ['Customer IDs, one per line', '客户 ID，每行一个'],
        ['Lead IDs, one per line', '商机 ID，每行一个'], ['Owner ID', '负责人 ID'], ['Product category', '产品类别'],
        ['Application', '应用'], ['Run Batch Repair', '执行批量修复'], ['Customer Merge', '客户合并'],
        ['Select a duplicate source customer and merge it into the target customer that should remain active.', '选择重复的源客户，将其合并到需要保留的目标客户。'],
        ['Search by approximate customer name or alias. Select the duplicate source and the target customer that should remain active.', '支持按客户名称或别名模糊搜索。请选择重复源客户和需要保留的目标客户。'],
        ['Source duplicate', '重复源客户'], ['Search source customer', '搜索源客户'],
        ['Search source name or alias', '搜索源客户名称或别名'], ['Search', '搜索'],
        ['Target customer', '目标客户'], ['Search target customer', '搜索目标客户'],
        ['Search target name or alias', '搜索目标客户名称或别名'],
        ['Merge Source Into Target', '将源客户合并到目标客户'], ['Select two customers', '请选择两个客户'],
        ['Select both customers to run a safe merge preview.', '请选择源客户和目标客户，系统将自动执行安全合并预览。'],
        ['Customer merge is available to Leader only.', '客户合并仅限 Leader 使用。'],
        ['Enter at least two characters.', '请至少输入两个字符。'],
        ['Searching names and aliases...', '正在搜索客户名称和别名……'],
        ['No matching customers.', '未找到匹配客户。'], ['Search failed', '搜索失败'],
        ['No location', '无地区信息'], ['Matched name', '匹配名称'], ['Matched alias', '匹配别名'],
        ['No customer selected.', '尚未选择客户。'], ['Aliases', '客户别名'], ['Contacts', '联系人'],
        ['Version', '版本'], ['Error loading customer', '加载客户失败'],
        ['Source and target must be different customers.', '源客户和目标客户不能是同一个客户。'],
        ['Checking merge safety...', '正在检查合并安全性……'],
        ['Checking related records and conflicts...', '正在检查关联记录和字段冲突……'],
        ['Confirm merge', '确认合并'], ['Preview required', '需要先完成预览'],
        ['Merge preview failed', '合并预览失败'], ['Merge preview ready', '合并预览已就绪'],
        ['The source will be archived. The target remains active and keeps conflicting values.', '源客户将被归档；目标客户保持有效，并在字段冲突时保留目标值。'],
        ['Leads', '商机'], ['Conflicts', '冲突项'], ['Domains', '域名'],
        ['Field conflicts', '字段冲突'], ['Contact conflicts', '联系人冲突'],
        ['Domain and alias conflicts', '域名与别名冲突'], ['Source value', '源值'],
        ['Target value', '目标值'], ['Resolution', '处理方式'],
        ['Field', '字段'], ['Website', '网站'], ['Industry', '行业'],
        ['Customer type', '客户类型'], ['Company size', '企业规模'], ['Language', '语言'],
        ['Postal code', '邮政编码'], ['Address', '地址'], ['Region', '区域'],
        ['Latitude', '纬度'], ['Longitude', '经度'], ['Normalized address', '标准化地址'],
        ['Geocode source', '地理编码来源'], ['Geocode confidence', '地理编码置信度'],
        ['Geocode locked', '地理编码已锁定'], ['Company description', '企业简介'],
        ['Additional data', '附加数据'],
        ['Duplicate contact email', '重复联系人邮箱'], ['Duplicate domain', '重复域名'],
        ['Duplicate alias', '重复别名'], ['Keep target value', '保留目标值'],
        ['Preserve source value in audit record', '在审计记录中保留源值'],
        ['Fill missing target fields, keep target conflicts, archive source duplicate', '补齐目标空字段；冲突时保留目标值，并归档重复源联系人'],
        ['Keep target and archive source duplicate', '保留目标记录并归档重复源记录'],
        ['No conflicting values were found.', '未发现冲突值。'],
        ['Merge complete', '合并完成'], ['Leads moved', '已迁移商机'],
        ['Contacts moved', '已迁移联系人'], ['Aliases moved', '已迁移别名'], ['Domains moved', '已迁移域名'],
        ['Select both source and target customers.', '请选择源客户和目标客户。'],
        ['Run a successful preview before merging.', '必须先成功完成合并预览。'],
        ['Merge "{source}" into "{target}"? The source customer will be archived.', '确认将“{source}”合并到“{target}”吗？源客户将被归档。'],
        ['Merging...', '正在合并……'], ['Customers merged', '客户合并完成'], ['Merge failed', '合并失败'],
        ['Inquiry Details', '询盘详情'], ['Save Changes', '保存修改'],
        ['Please select a file first', '请先选择文件'], ['Import failed', '导入失败'],
        ['Controlled XLSX import is available to Leader accounts only.', '受控 XLSX 导入仅限 Leader 账号使用。'],
        ['Running controlled preflight...', '正在执行受控预检……'], ['Running JSON preflight...', '正在执行 JSON 预检……'],
        ['Run preflight and resolve every blocking issue before import.', '请先执行预检并处理全部阻断问题，然后再导入。'],
        ['Only a Leader can preflight or import XLSX files.', '只有 Leader 可以预检或导入 XLSX 文件。'],
        ['Spreadsheet Import Complete', 'Excel 导入完成'], ['Created', '新增'], ['Updated', '更新'],
        ['Archived', '已归档'], ['Skipped', '已跳过'], ['Warnings', '警告'], ['Batch', '批次'],
        ['Spreadsheet Preflight', 'Excel 预检'], ['Source rows', '源数据行'], ['Entities', '实体'], ['Errors', '错误'],
        ['Member account mapping', '成员账号映射'], ['Customer matching', '客户匹配'],
        ['Issues and exclusions', '问题与排除项'], ['No issues found', '未发现问题'],
        ['Apply corrections & recheck', '应用修正并重新预检'], ['Ready to import', '可以导入'],
        ['Resolve or exclude all blockers before import', '请处理或排除全部阻断项后再导入'],
        ['Exclude record', '排除此记录'], ['Create new customer', '创建新客户'], ['Select account', '选择账号'],
        ['Matched', '已匹配'], ['member', '成员'], ['customer', '客户'], ['mappings', '项映射'],
        ['customers', '位客户'], ['issues', '项问题'], ['owner', '负责人'], ['collaborator', '协作人'],
        ['watcher', '关注人'], ['actor', '操作人'], ['task_assignee', '任务负责人'],
        ['blocker', '阻断'], ['resolved', '已解决'], ['matched', '已匹配'], ['create', '新建'],
        ['exact', '精确匹配'], ['manual', '人工匹配'], ['binding', '历史绑定'], ['new', '新建'],
        ['new customer', '新客户'], ['unresolved', '未解决'], ['Only .xlsx workbooks are supported', '仅支持 .xlsx 工作簿'],
        ['Workbook exceeds the 25 MB limit', '工作簿超过 25 MB 上限'], ['Workbook is empty', '工作簿为空'],
        ['Existing linked pre-sales tasks differ or contain update history. Review and archive the duplicate tasks in the App, then run preflight again.', '已绑定的售前任务内容不同或包含独立更新记录。请先在 App 中复核并归档重复任务，然后重新运行预检。'],
        ['Pre-sales task data changed after preflight; run preflight again', '售前任务数据在预检后发生变化，请重新运行预检。'],
        ['Spreadsheet import failed', 'Excel 导入失败'], ['Preflight failed', '预检失败'],
        ['The spreadsheet request failed before the local service responded. The current workbook was not imported. Please run preflight again.', 'Excel 请求在本地服务响应前失败。当前工作簿尚未导入，请重新运行预检。'],
        ['The local JPT service stopped or could not be reached. The current workbook was not imported. Reopen JPT and run preflight again.', '本地 JPT 服务已停止或无法连接。当前工作簿尚未导入，请重新打开 JPT 后再次运行预检。'],
        ['The spreadsheet preflight response could not be read. The current workbook was not imported. Please run preflight again.', 'Excel 预检响应无法读取。当前工作簿尚未导入，请重新运行预检。'],
        ['The import outcome could not be confirmed because the local service stopped or its response could not be read. Reopen JPT, verify the navigation counts and target records, then retry only if no import was recorded.', '由于本地服务停止或响应无法读取，本次导入结果无法确认。请重新打开 JPT，核对左侧导航计数和目标业务记录；仅在确认没有导入记录后再重试。'],
        ['Import outcome unconfirmed — reopen JPT and verify the navigation counts and target records before any retry.', '导入结果无法确认——请重新打开 JPT，核对左侧导航计数和目标业务记录后再决定是否重试。'],
        ['Import completed, but navigation counts could not be refreshed. Reopen JPT to load the latest counts.', '导入已经完成，但左侧导航计数未能刷新。请重新打开 JPT 以加载最新计数。'],

        // Sales cards and inquiry detail panel
        ['Basic', '基础信息'], ['Customer', '客户'], ['Requirement', '需求'], ['Evaluation', '评估'],
        ['Sample', '售前 / 样品'], ['Follow-ups', '跟进记录'], ['Data Quality', '数据质量'], ['Files', '文件'],
        ['Product', '产品'], ['Amount', '金额'], ['Next action', '下一步行动'], ['Task status', '任务状态'],
        ['No formal follow-up', '尚无正式跟进'], ['Inactive for', '未跟进时长'], ['Next follow-up', '下次跟进'],
        ['{count} days inactive', '已 {count} 天未跟进'],
        ['{count} days since inquiry (no formal follow-up)', '尚无正式跟进 · 距询盘 {count} 天'],
        ['{count} days since creation (no formal follow-up)', '尚无正式跟进 · 距创建 {count} 天'],
        ['Pre-sales', '售前负责人'], ['Due', '截止日期'], ['Quotation', '报价单'], ['PO', '订单号'],
        ['Close note', '结单说明'], ['Status', '状态'], ['Expected', '预计交付'], ['Not Requested', '未发起'],
        ['Not Started', '未开始'], ['None', '无'], ['Closed', '已关闭'],
        ['{count} samples', '{count} 个售前 / 样品商机'],
        ['{count} sample', '{count} 个售前 / 样品商机'],
        ['{count} pre-sales / sample leads', '{count} 个售前 / 样品商机'],
        ['{count} to review', '{count} 项待复核'],
        ['{count} leads', '{count} 个商机'], ['{count} active', '{count} 个进行中商机'],
        ['{count} orders', '{count} 个订单'], ['{count} issues', '{count} 个问题'],
        ['{count} fields', '{count} 个字段'],
        ['Sent: {date}', '发送时间：{date}'], ['Response: {date}', '回复时间：{date}'],
        ['Next: {action}', '下一步：{action}'], ['Date: {date}', '日期：{date}'],

        // Pre-sales / sample task panel. Enum values stay English in form values and API payloads.
        ['Sample requests', '售前 / 样品任务'], ['+ New request', '+ 新建任务'],
        ['Edit', '编辑'], ['Update result', '更新结果'], ['Archive', '归档'], ['Restore', '恢复'],
        ['Unassigned', '未分配'], ['No sample parameters', '暂无任务需求'],
        ['No sample request yet.', '暂无售前 / 样品任务。'],
        ['Pre-sales owner', '售前负责人'], ['Due date', '截止日期'],
        ['Sample parameters / request', '样品参数 / 任务需求'], ['Sample result', '样品结果'],
        ['Report link', '报告链接'], ['Confirmed date', '确认日期'], ['Save request', '保存任务'],
        ['Pending', '待确认'], ['Success', '成功'], ['Failed', '失败'],
        ['Result: {status}', '结果：{status}'], ['Due: {date}', '截止日期：{date}'],
        ['Report: {report}', '报告：{report}'],
        ['Task control', '任务管理'], ['Request and scope', '需求与范围'],
        ['Request description', '需求描述'], ['Request date', '申请日期'],
        ['Request date (source)', '申请日期（源表原文）'], ['Due date (source)', '截止日期（源表原文）'],
        ['Decision maker', '客户决策人'], ['Quantity', '数量'], ['Competitor', '竞争对手'],
        ['Key points', '关键要点'], ['Concerns', '关注事项'],
        ['Progress and result', '进展与结果'], ['Current progress', '当前进展'],
        ['Result summary', '结果摘要'], ['Supplemental notes', '补充说明'],
        ['Latest follow-up', '最近跟进'], ['Follow-up content', '跟进内容'],
        ['No formal follow-up recorded', '尚无正式跟进记录'], ['Not provided', '未提供'],
        ['Pre-sales tasks', '售前 / 样品任务'], ['+ New task', '+ 新建任务'],
        ['No pre-sales task yet.', '暂无售前 / 样品任务。'], ['{count} tasks', '{count} 项任务'],
        ['{leadCount} leads · {taskCount} tasks', '{leadCount} 个商机 · {taskCount} 项任务'],
        ['Save result', '保存结果'], ['Update task', '更新任务'], ['Save task', '保存任务'],
        ['Please enter a request description.', '请输入任务需求描述。'],
        ['Only an active assigned task result can be updated.', '只能更新已分配且未归档任务的结果。'],
        ['Current assignee', '当前负责人'], ['Inactive', '已停用'],
        ['Unable to load pre-sales owners. The current assignment was preserved.', '无法加载售前负责人列表，当前指派已保留。'],
        ['Pre-sales task created', '售前 / 样品任务已创建'],
        ['Pre-sales task updated', '售前 / 样品任务已更新'],
        ['Pre-sales task archived', '售前 / 样品任务已归档'],
        ['Pre-sales task restored', '售前 / 样品任务已恢复'],
        ['Archive this pre-sales task?', '确定归档这项售前 / 样品任务吗？'],
        ['Error saving pre-sales task', '保存售前 / 样品任务失败'],
        ['This task contains damaged JSON data. Repair or re-import it before saving.', '此任务包含损坏的 JSON 数据。请先修复或重新导入，再执行保存。'],
        ['Error archiving pre-sales task', '归档售前 / 样品任务失败'],
        ['Error restoring pre-sales task', '恢复售前 / 样品任务失败'],
        ['The change was saved, but the screen could not refresh. Reopen this lead to load the latest data.', '变更已保存，但页面刷新失败。请重新打开该商机以加载最新数据。'],
        ['Unable to load', '加载失败'],
        ['Unable to load pre-sales tasks. Please retry.', '无法加载售前 / 样品任务，请重试。'],
        ['Select a lead card, then create the task in the Pre-sales / Sample tab.', '请先选择一张商机卡片，再到“售前 / 样品”页签创建任务。'],
        ['Imported fields requiring review', '导入字段待复核'], ['Unknown Company', '未知公司'],
        ['No records found', '未找到记录'], ['Try adjusting your filters or create a new inquiry.', '请调整筛选条件或新建询盘。'],
        ['{shown} of {total} active', '显示 {shown} / {total} 个进行中商机'],
        ['No records in this view', '当前视图没有记录'],
        ['No active leads match the current search, owner, technical or business-region filters.', '当前搜索、负责人、技术或业务区域组合下没有进行中的商机。'],
        ['All {count} matching active leads are missing a next follow-up date. Set one in lead details or use All Active.', '匹配的 {count} 个进行中商机均未设置下次跟进日期。请在商机详情中补充日期，或切换到“全部进行中”。'],
        ['No matching active lead is due in this planned-date period; {missing} have no next follow-up date.', '所选计划日期范围内没有到期商机；另有 {missing} 个商机未设置下次跟进日期。'],
        ['The custom activity start date must not be after the end date.', '自定义活动起始日期不能晚于截止日期。'],
        ['Choose at least one custom activity date.', '请至少选择一个自定义活动日期。'],
        ['Every matching active lead already has a formal follow-up.', '所有匹配的进行中商机都已有正式跟进记录。'],
        ['No active lead matches the selected planned-date and activity-time filters.', '没有进行中的商机同时符合所选计划日期和活动时间条件。'],
        ['Unable to load follow-ups', '无法加载跟进列表'],
        ['The follow-up list could not be loaded. Please retry.', '跟进列表加载失败，请重试。'],
        ['Error loading lead', '加载商机失败'],

        // Core inquiry fields and common workflow choices
        ['Inquiry ID', '询盘ID'], ['Inquiry Date', '询盘日期'], ['Source Channel', '来源渠道'],
        ['Original Email Content', '原始邮件内容'], ['Assigned Sales', '负责销售'],
        ['Customer Information', '客户信息'], ['Primary Contact', '询盘主联系人'],
        ['Contact Name', '联系人姓名'], ['Position', '职位'], ['Company Name', '公司名称'],
        ['Email', '邮箱'], ['Phone', '电话'], ['Detailed Address', '详细地址'], ['Postal Code', '邮编'],
        ['Customer Type', '客户类型'], ['Industry', '行业'], ['Language', '语言'], ['Website', '网站'],
        ['Company Description', '公司简介'], ['Company Size', '公司规模'],
        ['Business Information Links', '商业信息链接'], ['Requirement Information', '需求信息'],
        ['Product Category', '产品大类'], ['Product Series', '产品系列'], ['Power Range', '功率范围'],
        ['Wavelength Requirement', '波长需求'], ['Application Scenario', '应用场景'],
        ['Processing Material', '加工材料'], ['Quantity Requirement', '数量需求'],
        ['Special Requirements', '特殊要求'], ['Potential Needs', '潜在需求挖掘'],
        ['Inquiry Evaluation', '询盘评估'], ['Inquiry Quality', '询盘质量'], ['Urgency', '紧急程度'],
        ['Estimated Value (USD)', '预估价值(USD)'], ['Current Stage', '当前阶段'],
        ['Next Follow-up Date', '下次跟进日期'], ['Deal Information', '成交信息'],
        ['Quotation Number', '报价单号'], ['Quotation Date', '报价日期'], ['PO Number', 'PO号'],
        ['PO Date', 'PO日期'], ['Contract Amount', '合同金额'], ['Currency', '币种'],
        ['Product Details', '产品明细'], ['Order Fulfillment', '订单履行'], ['Fulfillment Status', '履约状态'],
        ['Select...', '请选择……'], ['Select contact...', '请选择联系人……'], ['Yes', '是'], ['No', '否'],
        ['Website inquiry', '网站询盘'], ['Exhibition', '展会'], ['Referral', '转介绍'], ['Other', '其他'],
        ['End User', '终端用户'], ['Integrator', '系统集成商'], ['Distributor', '经销商'],
        ['High', '高'], ['Medium', '中'], ['Low', '低'], ['Meeting', '会议'], ['Video Call', '视频会议'],
        ['Technical', '技术问题'], ['Quality', '质量问题'], ['Delivery', '交付问题'],
        ['Draft', '草稿'], ['Active', '生效'], ['Planned', '已计划'], ['Visited', '已拜访'],
        ['Follow-up Needed', '需要跟进'],
        ['pending', '待处理'], ['responded', '已回复'], ['completed', '已完成'], ['scheduled', '已计划']
    ];
    const translations = Object.fromEntries(pairs);
    const reverseTranslations = {};
    pairs.forEach(([english, chinese]) => {
        if (!Object.hasOwn(reverseTranslations, chinese)) reverseTranslations[chinese] = english;
    });
    const DISPLAY_PARAM_KEYS = new Set(['result', 'stage', 'status']);
    const originalText = new WeakMap();
    const originalAttributes = new WeakMap();
    let language = normalize(localStorage.getItem(STORAGE_KEY) || navigator.language);

    function normalize(value) { return String(value || '').toLowerCase().startsWith('zh') ? 'zh-CN' : 'en'; }
    function escapeRegExp(value) { return value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'); }
    function compileTemplate(template) {
        const keys = [];
        let pattern = '';
        let cursor = 0;
        for (const match of template.matchAll(/\{([a-zA-Z0-9_]+)\}/g)) {
            pattern += escapeRegExp(template.slice(cursor, match.index)) + '(.+?)';
            keys.push(match[1]);
            cursor = match.index + match[0].length;
        }
        pattern += escapeRegExp(template.slice(cursor));
        return { keys, regex: new RegExp(`^${pattern}$`) };
    }
    const templatePairs = pairs
        .filter(([english]) => english.includes('{'))
        .map(([english, chinese]) => ({
            source: english,
            english: compileTemplate(english),
            chinese: compileTemplate(chinese),
        }));

    function matchTemplate(value, compiled) {
        const match = compiled.regex.exec(value);
        if (!match) return null;
        return Object.fromEntries(compiled.keys.map((key, index) => [key, match[index + 1]]));
    }
    function resolveRecord(value) {
        if (Object.hasOwn(translations, value)) return { source: value, params: {} };
        if (Object.hasOwn(reverseTranslations, value)) return { source: reverseTranslations[value], params: {} };
        for (const entry of templatePairs) {
            const params = matchTemplate(value, entry.english) || matchTemplate(value, entry.chinese);
            if (params) return { source: entry.source, params };
        }
        return { source: value, params: {} };
    }
    function replaceParams(template, params, targetLanguage) {
        return template.replace(/\{([a-zA-Z0-9_]+)\}/g, (placeholder, key) => {
            if (!Object.hasOwn(params, key)) return placeholder;
            const value = String(params[key] ?? '');
            if (!DISPLAY_PARAM_KEYS.has(key)) return value;
            const record = resolveRecord(value);
            return targetLanguage === 'zh-CN' ? (translations[record.source] || record.source) : record.source;
        });
    }
    function calendarDate(year, month, day, targetLanguage) {
        const numericYear = Number(year);
        const numericMonth = Number(month);
        const numericDay = Number(day);
        const date = new Date(numericYear, numericMonth - 1, numericDay);
        if (Number.isNaN(date.getTime())
            || date.getFullYear() !== numericYear
            || date.getMonth() !== numericMonth - 1
            || date.getDate() !== numericDay) return null;
        const locale = targetLanguage === 'zh-CN' ? 'zh-CN' : 'en-US';
        return new Intl.DateTimeFormat(locale, {
            year: 'numeric', month: 'short', day: 'numeric'
        }).format(date);
    }
    function localizeDates(value, targetLanguage) {
        const months = {
            Jan: 1, Feb: 2, Mar: 3, Apr: 4, May: 5, Jun: 6,
            Jul: 7, Aug: 8, Sep: 9, Oct: 10, Nov: 11, Dec: 12,
        };
        let result = String(value);
        result = result.replace(
            /\b(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+(\d{1,2}),\s+(\d{4})\b/g,
            (original, month, day, year) => calendarDate(year, months[month], day, targetLanguage) || original
        );
        return result.replace(
            /(\d{4})年(\d{1,2})月(\d{1,2})日/g,
            (original, year, month, day) => calendarDate(year, month, day, targetLanguage) || original
        );
    }
    function renderRecord(record, targetLanguage = language) {
        const template = targetLanguage === 'zh-CN'
            ? (translations[record.source] || record.source)
            : record.source;
        return localizeDates(replaceParams(template, record.params, targetLanguage), targetLanguage);
    }
    function t(text, params = {}) {
        const record = resolveRecord(String(text ?? ''));
        record.params = { ...record.params, ...params };
        return renderRecord(record);
    }
    function matchesKnownRendering(record, current) {
        return current === renderRecord(record, 'en') || current === renderRecord(record, 'zh-CN');
    }
    function translateTextNode(node) {
        if (!node.nodeValue || !node.nodeValue.trim()) return;
        const current = node.nodeValue.trim();
        let record = originalText.get(node);
        if (!record || !matchesKnownRendering(record, current)) {
            record = resolveRecord(current);
            originalText.set(node, record);
        }
        const translated = renderRecord(record);
        if (translated !== current) node.nodeValue = node.nodeValue.replace(current, translated);
    }
    function translateAttribute(element, attribute) {
        const current = element.getAttribute(attribute);
        if (!current) return;
        let saved = originalAttributes.get(element) || {};
        let record = saved[attribute];
        if (!record || !matchesKnownRendering(record, current)) record = resolveRecord(current);
        saved[attribute] = record;
        originalAttributes.set(element, saved);
        const translated = renderRecord(record);
        if (translated !== current) element.setAttribute(attribute, translated);
    }
    function apply(root = document.body) {
        if (!root) return;
        if (root.nodeType === Node.TEXT_NODE) return translateTextNode(root);
        if (![Node.ELEMENT_NODE, Node.DOCUMENT_NODE].includes(root.nodeType)) return;
        const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
        while (walker.nextNode()) translateTextNode(walker.currentNode);
        const elements = root.nodeType === Node.ELEMENT_NODE ? [root, ...root.querySelectorAll('*')] : [...root.querySelectorAll('*')];
        elements.forEach(element => ['placeholder', 'title', 'aria-label'].forEach(attribute => translateAttribute(element, attribute)));
        document.documentElement.lang = language;
        syncToggle();
    }
    function syncToggle() {
        document.querySelectorAll('[data-language-toggle]').forEach(button => {
            button.textContent = language === 'zh-CN' ? 'EN' : '中';
            button.title = language === 'zh-CN' ? '切换到 English' : 'Switch to 中文';
            button.setAttribute('aria-label', button.title);
        });
    }
    function setLanguage(next) {
        language = normalize(next);
        localStorage.setItem(STORAGE_KEY, language);
        apply(document.body);
        window.dispatchEvent(new CustomEvent('language:changed', { detail: { language } }));
    }
    function toggle() { setLanguage(language === 'zh-CN' ? 'en' : 'zh-CN'); }
    function init() {
        apply(document.body);
        const observer = new MutationObserver(mutations => mutations.forEach(mutation => {
            if (mutation.type === 'characterData') translateTextNode(mutation.target);
            if (mutation.type === 'attributes') translateAttribute(mutation.target, mutation.attributeName);
            mutation.addedNodes.forEach(apply);
        }));
        observer.observe(document.body, {
            childList: true,
            subtree: true,
            characterData: true,
            attributes: true,
            attributeFilter: ['placeholder', 'title', 'aria-label'],
        });
    }
    window.I18n = {
        init, t, apply, toggle, setLanguage,
        language: () => language,
        locale: () => language === 'zh-CN' ? 'zh-CN' : 'en-US',
    };
    document.addEventListener('DOMContentLoaded', init, { once: true });
})();
