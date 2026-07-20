"""Static and runtime contracts for the bilingual frontend foundation."""

from __future__ import annotations

import subprocess
from pathlib import Path


ROOT = Path(__file__).parent


def main() -> None:
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
    ):
        assert f"'{label}'" in i18n, f"missing translation contract: {label}"

    assert "['Open', '待处理']" in i18n
    assert "['In Progress', '进行中']" in i18n
    assert "['Open', '进行中']" not in i18n
    assert "['placeholder', 'title', 'aria-label']" in i18n
    assert "window.I18n?.locale?.()" in utils

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
