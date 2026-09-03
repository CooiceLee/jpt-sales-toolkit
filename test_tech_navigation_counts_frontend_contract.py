"""Frontend contracts for role-aware Tech navigation workload counts."""

from __future__ import annotations

import subprocess
from pathlib import Path


ROOT = Path(__file__).parent
FRONTEND = ROOT / "frontend"
MODULES = FRONTEND / "js" / "modules"


def static_contracts() -> None:
    app = (FRONTEND / "js" / "app.js").read_text(encoding="utf-8")
    client = (FRONTEND / "js" / "api-client.js").read_text(encoding="utf-8")
    refresh = (MODULES / "refresh-counts.js").read_text(encoding="utf-8")
    packages = (MODULES / "tech-task-packages.js").read_text(encoding="utf-8")
    sampling = (MODULES / "sampling-actions.js").read_text(encoding="utf-8")
    aftersales = (MODULES / "aftersales-actions.js").read_text(encoding="utf-8")

    assert "return request('/tasks/workload-summary')" in client
    assert "        getTaskWorkloadSummary," in client
    assert "refreshTechNavigationCounts().catch" in app
    assert "ApiClient.getTaskWorkloadSummary()" in refresh
    assert "pre_sales_active_lead_count" in refresh
    assert "after_sales_active_lead_count" in refresh
    assert "await refreshTechNavigationCounts()" in refresh
    assert "await refreshAllCounts()" in packages
    assert "await refreshAllCounts()" in sampling
    assert "await refreshAllCounts()" in aftersales
    # A Tech user has no dashboard to read, so the branch that serves them must
    # not call for one. Read to the branch's own closing brace rather than to
    # the next return, so how it returns is free to change.
    assert "ApiClient.getDashboard()" not in _tech_branch(refresh), (
        "the Tech branch reads the dashboard, which Tech users cannot see"
    )


def _tech_branch(source: str) -> str:
    """The body of `if (RoleCapabilities.isTech()) { ... }`, braces matched."""
    marker = "if (RoleCapabilities.isTech())"
    start = source.index("{", source.index(marker))
    depth, index = 0, start
    while index < len(source):
        if source[index] == "{":
            depth += 1
        elif source[index] == "}":
            depth -= 1
            if depth == 0:
                return source[start:index + 1]
        index += 1
    raise AssertionError("the Tech branch is not closed")


