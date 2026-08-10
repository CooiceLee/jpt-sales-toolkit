"""Frontend contracts for the isolated Leader/Tech task package workflow."""

from __future__ import annotations

import subprocess
from pathlib import Path


ROOT = Path(__file__).parent
FRONTEND = ROOT / "frontend"
MODULES = FRONTEND / "js" / "modules"


def static_contracts() -> None:
    index = (FRONTEND / "index.html").read_text(encoding="utf-8")
    client = (FRONTEND / "js" / "api-client.js").read_text(encoding="utf-8")
    roles = (MODULES / "role-capabilities.js").read_text(encoding="utf-8")
    view = (MODULES / "tech-task-package-view.js").read_text(encoding="utf-8")
    actions = (MODULES / "tech-task-packages.js").read_text(encoding="utf-8")
    i18n = (FRONTEND / "js" / "i18n.js").read_text(encoding="utf-8")

    endpoints = (
        "/data/tech-tasks/assignments/export",
        "/data/tech-tasks/assignments/preflight",
        "/data/tech-tasks/assignments/import",
        "/data/tech-tasks/results/export",
        "/data/tech-tasks/results/preflight",
        "/data/tech-tasks/results/import",
    )
    assert all(f"'{path}'" in client for path in endpoints)
    for method in (
        "exportTechTaskAssignments", "preflightTechTaskAssignments",
        "importTechTaskAssignments", "exportTechTaskResults",
        "preflightTechTaskResults", "importTechTaskResults",
    ):
        assert f"        {method}," in client, f"API method is not public: {method}"
    download_helper = client[client.index("async function downloadTechTaskPackage"):client.index("async function sendTechTaskPackage")]
    upload_helper = client[client.index("async function sendTechTaskPackage"):client.index("async function exportTechTaskAssignments")]
    assert "method: 'POST'" in download_helper
    assert "{ method: 'POST', body: formData }" in upload_helper

    assert "[...TECH_WORKFLOW_MODULES, 'export']" in roles
    assert 'data-transfer-target="tech"' in index
    assert "data-tech-task-exchange" in index and "data-sales-exchange" in index
    assert index.index("tech-task-package-view.js") < index.index("tech-task-packages.js")
    assert "escapeHtml(issueText(item))" in view
    assert "escapeHtml(user.id)" in view and "escapeHtml(user.display_name)" in view
    assert "onTechTaskPackageFileChanged" in actions
    assert "['errors', 'skipped', 'conflicts']" in actions

    bilingual = {
        "Tech Task Packages": "技术任务包",
        "Independent task exchange": "独立技术任务交换",
        "Preflight assignments": "预检分配包",
        "Import assignments": "导入任务",
        "Preflight results": "预检结果包",
        "Import results": "导入结果",
        "Task package downloaded": "技术任务包已下载",
    }
    for english, chinese in bilingual.items():
        assert f"['{english}', '{chinese}']" in i18n, english

    for module in (view, actions):
        assert len(module.splitlines()) <= 160


