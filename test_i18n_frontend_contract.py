"""Static and runtime contracts for the bilingual frontend foundation."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path


ROOT = Path(__file__).parent
RUNTIME_ACTIONS = (
    "coordinate-actions.js",
    "coordinate-save.js",
    "coordinate-panel.js",
    "coordinate-review-actions.js",
    "followups-actions.js",
    "aftersales-actions.js",
    "files-actions.js",
    "batch-geocode.js",
)
ACTION_TRANSLATORS = {
    "coordinate-actions.js": "coordinateText",
    "coordinate-save.js": "coordinateText",
    "coordinate-panel.js": "coordinateText",
    "coordinate-review-actions.js": "coordinateText",
    "followups-actions.js": "followupActionText",
    "aftersales-actions.js": "afterSalesActionText",
    "files-actions.js": "fileActionText",
    "batch-geocode.js": "batchGeocodeText",
}


def _source(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


# The screens where an untranslated server message is most visible: both show
# whatever the API returned, so a message added on the server without a
# translation reaches a Chinese user in English.
SERVER_MESSAGE_SOURCES = (
    "backend/routers/authorization.py",
    "backend/routers/admin.py",
    "backend/services/offline_authorization_service.py",
    "backend/services/leader_authorization_recovery_service.py",
    "backend/authorization/issuer.py",
    "backend/authorization/device.py",
    "backend/services/trip_team_adapter.py",
)


def check_server_messages_are_translated() -> None:
    """A message the server raises must have a translation before it is shown.

    The authorization screens and the Excel preflight display the API's own
    text, so this is not a cosmetic gap: the user reads English in an otherwise
    Chinese interface at exactly the moment something went wrong.
    """
    i18n = _source("frontend/js/i18n.js")
    missing = []
    for relative in SERVER_MESSAGE_SOURCES:
        path = ROOT / relative
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8")
        for message in re.findall(
            r'(?:AuthorizationError|ValueError|detail=)\(?\s*"([A-Z][^"]{12,140})"',
            text,
        ):
            if f"['{message}'" not in i18n and f'["{message}"' not in i18n:
                missing.append(f"{relative}: {message}")
    assert not missing, (
        "these server messages reach the user untranslated:\n  "
        + "\n  ".join(sorted(missing))
    )


def check_authorization_screens_translate_what_they_show() -> None:
    """Every authorization message box has to pass its text through I18n."""
    for name in ("authorization-activation.js", "authorization-center.js"):
        source = _source(f"frontend/js/modules/{name}")
        setters = re.findall(
            r"function set\w*Message\([^)]*\)\s*\{(.*?)\n    \}", source, re.S
        )
        assert setters, f"{name} has no message setter to check"
        for body in setters:
            assert "I18n.t(" in body, (
                f"{name} writes a message without translating it: {body.strip()[:120]}"
            )


def main() -> None:
    check_server_messages_are_translated()
    check_authorization_screens_translate_what_they_show()
    i18n = (ROOT / "frontend" / "js" / "i18n.js").read_text(encoding="utf-8")
    utils = (ROOT / "frontend" / "js" / "shared" / "utils.js").read_text(encoding="utf-8")

    for label in (
        "Basic", "Customer", "Requirement", "Evaluation", "Sample", "Follow-ups",
        "Data Quality", "Files", "Sample requests", "Pre-sales owner", "Due date",
        "Sample parameters / request", "Sample result", "Report link", "Confirmed date",
        "No sample parameters", "Not Requested", "Open", "In Progress",
        "Request description", "Current progress", "Latest follow-up", "Follow-up content",
        "{count} samples", "{count} to review", "{leadCount} leads · {taskCount} tasks",
        "Search customer, contact, country", "All sales", "All tech",
        "Last activity", "Never formally followed up", "Inactive 90+ days",
        "{count} days inactive", "{shown} of {total} active",
        "Search and open accessible leads...", "{count} matching leads",
        "{count} imported fields require review", "Discard unsaved changes?",
        "Address candidates", "Showing {from}–{to} of {total}",
        "Address search sends these location fields to one or more configured external geocoding services.",
        "Selected via {provider}: {address}",
        "External service",
        "Found {count} matches via {provider}. The first is selected; choose another below if needed.",
        "Coordinates saved.", "Error saving coordinates: {error}",
        "Wait for address search to finish or cancel it before saving.",
        "Coordinate data version is unavailable. Close this window and reopen it before saving.",
        "Customer coordinate data is no longer available. Please refresh the list.",
        "You can view this customer, but only the owner or a collaborator can edit its coordinates.",
        "Follow-up updated.", "Error saving follow-up: {error}",
        "Archive this follow-up?", "Issue logged.",
        "Archive this after-sales issue?", "File uploaded.",
        "Archive this file?", "Found {count} customers needing geocoding.",
        "Customer address fields will be sent to one or more configured external geocoding services. Use this only for data approved for external processing.",
        "Processing {current}/{total}...", "Batch geocode complete.",
        "Follow-up Tracker", "Deal Closer", "Location", "Coordinates", "Actions", "Fix",
        "Next:", "+ Add Follow-up", "Close Lead", "Reason tag", "Close lead",
        "Cannot access clipboard. Please paste manually.", "Please select a new owner",
        "Error changing owner: {error}", "Trip plan created", "Error creating trip plan: {error}",
        "Lead created: {id}", "Member saved",
        "Deactivate {name}? Existing offline data will remain on their device.",
        "Authorization downloaded: {filename}", "Changes saved",
        "Conflict: {error}. Please refresh and try again.", "Error saving contact: {error}",
        "Customer is not plotted on the review map. Opened coordinate correction.",
        "Visit saved", "Error exporting visit day: {error}",
        "Visit purpose", "Result notes", "Unscheduled stops", "Export day report",
        "No stops on this date", "No scheduled date", "Customer departments / teams",
        "Customer personnel", "Channel partner companions (if any)",
        "Channel partner companions", "JPT internal participants", "Lead",
        "Customer needs", "Budget", "Sample needed", "Quote needed",
        "Meeting notes", "Upload files",
        "This customer needs coordinate review before it can be shown on the map.",
        "{action} conflict: this plan was updated elsewhere. The latest data will be loaded; please retry.",
        "Could not load more candidates", "Enter at least one Customer ID or Lead ID",
        "Exit JPT Sales Toolkit on this computer?", "Unable to exit JPT: {error}",
        "Please enter username and password", "Invalid username or password",
        "Loading dashboard data...", "Dashboard data unavailable. Please retry.",
        "Create a full backup before import", "Authorization Check Failed",
        "Unable to verify authorization status. Restart JPT and try again.",
        "Loading candidates...", "Unable to load saved plans", "No stops yet",
        "No saved plans", "No dates", "Untitled", "Trip Plan {date}",
        "{start} to {end}", "Archive trip plan “{title}”?", "Trip plan archived",
        "{count} files uploaded. Reselect only the files not uploaded: {files}. Error: {error}",
        "JPT has stopped", "You can close this window safely.",
        "Locked", "{count} won", "{count} open", "Open Lead", "Fix Location",
        "No fields configured for this tab.", "Enter at least a contact name or email address.",
        "Email format: example@company.com",
        "GLOBAL", "North America / Canada / Australia", "Russia / Turkey / Middle East",
        "Add to Plan", "Error loading coordinate data",
        "{count} customers · country aggregate", "High", "Medium", "Low",
        "Score", "Value", "Reasons", "Map", "Showing {shown} of {total}", "Load more",
        "Multiple open leads", "Quoted opportunities", "Active follow-up", "Pipeline value",
        "Service or renewal context", "Coordinate needs review",
    ):
        assert f"'{label}'" in i18n, f"missing translation contract: {label}"

    modules = ROOT / "frontend" / "js" / "modules"
    # Native dialogs and toast notifications must never receive a bare literal.
    # Scanning every module prevents untranslated feedback from reappearing in a
    # less frequently used workflow.
    bare_runtime_call = re.compile(r"\b(?:window\.)?(?:alert|confirm|notify)\(\s*(['\"])")
    for source_path in sorted(modules.glob("*.js")):
        source = source_path.read_text(encoding="utf-8")
        assert bare_runtime_call.search(source) is None, (
            f"{source_path.name} opens native/runtime UI with a bare literal"
        )

    for filename in RUNTIME_ACTIONS:
        source = (modules / filename).read_text(encoding="utf-8")
        for unlocalized_call in ("alert('", 'alert("', "confirm('", 'confirm("', "notify('", 'notify("'):
            assert unlocalized_call not in source, (
                f"{filename} opens native/runtime UI without I18n.t: {unlocalized_call}"
            )
        translator = ACTION_TRANSLATORS[filename]
        keys = re.findall(rf"\b{translator}\(\s*(['\"])(.*?)\1", source, flags=re.DOTALL)
        for _, key in keys:
            assert f"['{key}'" in i18n or f'["{key}"' in i18n, (
                f"{filename} uses untranslated runtime key: {key}"
            )

    assert "['Open', '待处理']" in i18n
    assert "['In Progress', '进行中']" in i18n
    assert "['Open', '进行中']" not in i18n
    assert "['placeholder', 'title', 'aria-label']" in i18n
    assert "node.parentElement?.closest?.('[data-language-toggle]')" in i18n
    assert "window.I18n?.locale?.()" in utils

    coordinate_review = (modules / "coordinate-review-view.js").read_text(encoding="utf-8")
    review_map = (modules / "review-map-view.js").read_text(encoding="utf-8")
    inquiry_form = (modules / "inquiry-form.js").read_text(encoding="utf-8")
    trip_plans = (modules / "trip-plans.js").read_text(encoding="utf-8")
    trip_form = (modules / "trip-form.js").read_text(encoding="utf-8")
    assert "coordinateText('No data available')" in coordinate_review
    assert "coordinateText(p.coordinate_quality" in coordinate_review
    assert "coordinateText(isVerified ? 'Verified' : 'Auto Exact')" in coordinate_review
    assert "t('Locked')" in review_map and "t('{count} won'" in review_map
    assert "t('Open Lead')" in review_map and "t('Fix Location')" in review_map
    assert "I18n.t('No fields configured for this tab.')" in inquiry_form
    assert "姓名或邮箱至少填写一项" not in inquiry_form
    assert "邮箱格式: example@company.com" not in inquiry_form
    assert "I18n.t('No saved plans')" in trip_plans
    assert "formatTripPlanDateRange(plan)" in trip_plans
    assert "plan.title || I18n.t('Untitled')" in trip_plans
    assert "I18n.t('Trip Plan {date}'" in trip_form
    assert "toLocaleDateString('en-US')" not in trip_form

    harness = r"""
