"""Unsaved, saving, saved and refused have to look different.

A panel that looks the same whichever of those is true teaches people to press
Save twice and to distrust what is on the screen. The four states are shown in
the footer beside the button that causes them, and they come from the save
itself rather than from a guess.

Also covers the shared workspace head - title, how many things are in this
view, and the one action that starts work here - and a colour token the styles
named but nobody had defined.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent
INDEX = (ROOT / "frontend" / "index.html").read_text(encoding="utf-8")
CSS = (ROOT / "frontend" / "css" / "style.css").read_text(encoding="utf-8")
SAVE = (ROOT / "frontend" / "js" / "modules" / "inquiry-save.js").read_text(
    encoding="utf-8"
)


def check_the_footer_can_speak() -> None:
    assert 'id="panel-save-state"' in INDEX, "the panel footer cannot say anything"
    footer = INDEX[INDEX.index('class="panel-footer"'):]
    footer = footer[:footer.index("</div>")]
    assert 'id="panel-save-state"' in footer, (
        "the state is not beside the button that causes it"
    )
    for state in ("is-dirty", "is-busy", "is-done", "is-failed"):
        assert f".panel-save-state.{state}" in CSS, f"no style for {state}"
    # Four states, four different colours: one of them being the default
    # colour would make it invisible.
    tones = re.findall(r"\.panel-save-state\.is-\w+ \{ color: var\((--[\w-]+)\)", CSS)
    assert len(set(tones)) == len(tones) >= 4, f"states share a colour: {tones}"


def check_the_save_reports_each_state() -> None:
    for state in ("'saving'", "'saved'", "'failed'"):
        assert f"PanelSaveState?.show?.({state})" in SAVE, (
            f"the save never reports {state}"
        )
    # A stale response must not report anything: the reader has moved on.
    stale = SAVE.index("Stale inquiry save error")
    failed = SAVE.index("PanelSaveState?.show?.('failed')")
    assert stale < failed, (
        "a response the reader moved past still reports a failure at them"
    )


def check_every_colour_the_styles_use_is_defined() -> None:
    """A rule that names an undefined variable does nothing at all.

    `.inquiry-card:hover` asked for `--wine-200`, which was never declared, so
    the hover border never changed.
    """
    declared = set(re.findall(r"^\s*(--[\w-]+):", CSS, re.M))
    used = set(re.findall(r"var\((--[\w-]+)(?:\s*,[^)]*)?\)", CSS))
    fallback = set(re.findall(r"var\((--[\w-]+)\s*,", CSS))
    missing = sorted((used - declared) - fallback)
    assert not missing, f"styles use colours nobody declared: {missing}"


# Every work queue: the module, the count it shows, and the action that starts
# work there. Each of these used to arrange them differently, so the reader had
# to find the count and the button again on every page.
WORK_QUEUES = (
    ("handler", "inquiry-count", "showNewInquiryModal()"),
    ("followup", "followup-count", "logFollowUp()"),
    ("sampling", "sampling-count", "newSampleRequest()"),
    ("deal", "deal-count", "createQuote()"),
    ("fulfillment", "fulfillment-count", "logStatus()"),
    ("aftersales", "aftersales-count", "logIssue()"),
)


def check_the_workspace_head_is_one_shape() -> None:
    assert ".workspace-head {" in CSS
    for part in (".workspace-count", ".workspace-actions"):
        assert part in CSS, f"the shared head has no {part}"
    for module, count_id, action in WORK_QUEUES:
        block = INDEX[INDEX.index(f'id="module-{module}"'):]
        head = block[:block.index("</div>", block.index('class="workspace-head"'))
                     + 600] if 'class="workspace-head"' in block[:2000] else ""
        assert 'class="workspace-head"' in block[:2000], (
            f"the {module} module does not use the shared head"
        )
        head = block[block.index('class="workspace-head"'):]
        head = head[:head.index('class="filters-bar"')] if 'class="filters-bar"' in head[:3000] else head[:1500]
        assert f'class="workspace-count" id="{count_id}"' in head, (
            f"{module}: the count is not the shared count element"
        )
        assert action in head, f"{module}: the primary action is not in the head"
    # And the old arrangement is gone, not merely unused.
    assert "filter-summary" not in INDEX, (
        "a module still keeps its count inside the filter bar"
    )
    assert "filter-action" not in INDEX, (
        "a module still keeps its primary action inside the filter bar"
    )


HARNESS = r"""
const fs = require('fs');
const vm = require('vm');
const assert = require('assert');

const label = { className: '', textContent: '', attributes: {},
                setAttribute(name, value) { this.attributes[name] = value; } };
const listeners = {};
const content = {
  dataset: {},
  addEventListener(name, handler) { listeners[name] = handler; },
};
const context = {
  console,
  I18n: { t: text => text },
  document: {
    getElementById: id => (
      id === 'panel-save-state' ? label
      : id === 'panel-content' ? content
      : null),
    addEventListener() {},
  },
};
context.window = context;
vm.createContext(context);
vm.runInContext(fs.readFileSync('frontend/js/modules/panel-save-state.js', 'utf8'), context);
const { PanelSaveState } = context;

// Each state says something different, and only one of them is silent.
const seen = new Map();
for (const state of ['clean', 'dirty', 'saving', 'saved', 'failed']) {
  PanelSaveState.show(state);
  seen.set(state, { text: label.textContent, tone: label.className });
}
assert.strictEqual(seen.get('clean').text, '', 'an untouched form still says something');
for (const state of ['dirty', 'saving', 'saved', 'failed']) {
  assert.ok(seen.get(state).text.length > 0, `${state} says nothing`);
}
const texts = ['dirty', 'saving', 'saved', 'failed'].map(state => seen.get(state).text);
assert.strictEqual(new Set(texts).size, 4, `two states read the same: ${texts}`);
const tones = ['dirty', 'saving', 'saved', 'failed'].map(state => seen.get(state).tone);
assert.strictEqual(new Set(tones).size, 4, `two states look the same: ${tones}`);

// A refusal has to reach a screen reader when it happens; the rest are quiet.
PanelSaveState.show('failed');
assert.strictEqual(label.attributes.role, 'alert');
PanelSaveState.show('saving');
assert.strictEqual(label.attributes.role, 'status');

// Typing anywhere in the panel reports unsaved work.
PanelSaveState.show('clean');
PanelSaveState.watch();
listeners.input({ target: { matches: () => true } });
assert.ok(label.textContent.length > 0, 'typing did not report unsaved changes');
assert.ok(label.className.includes('is-dirty'), label.className);

// And something that is not a field does not.
PanelSaveState.show('clean');
listeners.change({ target: { matches: () => false } });
assert.strictEqual(label.textContent, '', 'a click on plain text reported an edit');
"""


def main() -> None:
    check_the_footer_can_speak()
    check_the_save_reports_each_state()
    check_every_colour_the_styles_use_is_defined()
    check_the_workspace_head_is_one_shape()
    result = subprocess.run(
        ["node", "-e", HARNESS], cwd=ROOT, text=True, capture_output=True, check=False,
    )
    assert result.returncode == 0, result.stderr or result.stdout
    print("PASS: the panel says which of the four states it is in")


if __name__ == "__main__":
    main()
