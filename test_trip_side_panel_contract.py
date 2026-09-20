"""The candidate panel: how tall it may be, and when it is redrawn.

Two things the reader met on the same screen.

Its height was a fixed sum - the window minus the application header - which is
only true once it has pinned. Before that it starts further down, below the
plan's header and the zone tabs, and keeps the full height: its bottom then sat
below the window, so scrolling the panel reached its end with rows still off
screen. The inner scrollbar said "that is everything" when it was not, and the
only way out was to scroll the whole page.

And the list says which customers are already on the plan - read once, when the
candidates loaded. Every stop added since left it offering to add a customer
that was already there, until something unrelated happened to redraw it.
"""

from __future__ import annotations

import json
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
MODULES = ROOT / "frontend" / "js" / "modules"
CSS = (ROOT / "frontend" / "css" / "style.css").read_text(encoding="utf-8")


HARNESS = r"""
const fs = require('fs');
const vm = require('vm');
const assert = require('assert/strict');

// A pinned panel that starts wherever the page has been scrolled to.
let sideTop = 123;
let visible = true;
const applied = {};
const side = {
  style: {
    setProperty: (name, value) => { applied[name] = value; },
    removeProperty: name => { delete applied[name]; },
  },
  get offsetParent() { return visible ? {} : null; },
  getBoundingClientRect: () => (visible
    ? { top: sideTop, bottom: sideTop + 400, height: 400 }
    : { top: 0, bottom: 0, height: 0 }),
};
const main = {
  dataset: {},
  addEventListener() {},
  getBoundingClientRect: () => ({ top: 72, bottom: 1000 }),
};
const ctx = {
  console,
  innerHeight: 1000,
  requestAnimationFrame: callback => callback(),
  addEventListener() {},
  getComputedStyle: () => ({ position: 'sticky' }),
  document: {
    addEventListener() {},
    querySelector: selector => (selector.includes('trip-side') ? side : main),
  },
};
ctx.window = ctx;
vm.createContext(ctx);
vm.runInContext(fs.readFileSync('frontend/js/modules/trip-side-height.js', 'utf8'),
                ctx, { filename: 'trip-side-height.js' });

// Not pinned yet: only what is left below where it starts.
ctx.TripSideHeight.sync();
assert.equal(applied['--trip-side-height'], '877px',
  `a panel starting at 123 was given ${applied['--trip-side-height']}`);

// Pinned: the whole visible strip.
sideTop = 72;
ctx.TripSideHeight.sync();
assert.equal(applied['--trip-side-height'], '928px');

// Its zone is hidden, so every edge is zero: measuring then would write "as
// tall as the window" and keep it until something else happened to ask again.
visible = false;
ctx.TripSideHeight.sync();
assert.equal(applied['--trip-side-height'], '928px',
  'the panel was measured while its zone was hidden');

// Never so short that it stops being a list.
visible = true;
sideTop = 980;
ctx.TripSideHeight.sync();
assert.ok(parseInt(applied['--trip-side-height'], 10) >= 280,
  applied['--trip-side-height']);
console.log(JSON.stringify({ ok: true }));
"""


def check_the_panel_is_measured_where_it_is() -> None:
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False,
                                     encoding="utf-8") as handle:
        handle.write(HARNESS)
        script = handle.name
    result = subprocess.run(["node", script], capture_output=True, text=True, cwd=ROOT)
    Path(script).unlink(missing_ok=True)
    assert result.returncode == 0, result.stderr or result.stdout
    assert json.loads(result.stdout.strip().splitlines()[-1])["ok"]


def check_the_style_uses_the_measurement() -> None:
    block = CSS[CSS.index(".trip-side {"):CSS.index("}", CSS.index(".trip-side {"))]
    assert "var(--trip-side-height" in block, (
        "the panel is back to a fixed height that is only right once it has "
        f"pinned: {block}"
    )
    assert "calc(100vh" in block, "there is no fallback if the measurement never runs"


def check_the_list_follows_the_plan() -> None:
    zones = (MODULES / "trip-zones.js").read_text(encoding="utf-8")
    assert "renderTripCandidates?.()" in zones, (
        "nothing redraws the candidate list when the plan changes, so it goes "
        "on offering to add customers that are already on it"
    )
    assert "TripSideHeight?.sync?.()" in zones, (
        "the panel is never re-measured when a zone opens, and its zone is "
        "hidden when the page first lays out"
    )
    listing = (MODULES / "trip-candidates-list.js").read_text(encoding="utf-8")
    assert "side.scrollTop = readingAt" in listing, (
        "redrawing the list throws away where the reader had scrolled to - and "
        "it is now redrawn every time the plan changes"
    )
    assert "inCurrentPlan" in listing


def main() -> None:
    check_the_panel_is_measured_where_it_is()
    check_the_style_uses_the_measurement()
    check_the_list_follows_the_plan()
    print("PASS: the candidate panel ends where the window ends, and its rows "
          "say whether the customer is already on the plan")


if __name__ == "__main__":
    main()