const fs = require('fs');
const vm = require('vm');
const assert = require('assert');

const storage = new Map([['jpt_ui_language', 'en']]);
const context = {
    console, Intl, Date,
    localStorage: {
        getItem: key => storage.get(key) || null,
        setItem: (key, value) => storage.set(key, value),
    },
    navigator: { language: 'en-US' },
    Node: { TEXT_NODE: 3, ELEMENT_NODE: 1, DOCUMENT_NODE: 9 },
    NodeFilter: { SHOW_TEXT: 4 },
    CustomEvent: class CustomEvent {
        constructor(type, options) { this.type = type; this.detail = options?.detail; }
    },
    MutationObserver: class MutationObserver {
        observe() {}
    },
};
context.document = {
    body: null,
    documentElement: { lang: 'en' },
    addEventListener() {},
    querySelectorAll() { return []; },
    createTreeWalker() { return { nextNode: () => false, currentNode: null }; },
};
context.dispatchEvent = () => true;
context.window = context;
vm.createContext(context);
vm.runInContext(fs.readFileSync('frontend/js/i18n.js', 'utf8'), context);
vm.runInContext(fs.readFileSync('frontend/js/shared/utils.js', 'utf8'), context);

context.I18n.setLanguage('zh-CN');
assert.strictEqual(context.I18n.t('Open'), '待处理');
assert.strictEqual(context.I18n.t('In Progress'), '进行中');
assert.strictEqual(context.I18n.t('Search customer, contact, country'), '搜索客户、联系人、国家');
assert.strictEqual(context.I18n.t('All sales'), '全部销售');
assert.strictEqual(context.I18n.t('All tech'), '全部技术');
assert.strictEqual(
    context.I18n.t('{shown} of {total} active', { shown: 17, total: 244 }),
    '显示 17 / 244 个进行中商机'
);
assert.strictEqual(context.I18n.t('{count} days inactive', { count: 90 }), '已 90 天未跟进');
assert.strictEqual(context.I18n.t('{count} matching leads', { count: 3 }), '找到 3 个匹配商机');
assert.strictEqual(context.I18n.t('{count} imported fields require review', { count: 2 }), '2 个导入字段需要复核');
assert.strictEqual(context.I18n.t('Discard unsaved changes?'), '要放弃尚未保存的修改吗？');
assert.strictEqual(context.I18n.t('Address candidates'), '地址候选项');
assert.strictEqual(
    context.I18n.t('Wait for address search to finish or cancel it before saving.'),
    '请等待地址搜索完成，或先取消搜索后再保存。'
);
assert.strictEqual(
    context.I18n.t('Coordinate data version is unavailable. Close this window and reopen it before saving.'),
    '坐标数据版本不可用。请关闭此窗口并重新打开后再保存。'
);
assert.strictEqual(context.I18n.t('Coordinates saved.'), '坐标已保存。');
assert.strictEqual(
    context.I18n.t('You can view this customer, but only the owner or a collaborator can edit its coordinates.'),
    '您可以查看该客户，但只有负责人或协作者可以编辑其坐标。'
);
assert.strictEqual(
    context.I18n.t('Error saving coordinates: {error}', { error: context.I18n.t('Unknown error') }),
    '保存坐标失败：未知错误'
);
assert.strictEqual(context.I18n.t('Archive this follow-up?'), '要归档这条跟进记录吗？');
assert.strictEqual(context.I18n.t('Issue logged.'), '售后问题已记录。');
assert.strictEqual(context.I18n.t('File uploaded.'), '文件已上传。');
assert.strictEqual(context.I18n.t('Changes saved'), '修改已保存。');
assert.strictEqual(
    context.I18n.t('Error changing owner: {error}', { error: 'network' }),
    '更换负责人失败：network'
);
assert.strictEqual(context.I18n.t('Locked'), '已锁定');
assert.strictEqual(context.I18n.t('{count} won', { count: 2 }), '2 个已赢单');
assert.strictEqual(context.I18n.t('Open Lead'), '打开商机');
assert.strictEqual(context.I18n.t('GLOBAL'), '全球');
assert.strictEqual(context.I18n.t('Add to Plan'), '加入计划');
assert.strictEqual(context.I18n.t('Visit purpose'), '拜访目的');
assert.strictEqual(context.I18n.t('Result notes'), '结果备注');
assert.strictEqual(context.I18n.t('Unscheduled stops'), '未排程拜访');
assert.strictEqual(context.I18n.t('Export day report'), '导出当日拜访报告');
assert.strictEqual(context.I18n.t('Customer departments / teams'), '客户部门 / 团队');
assert.strictEqual(context.I18n.t('Customer personnel'), '客户人员');
assert.strictEqual(context.I18n.t('Channel partner companions (if any)'), '渠道代理公司陪同人员（如有）');
assert.strictEqual(context.I18n.t('Channel partner companions'), '渠道代理公司陪同人员');
assert.strictEqual(context.I18n.t('JPT internal participants'), 'JPT 内部参会人员');
assert.strictEqual(context.I18n.t('Lead'), '商机');
assert.strictEqual(context.I18n.t('Customer needs'), '客户需求');
assert.strictEqual(context.I18n.t('Sample needed'), '需要样品');
assert.strictEqual(context.I18n.t('Quote needed'), '需要报价');
assert.strictEqual(context.I18n.t('Meeting notes'), '会议记录');
assert.strictEqual(context.I18n.t('Upload files'), '上传文件');
assert.strictEqual(context.I18n.t('Error loading coordinate data'), '坐标数据加载失败');
assert.strictEqual(context.I18n.t('{count} customers · country aggregate', { count: 3 }), '3 位客户 · 国家聚合');
assert.strictEqual(context.I18n.t('High'), '高');
assert.strictEqual(context.I18n.t('Invalid username or password'), '用户名或密码错误。');
assert.strictEqual(
    context.I18n.t('Dashboard data unavailable. Please retry.'),
    '仪表盘数据不可用，请重试。'
);
assert.strictEqual(
    context.I18n.t('Archive trip plan “{title}”?', { title: 'Europe 2026' }),
    '要归档出差计划“Europe 2026”吗？'
);
assert.strictEqual(context.I18n.t('No saved plans'), '尚无已保存的出差计划');
assert.strictEqual(context.I18n.t('No dates'), '尚未设置日期');
assert.strictEqual(context.I18n.t('Untitled'), '未命名');
assert.strictEqual(
    context.I18n.t('Trip Plan {date}', { date: context.formatDate('2026-09-15') }),
    '出差计划 2026年9月15日'
);
assert.strictEqual(
    context.I18n.t('{start} to {end}', {
        start: context.formatDate('2026-09-15'), end: context.formatDate('2026-09-30')
    }),
    '2026年9月15日 至 2026年9月30日'
);
assert.strictEqual(
    context.I18n.t(
        '{count} files uploaded. Reselect only the files not uploaded: {files}. Error: {error}',
        { count: 2, files: 'a.pdf', error: 'timeout' }
    ),
    '已上传 2 个文件。请仅重新选择未上传的文件：a.pdf。错误：timeout'
);
assert.strictEqual(
    context.I18n.t('Deactivate {name}? Existing offline data will remain on their device.', { name: 'Amy' }),
    '要停用 Amy 吗？其设备上的现有离线数据会保留。'
);
assert.strictEqual(
    context.I18n.t('Found {count} customers needing geocoding.', { count: 12 }),
    '发现 12 个客户需要地理编码。'
);
assert.strictEqual(
    context.I18n.t('Processing {current}/{total}...', { current: 2, total: 12 }),
    '正在处理 2/12……'
);
assert.strictEqual(
    context.I18n.t('Showing {from}–{to} of {total}', { from: 1, to: 25, total: 177 }),
    '显示第 1–25 条，共 177 条'
);
assert.notStrictEqual(context.I18n.t('Open'), context.I18n.t('In Progress'));
assert.strictEqual(context.I18n.t('{count} samples', { count: 244 }), '244 个售前 / 样品商机');
assert.strictEqual(context.I18n.t('244 samples'), '244 个售前 / 样品商机');
assert.strictEqual(
    context.I18n.t('{leadCount} leads · {taskCount} tasks', { leadCount: 83, taskCount: 89 }),
    '83 个商机 · 89 项任务'
);
assert.strictEqual(context.I18n.t('484 leads'), '484 个商机');
assert.strictEqual(context.I18n.t('Result: Pending'), '结果：待确认');
assert.strictEqual(context.I18n.t('Sent: Jul 17, 2026'), '发送时间：2026年7月17日');

