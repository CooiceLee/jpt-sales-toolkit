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
        ['Pipeline', '销售管线'], ['Total Inquiries', '询盘总数'], ['All time', '全部时间'], ['Last 7 Days', '最近 7 天'],
        ['New inquiries', '新增询盘'], ['Following', '跟进中'], ['Active follow-ups', '进行中的跟进'],
        ['Won Deals', '已赢单'], ['Closed won', '已成交'], ['Won Value', '成交金额'], ['Total deal amount', '成交总金额'],
        ['Review Map', '复盘地图'], ['Loading map data...', '正在加载地图数据……'], ['Stage', '阶段'], ['All stages', '全部阶段'],
        ['New', '新建'], ['Assigned', '已分配'], ['Quoted', '已报价'], ['Won', '赢单'], ['Lost', '丢单'],
        ['Outcome', '结果'], ['All outcomes', '全部结果'], ['Open', '进行中'], ['Region', '区域'], ['All regions', '全部区域'],
        ['Europe', '欧洲'], ['Southeast Asia', '东南亚'], ['Americas', '美洲'], ['Russia/India/ME', '俄罗斯/印度/中东'],
        ['Coordinate quality', '坐标质量'], ['All coordinates', '全部坐标'], ['Exact only', '仅精确坐标'],
        ['Needs geocode', '需要地理编码'], ['Batch Geocode', '批量地理编码'],
        ['Re-geocode customers without precise coordinates', '为缺少精确坐标的客户重新编码'],
        ['Step 01 · Inquiry Parser', '步骤 01 · 询盘解析'], ['Raw Email', '原始邮件'], ['Paste', '粘贴'], ['Clear', '清空'],
        ['Paste the inquiry email content here...', '在此粘贴询盘邮件内容……'], ['chars', '字符'],
        ['⚡ Parse with AI', '⚡ 使用 AI 解析'], ['Extracted Fields', '提取字段'], ['Discard', '放弃'],
        ['✓ Save as new inquiry', '✓ 保存为新询盘'], ['Step 02 · Inquiry Handler', '步骤 02 · 询盘处理'],
        ['Search company, ID, country...', '搜索公司、编号、国家……'], ['+ New Inquiry', '+ 新建询盘'],
        ['Step 03 · Follow-up Tracker', '步骤 03 · 跟进管理'], ['All Active', '全部进行中'], ['Overdue', '已逾期'],
        ['Due today', '今日到期'], ['This week', '本周'], ['+ Log follow-up', '+ 记录跟进'],
        ['Step 04 · Sample Manager', '步骤 04 · 样品管理'], ['All sampling', '全部样品'], ['In progress', '进行中'],
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
        ['Full Backup Before Import', '导入前完整备份'],
        ['Includes the database, attachments and runtime authorization configuration. Keep the displayed backup path for rollback.', '完整备份包含数据库、附件和运行时授权配置。请保存页面显示的备份路径，以便回滚。'],
        ['Create Full Backup', '创建完整备份'], ['Creating full backup...', '正在创建完整备份……'],
        ['Full backup created', '完整备份已创建'], ['Backup failed', '备份失败'], ['Unknown error', '未知错误'],
        ['Import & Merge', '导入并合并'],
        ['JSON keeps the existing member exchange flow. XLSX uses Leader-controlled preflight, correction and commit.', 'JSON 用于现有成员数据交换；XLSX 由 Leader 执行受控预检、修正和提交。'],
        ['JPT-XLSX-1.0 templates and source workbooks are distributed separately from the application installer.', 'JPT-XLSX-1.0 模板和源工作簿与应用安装程序分开分发。'],
        ['Import only merges data records. Attachment files must be transferred separately. For complete backup/restore, ask the administrator to use the server backup/restore procedure.', '导入只合并数据记录；附件文件必须单独传递。完整备份与恢复须由管理员使用服务端备份/恢复流程。'],
        ['Preflight Check', '预检'], ['Data Governance', '数据治理'], ['Normalize Countries / Regions', '规范化国家/区域'],
        ['Load Coordinate Audit', '加载坐标审计'], ['Customer IDs, one per line', '客户 ID，每行一个'],
        ['Lead IDs, one per line', '商机 ID，每行一个'], ['Owner ID', '负责人 ID'], ['Product category', '产品类别'],
        ['Application', '应用'], ['Run Batch Repair', '执行批量修复'], ['Customer Merge', '客户合并'],
        ['Select a duplicate source customer and merge it into the target customer that should remain active.', '选择重复的源客户，将其合并到需要保留的目标客户。'],
        ['Source duplicate', '重复源客户'], ['Search source customer', '搜索源客户'], ['Search', '搜索'],
        ['Target customer', '目标客户'], ['Search target customer', '搜索目标客户'],
        ['Merge Source Into Target', '将源客户合并到目标客户'], ['Inquiry Details', '询盘详情'], ['Save Changes', '保存修改'],
        ['Please select a file first', '请先选择文件'], ['Import failed', '导入失败'],
        ['Controlled XLSX import is available to Leader accounts only.', '受控 XLSX 导入仅限 Leader 账号使用。'],
        ['Running controlled preflight...', '正在执行受控预检……'], ['Running JSON preflight...', '正在执行 JSON 预检……'],
        ['Run preflight and resolve every blocking issue before import.', '请先执行预检并处理全部阻断问题，然后再导入。'],
        ['Only a Leader can preflight or import XLSX files.', '只有 Leader 可以预检或导入 XLSX 文件。'],
        ['Spreadsheet Import Complete', 'Excel 导入完成'], ['Created', '新增'], ['Updated', '更新'],
        ['Archived', '归档'], ['Skipped', '跳过'], ['Warnings', '警告'], ['Batch', '批次'],
        ['Spreadsheet Preflight', 'Excel 预检'], ['Source rows', '源数据行'], ['Entities', '实体'], ['Errors', '错误'],
        ['Member account mapping', '成员账号映射'], ['Customer matching', '客户匹配'],
        ['Issues and exclusions', '问题与排除项'], ['No issues found', '未发现问题'],
        ['Apply corrections & recheck', '应用修正并重新预检'], ['Ready to import', '可以导入'],
        ['Resolve or exclude all blockers before import', '请处理或排除全部阻断项后再导入'],
        ['Exclude record', '排除此记录'], ['Create new customer', '创建新客户'], ['Select account', '选择账号'],
        ['new customer', '新客户'], ['unresolved', '未解决'], ['Only .xlsx workbooks are supported', '仅支持 .xlsx 工作簿'],
        ['Workbook exceeds the 25 MB limit', '工作簿超过 25 MB 上限'], ['Workbook is empty', '工作簿为空'],
        ['Spreadsheet import failed', 'Excel 导入失败'], ['Preflight failed', '预检失败']
    ];
    const translations = Object.fromEntries(pairs);
    const reverseTranslations = Object.fromEntries(pairs.map(([english, chinese]) => [chinese, english]));
    const originalText = new WeakMap();
    const originalAttributes = new WeakMap();
    let language = normalize(localStorage.getItem(STORAGE_KEY) || navigator.language);

    function normalize(value) { return String(value || '').toLowerCase().startsWith('zh') ? 'zh-CN' : 'en'; }
    function t(text, params = {}) {
        const source = String(text ?? '');
        let result = language === 'zh-CN' ? (translations[source] || source) : source;
        Object.entries(params).forEach(([key, value]) => { result = result.replaceAll(`{${key}}`, String(value)); });
        return result;
    }
    function translateTextNode(node) {
        if (!node.nodeValue || !node.nodeValue.trim()) return;
        const current = node.nodeValue.trim();
        let source = originalText.get(node);
        if (!source || (current !== source && current !== translations[source])) {
            source = reverseTranslations[current] || current;
            originalText.set(node, source);
        }
        const translated = language === 'zh-CN' ? (translations[source] || source) : source;
        if (translated !== current) node.nodeValue = node.nodeValue.replace(current, translated);
    }
    function translateAttribute(element, attribute) {
        const current = element.getAttribute(attribute);
        if (!current) return;
        let saved = originalAttributes.get(element) || {};
        let source = saved[attribute];
        if (!source || (current !== source && current !== translations[source])) source = reverseTranslations[current] || current;
        saved[attribute] = source;
        originalAttributes.set(element, saved);
        element.setAttribute(attribute, language === 'zh-CN' ? (translations[source] || source) : source);
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
        const button = document.getElementById('language-toggle');
        if (!button) return;
        button.textContent = language === 'zh-CN' ? 'EN' : '中';
        button.title = language === 'zh-CN' ? '切换到 English' : 'Switch to 中文';
        button.setAttribute('aria-label', button.title);
    }
    function setLanguage(next) {
        language = next === 'zh-CN' ? 'zh-CN' : 'en';
        localStorage.setItem(STORAGE_KEY, language);
        apply(document.body);
        window.dispatchEvent(new CustomEvent('language:changed', { detail: { language } }));
    }
    function toggle() { setLanguage(language === 'zh-CN' ? 'en' : 'zh-CN'); }
    function init() {
        apply(document.body);
        const observer = new MutationObserver(mutations => mutations.forEach(mutation => {
            if (mutation.type === 'characterData') translateTextNode(mutation.target);
            mutation.addedNodes.forEach(apply);
        }));
        observer.observe(document.body, { childList: true, subtree: true, characterData: true });
    }
    window.I18n = { init, t, apply, toggle, setLanguage, language: () => language };
    document.addEventListener('DOMContentLoaded', init, { once: true });
})();
