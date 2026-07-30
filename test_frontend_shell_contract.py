"""Focused contracts for authentication and the reusable frontend shell."""

from __future__ import annotations

import subprocess
from pathlib import Path


ROOT = Path(__file__).parent
FRONTEND = ROOT / "frontend"
MODULES = FRONTEND / "js" / "modules"


def main() -> None:
    app = (FRONTEND / "js" / "app.js").read_text(encoding="utf-8")
    api = (FRONTEND / "js" / "api-client.js").read_text(encoding="utf-8")
    activation = (MODULES / "authorization-activation.js").read_text(encoding="utf-8")
    parser = (MODULES / "intake-parser.js").read_text(encoding="utf-8")
    filters = (MODULES / "stage-filters.js").read_text(encoding="utf-8")
    menu = (MODULES / "user-menu.js").read_text(encoding="utf-8")
    css = (FRONTEND / "css" / "style.css").read_text(encoding="utf-8")

    assert "dataset.navigationBound" in app
    assert "dataset.parserBound" in parser
    assert "dataset.stageFilterBound" in filters and "dataset.filterTabBound" in filters
    assert "dataset.userMenuBound" in menu
    assert "aria-expanded" in menu and "event.key === 'Escape'" in menu

    assert "clearDashboardData()" in app
    assert "Dashboard data unavailable. Please retry." in app
    assert "dashboard-retry" in app and "retry.addEventListener('click', loadDashboard)" in app
    assert "Map errors have their own visible state" in app

    status_failure = activation.index("Authorization status unavailable; login remains blocked.")
    assert activation.index("ApiClient.clearAuth();", status_failure) > status_failure
    assert activation.index("return false;", status_failure) > status_failure
    assert "using legacy login flow" not in activation

    assert "ANONYMOUS_ENDPOINTS" in api
    assert "token && !isAnonymousEndpoint(endpoint)" in api
    assert ".kpi-grid-5" in css and "@media (max-width: 520px)" in css
    mobile = css[css.index("@media (max-width: 768px)"):]
    assert ".rail {" in mobile and "overflow-y: auto;" in mobile
    assert ".rail { display: none; }" not in mobile

    harness = r"""
const fs = require('fs');
const vm = require('vm');
const assert = require('assert');

const storage = new Map();
let mode = 'login-error';
let logoutEvents = 0;
function response(status, detail = null, data = null) {
  return {
    status,
    ok: status >= 200 && status < 300,
    async text() { return JSON.stringify({ detail }); },
    async json() { return data; },
  };
}
const context = {
  console,
  localStorage: {
    getItem: key => storage.get(key) || null,
    setItem: (key, value) => storage.set(key, value),
    removeItem: key => storage.delete(key),
  },
  CustomEvent: class CustomEvent { constructor(type) { this.type = type; } },
  async fetch() {
    if (mode === 'login-error') return response(401, 'Invalid username or password');
    if (mode === 'login-success') {
      return response(200, null, {
        token: 'valid-token',
        user: { id: 'sales-1', role: 'sales' },
      });
    }
    return response(401, 'Unauthorized');
  },
};
context.window = context;
context.dispatchEvent = event => {
  if (event.type === 'auth:logout') logoutEvents += 1;
};
vm.createContext(context);
vm.runInContext(
  fs.readFileSync('frontend/js/api-client.js', 'utf8') + '\nthis.__api = ApiClient;',
  context
);

(async () => {
  await assert.rejects(
    context.__api.login('sales', 'wrong'),
    error => error.status === 401 && error.message === 'Invalid username or password'
  );
  assert.strictEqual(logoutEvents, 0);

  mode = 'login-success';
  await context.__api.login('sales', 'correct');
  assert.strictEqual(context.__api.getToken(), 'valid-token');

  mode = 'protected-error';
  await assert.rejects(
    context.__api.getMe(),
    error => error.status === 401 && error.message === 'Session expired. Please login again.'
  );
  assert.strictEqual(logoutEvents, 1);
  assert.strictEqual(context.__api.getToken(), null);
})().catch(error => {
  console.error(error);
  process.exitCode = 1;
});
"""
    result = subprocess.run(
        ["node", "-e", harness],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr or result.stdout
    print("PASS: shell idempotency, auth meaning, activation gate and responsive contracts")


if __name__ == "__main__":
    main()