const countNode = { nodeType: 3, nodeValue: '244 samples' };
context.I18n.apply(countNode);
assert.strictEqual(countNode.nodeValue, '244 个售前 / 样品商机');
context.I18n.setLanguage('en');
context.I18n.apply(countNode);
assert.strictEqual(countNode.nodeValue, '244 samples');

const dateNode = { nodeType: 3, nodeValue: 'JPT-2607 · Jul 17, 2026' };
context.I18n.setLanguage('zh-CN');
context.I18n.apply(dateNode);
assert.strictEqual(dateNode.nodeValue, 'JPT-2607 · 2026年7月17日');
context.I18n.setLanguage('en');
context.I18n.apply(dateNode);
assert.strictEqual(dateNode.nodeValue, 'JPT-2607 · Jul 17, 2026');

const attributes = { title: 'In Progress', value: 'In Progress' };
const option = {
    nodeType: 1,
    querySelectorAll: () => [],
    getAttribute: name => attributes[name] ?? null,
    setAttribute: (name, value) => { attributes[name] = value; },
};
context.I18n.setLanguage('zh-CN');
context.I18n.apply(option);
assert.strictEqual(attributes.title, '进行中');
assert.strictEqual(attributes.value, 'In Progress');
context.I18n.setLanguage('en');
context.I18n.apply(option);
assert.strictEqual(attributes.title, 'In Progress');
assert.strictEqual(attributes.value, 'In Progress');

context.I18n.setLanguage('zh-CN');
assert.strictEqual(context.formatDate('2026-07-17T12:00:00'), '2026年7月17日');
assert.strictEqual(context.formatDate('2026-07-17'), '2026年7月17日');
context.I18n.setLanguage('en');
assert.strictEqual(context.formatDate('2026-07-17T12:00:00'), 'Jul 17, 2026');
assert.strictEqual(context.formatDate('2026-07-17'), 'Jul 17, 2026');
assert.strictEqual(context.formatDate('not-a-date'), 'not-a-date');
"""
    result = subprocess.run(
        ["node", "-e", harness],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr or result.stdout
    print("PASS: bilingual labels, dynamic counts, enum display and locale date contracts")


if __name__ == "__main__":
    main()