def browser_contracts() -> None:
    harness = r"""
const fs = require('fs');
const vm = require('vm');
const assert = require('assert');
const source = name => fs.readFileSync(`frontend/js/modules/${name}`, 'utf8');
const escaped = value => String(value ?? '').replace(/&/g, '&amp;')
  .replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;')
  .replace(/'/g, '&#39;');

function classList() {
  return { values: new Set(), toggle(name, on) { on ? this.values.add(name) : this.values.delete(name); },
    add(name) { this.values.add(name); } };
}

async function verifyRole(role) {
  const nav = ['dashboard', 'sampling', 'aftersales', 'export'].map(module => ({ dataset: { module }, classList: classList() }));
  const leaderOnly = [{ classList: classList() }];
  const salesExchange = [{ classList: classList() }];
  const techExchange = [{ classList: classList() }];
  const taskRoles = ['leader', 'tech'].map(itemRole => ({ dataset: { techTaskRole: itemRole }, hidden: true }));
  const recipient = { innerHTML: '' };
  const context = { console, State: { user: { role } }, escapeHtml: escaped,
    I18n: { t: value => value }, ApiClient: { listUsers: async () => [
      { id: '<tech-id>', display_name: '<img onerror=alert(1)>', is_active: true }
    ] },
    document: {
      getElementById(id) { return id === 'tech-task-recipient' ? recipient : null; },
      querySelectorAll(selector) {
        if (selector.includes('[data-module]')) return nav;
        if (selector === '[data-leader-spreadsheet]') return leaderOnly;
        if (selector === '[data-sales-exchange]') return salesExchange;
        if (selector === '[data-tech-task-exchange]') return techExchange;
        if (selector === '[data-tech-task-role]') return taskRoles;
        return [];
      }
    }
  };
  context.window = context;
  context.DataTransferWorkspace = { ensureAccessible() {} };
  vm.createContext(context);
  vm.runInContext(source('role-capabilities.js'), context);
  vm.runInContext(source('tech-task-package-view.js'), context);
  context.RoleCapabilities.applyNavigation();
  context.TechTaskPackageView.ensureRole();
  await new Promise(resolve => setImmediate(resolve));
  const hidden = item => item.classList.values.has('hidden');
  assert.strictEqual(context.RoleCapabilities.canAccessModule('export'), true);
  assert.strictEqual(hidden(salesExchange[0]), role === 'tech');
  assert.strictEqual(hidden(techExchange[0]), role === 'sales');
  assert.strictEqual(hidden(leaderOnly[0]), role !== 'leader');
  assert.strictEqual(taskRoles[0].hidden, role !== 'leader');
  assert.strictEqual(taskRoles[1].hidden, role !== 'tech');
  if (role === 'tech') assert.strictEqual(hidden(nav.find(item => item.dataset.module === 'export')), false);
  if (role === 'leader') {
    assert.ok(recipient.innerHTML.includes('&lt;tech-id&gt;'));
    assert.ok(recipient.innerHTML.includes('&lt;img'));
    assert.ok(!recipient.innerHTML.includes('<img'));
  }
}

async function verifyGateAndEscaping() {
  const fileA = { name: 'a.jpttask', size: 10, lastModified: 1 };
  const fileB = { name: 'b.jpttask', size: 11, lastModified: 2 };
  const elements = {
    'tech-assignment-file': { files: [fileA], value: 'a.jpttask' },
    'tech-assignment-import': { disabled: false, title: '', setAttribute() {} },
    'tech-assignment-result': { innerHTML: '' },
    'tech-result-file': { files: [], value: '' },
    'tech-result-import': { disabled: false, title: '', setAttribute() {} },
    'tech-result-result': { innerHTML: '' },
  };
  let report = { can_import: true, summary: { total: 1, errors: 0, skipped: 0, conflicts: 0 } };
  const context = { console, State: { user: { role: 'tech' } }, escapeHtml: escaped,
    I18n: { t: value => value }, alert() {}, downloadBlob() {}, refreshAllCounts: async () => {},
    ApiClient: {
      listUsers: async () => [], preflightTechTaskAssignments: async () => report,
      importTechTaskAssignments: async () => report, preflightTechTaskResults: async () => report,
      importTechTaskResults: async () => report, exportTechTaskAssignments: async () => ({}),
      exportTechTaskResults: async () => ({ blob: {}, filename: 'x.jptresult' })
    }, document: { getElementById: id => elements[id] || null, querySelectorAll: () => [] } };
  context.window = context;
  vm.createContext(context);
  vm.runInContext(source('tech-task-package-view.js'), context);
  vm.runInContext(source('tech-task-packages.js'), context);

  for (const blocker of ['errors', 'skipped', 'conflicts']) {
    report = { can_import: false, summary: { errors: 0, skipped: 0, conflicts: 0, [blocker]: 1 } };
    await context.preflightTechTaskPackage('assignment');
    assert.strictEqual(elements['tech-assignment-import'].disabled, true, `${blocker} must block import`);
  }
  report = { summary: { total: 1, errors: 0, skipped: 0, conflicts: 0 } };
  await context.preflightTechTaskPackage('assignment');
  assert.strictEqual(elements['tech-assignment-import'].disabled, true, 'missing can_import must block import');
  report = { can_import: true, summary: { total: 1, errors: 0, skipped: 0, conflicts: 0 } };
  await context.preflightTechTaskPackage('assignment');
  assert.strictEqual(elements['tech-assignment-import'].disabled, false);
  elements['tech-assignment-file'].files = [fileB];
  context.onTechTaskPackageFileChanged('assignment');
  assert.strictEqual(elements['tech-assignment-import'].disabled, true);

  context.TechTaskPackageView.renderReport('tech-assignment-result', {
    summary: { total: 1 }, issues: [{ message: '<img src=x onerror=alert(1)>' }]
  }, '<script>alert(1)</script>');
  const html = elements['tech-assignment-result'].innerHTML;
  assert.ok(html.includes('&lt;script&gt;') && html.includes('&lt;img'));
  assert.ok(!html.includes('<script>') && !html.includes('<img'));
}

(async () => {
  for (const role of ['leader', 'tech', 'sales']) await verifyRole(role);
  await verifyGateAndEscaping();
  console.log('PASS: Tech package role visibility, guarded preflight and escaping');
})().catch(error => { console.error(error); process.exitCode = 1; });
"""
    result = subprocess.run(
        ["node", "-e", harness], cwd=ROOT, text=True,
        capture_output=True, check=False,
    )
    assert result.returncode == 0, result.stderr or result.stdout


def main() -> None:
    static_contracts()
    browser_contracts()
    print("PASS: Tech task package frontend contracts")


if __name__ == "__main__":
    main()