def browser_contracts() -> None:
    harness = r"""
const fs = require('fs');
const vm = require('vm');
const assert = require('assert');
const source = fs.readFileSync('frontend/js/modules/refresh-counts.js', 'utf8');

async function techFlow() {
  const text = {};
  let workloadCalls = 0;
  let dashboardCalls = 0;
  const loaded = [];
  const context = {
    console,
    RoleCapabilities: { isTech: () => true },
    ApiClient: {
      getTaskWorkloadSummary: async () => {
        workloadCalls += 1;
        return { pre_sales_active_lead_count: 55, after_sales_active_lead_count: 7 };
      },
      getDashboard: async () => { dashboardCalls += 1; throw new Error('forbidden'); }
    },
    setText: (id, value) => { text[id] = value; },
    applyNavigationCounts: () => { throw new Error('Tech must not use dashboard counts'); },
    loadModuleData: async module => { loaded.push(module); },
    document: { querySelector: () => ({ id: 'module-sampling' }) }
  };
  context.window = context;
  vm.createContext(context);
  vm.runInContext(source, context);

  await context.refreshTechNavigationCounts();
  assert.deepStrictEqual(text, {
    'nav-sampling-total': 55,
    'nav-aftersales-total': 7
  });
  await context.refreshAllCounts();
  assert.strictEqual(workloadCalls, 2);
  assert.strictEqual(dashboardCalls, 0);
  assert.deepStrictEqual(loaded, ['sampling']);
}

async function techFailure() {
  const text = {};
  const loaded = [];
  const context = {
    console,
    RoleCapabilities: { isTech: () => true },
    ApiClient: { getTaskWorkloadSummary: async () => { throw new Error('offline'); } },
    setText: (id, value) => { text[id] = value; },
    document: { querySelector: () => null },
    loadModuleData: async module => { loaded.push(module); }
  };
  context.window = context;
  vm.createContext(context);
  vm.runInContext(source, context);
  await assert.rejects(context.refreshTechNavigationCounts(), /offline/);
  assert.strictEqual(text['nav-sampling-total'], '—');
  assert.strictEqual(text['nav-aftersales-total'], '—');
  context.document.querySelector = () => ({ id: 'module-aftersales' });
  await context.refreshAllCounts();
  assert.deepStrictEqual(loaded, ['aftersales']);
}

async function commercialFlow() {
  let workloadCalls = 0;
  let dashboardCalls = 0;
  let applied = null;
  const loaded = [];
  const stats = { total_leads: 9 };
  const context = {
    console,
    RoleCapabilities: { isTech: () => false },
    ApiClient: {
      getTaskWorkloadSummary: async () => { workloadCalls += 1; return {}; },
      getDashboard: async () => { dashboardCalls += 1; return stats; }
    },
    setText() {},
    applyNavigationCounts: value => { applied = value; },
    loadModuleData: async module => { loaded.push(module); },
    document: { querySelector: () => ({ id: 'module-followup' }) }
  };
  context.window = context;
  vm.createContext(context);
  vm.runInContext(source, context);
  await context.refreshAllCounts();
  assert.strictEqual(workloadCalls, 0);
  assert.strictEqual(dashboardCalls, 1);
  assert.strictEqual(applied, stats);
  assert.deepStrictEqual(loaded, ['followup']);
}

(async () => {
  await techFlow();
  await techFailure();
  await commercialFlow();
  console.log('PASS: Tech navigation counts use the narrow workload endpoint');
})().catch(error => { console.error(error); process.exitCode = 1; });
"""
    result = subprocess.run(
        ["node", "-e", harness], cwd=ROOT, text=True,
        capture_output=True, check=False,
    )
    assert result.returncode == 0, result.stderr or result.stdout


def aftersales_scope_contracts() -> None:
    harness = r"""
const fs = require('fs');
const vm = require('vm');
const assert = require('assert');
const source = fs.readFileSync('frontend/js/modules/service-worklists.js', 'utf8');

async function renderForRole(isTech) {
  let rendered = null;
  const leads = isTech ? [
    { id: 'own-after', service_status: 'Open', sales_stage: 'Following' },
    { id: 'pre-only', service_status: 'Open', sales_stage: 'Following' },
  ] : [
    { id: 'commercial-global', service_status: 'Resolved', sales_stage: 'Following' },
  ];
  const tasks = isTech ? [
    { id: 'task-own', lead_id: 'own-after', status: 'Resolved' },
  ] : [];
  const context = {
    console,
    window: null,
    I18n: { t: value => value },
    RoleCapabilities: { isTech: () => isTech },
    ApiClient: {
      listLeads: async () => leads,
      listAfterSalesTasks: async () => tasks,
    },
    getSharedLeadFilters: () => ({}),
    leadToCardItem: (lead, extra) => ({ ...lead, ...extra }),
    State: { currentFilters: { aftersales: 'all' } },
    WorklistSort: { aftersales: items => items },
    setText() {},
    renderCards: (_id, items) => { rendered = items; },
    setPanelError() {},
  };
  context.window = context;
  vm.createContext(context);
  vm.runInContext(source, context);
  await context.loadAftersales();
  return rendered;
}

(async () => {
  const techItems = await renderForRole(true);
  assert.strictEqual(techItems.length, 1);
  assert.strictEqual(techItems[0].id, 'own-after');
  assert.strictEqual(techItems[0].service_status, 'Resolved');
  assert.strictEqual(techItems[0].after_sales_count, 1);

  const commercialItems = await renderForRole(false);
  assert.strictEqual(commercialItems.length, 1);
  assert.strictEqual(commercialItems[0].service_status, 'Resolved');
  console.log('PASS: Tech after-sales cards are scoped to assigned tasks');
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
    aftersales_scope_contracts()
    print("PASS: Tech navigation count frontend contracts")


if __name__ == "__main__":
    main()
