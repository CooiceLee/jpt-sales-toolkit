"""A refresh that failed must not be reported as a refresh that worked.

The navigation numbers are what a reader checks after importing something or
saving a task. When the request behind them failed, the Tech branch caught the
error, drew em dashes and still answered "refreshed" - so the two callers that
ask, in order to tell the reader whether the numbers are current, were told
yes. The import screens then said the import was complete with nothing about
the counts, and the reader took the stale numbers for the new ones.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent

HARNESS = r"""
const fs = require('fs');
const vm = require('vm');
const assert = require('assert');

function build({ isTech, failing }) {
  const texts = {};
  const context = {
    console: { error() {} },
    I18n: { t: text => text },
    RoleCapabilities: { isTech: () => isTech },
    ApiClient: {
      getTaskWorkloadSummary: async () => {
        if (failing) throw new Error('offline');
        return { pre_sales_active_lead_count: 3, after_sales_active_lead_count: 5 };
      },
      getDashboard: async () => {
        if (failing) throw new Error('offline');
        return { stage_counts: {}, service_open_count: 0 };
      },
    },
    setText: (id, value) => { texts[id] = String(value); },
    document: { querySelector: () => null },
    loadModuleData: async () => {},
    State: { user: { role: isTech ? 'tech' : 'leader' } },
  };
  context.window = context;
  vm.createContext(context);
  vm.runInContext(
    fs.readFileSync('frontend/js/modules/refresh-counts.js', 'utf8'), context);
  return { context, texts };
}

(async () => {
  // Tech, request fails: dashes on screen, and the answer says so.
  const techFailing = build({ isTech: true, failing: true });
  const techResult = await techFailing.context.refreshNavigationCounts();
  assert.strictEqual(techResult, false,
    'a failed Tech count refresh reported itself as successful');
  assert.strictEqual(techFailing.texts['nav-sampling-total'], '—',
    'the unknown count was left showing its old number');
  assert.strictEqual(techFailing.texts['nav-aftersales-total'], '—');

  // Tech, request succeeds: the numbers arrive and the answer says so.
  const techOk = build({ isTech: true, failing: false });
  assert.strictEqual(await techOk.context.refreshNavigationCounts(), true);
  assert.strictEqual(techOk.texts['nav-sampling-total'], '3');
  assert.strictEqual(techOk.texts['nav-aftersales-total'], '5');

  // The commercial branch already answered honestly; it must keep doing so.
  const leaderFailing = build({ isTech: false, failing: true });
  assert.strictEqual(await leaderFailing.context.refreshNavigationCounts(), false);

  // And the whole-page refresh inherits that answer.
  const bothFailing = build({ isTech: true, failing: true });
  assert.strictEqual(await bothFailing.context.refreshAllCounts(), false,
    'refreshAllCounts reported success while its counts had failed');
})().catch(error => { console.error(error); process.exitCode = 1; });
"""

# The three places that act on the answer. Each one tells the reader that the
# work landed but the numbers did not, instead of catching an error that this
# function never throws.
CALLERS = (
    ("frontend/js/modules/spreadsheet-import-actions.js", "import-result"),
    ("frontend/js/modules/data-transfer.js", "insertAdjacentHTML"),
    ("frontend/js/modules/tech-task-packages.js", "insertAdjacentHTML"),
)


def check_callers_read_the_answer() -> None:
    for relative, marker in CALLERS:
        source = (ROOT / relative).read_text(encoding="utf-8")
        assert "refreshAllCounts().catch" not in source, (
            f"{relative} catches an error that refreshAllCounts never throws, "
            "so its warning can never appear"
        )
        assert "if (!await refreshAllCounts())" in source, (
            f"{relative} ignores whether the counts were actually refreshed"
        )
        assert "navigation counts could not be refreshed" in source, (
            f"{relative} says nothing when the counts are stale"
        )
        assert marker in source, f"{relative}: {marker} is gone"


def main() -> None:
    check_callers_read_the_answer()
    result = subprocess.run(
        ["node", "-e", HARNESS], cwd=ROOT, text=True, capture_output=True, check=False,
    )
    assert result.returncode == 0, result.stderr or result.stdout
    print("PASS: a failed count refresh is reported as a failure")


if __name__ == "__main__":
    main()
