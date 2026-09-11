#!/usr/bin/env python3
"""Stable-release UX and accessibility contracts."""

import subprocess
from pathlib import Path


ROOT = Path(__file__).parent


FOCUS_HARNESS = r"""
const fs = require('fs');
const vm = require('vm');
const assert = require('assert');

// A dialog that has just stopped being display:none cannot take focus yet:
// the first focus() call is dropped, exactly as the browser drops it.
let boxReady = false;
const focused = [];
const make = (id, tag = 'BUTTON') => ({
    id, tagName: tag, hidden: false, disabled: false,
    get offsetParent() { return boxReady ? modal : null; },
    focus() { if (!boxReady) return; focused.push(id); context.document.activeElement = this; },
    getAttribute: () => null, setAttribute() {}, click() {},
    classList: { contains: () => false, add() {}, remove() {}, toggle() {} },
});
const cancel = make('cancel');
const field = make('new-inquiry-company', 'INPUT');
const modal = {
    id: 'new-inquiry-modal', tagName: 'DIV',
    children: [cancel, field],
    classList: {
        _on: new Set(),
        contains(name) { return this._on.has(name); },
        add(name) { this._on.add(name); },
        remove(name) { this._on.delete(name); },
    },
    setAttribute() {}, getAttribute: () => null,
    querySelector: selector => (selector.includes('autofocus') ? field : null),
    querySelectorAll: () => [cancel, field],
    contains(node) { return node === cancel || node === field || node === modal; },
};
const app = { id: 'app', inert: false, classList: { contains: () => false, add() {}, remove() {} } };
const frames = [];
const context = {
    console,
    requestAnimationFrame: callback => frames.push(callback),
    document: {
        activeElement: { id: 'opener', isConnected: true, focus() { focused.push('opener'); } },
        getElementById: id => (id === 'app' ? app : (id === modal.id ? modal : null)),
        querySelector: () => null,
        querySelectorAll: () => [],
        addEventListener() {},
        createElement: () => ({ classList: { add() {}, remove() {} }, setAttribute() {},
                                remove() {}, style: {} }),
        body: { appendChild() {} },
    },
    setTimeout, clearTimeout,
};
context.window = context;
vm.createContext(context);
vm.runInContext(fs.readFileSync('frontend/js/shared/utils.js', 'utf8'), context);

context.showModal('new-inquiry-modal');
// The frame the browser gives it: the dialog still has no box.
frames.shift()();
assert.deepStrictEqual(focused, [], 'focus was claimed while the dialog had no box');
boxReady = true;
while (frames.length) frames.shift()();
assert.ok(focused.length > 0, 'the dialog never took focus, so it stayed on the page behind it');
assert.strictEqual(focused[0], 'new-inquiry-company',
  'the dialog focused something other than its first field');

// And a reader who has already clicked into the dialog keeps what they chose:
// a later frame must not pull focus back to the first field.
focused.length = 0;
modal.classList.remove('show');
context.document.activeElement = cancel;
context.showModal('new-inquiry-modal');
while (frames.length) frames.shift()();
assert.deepStrictEqual(focused, [],
  'the dialog took focus away from the field the reader had already chosen');
"""


def check_a_dialog_takes_focus_even_when_the_first_try_is_too_early() -> None:
    """Opening a dialog must land focus inside it, not on the page behind."""
    result = subprocess.run(
        ["node", "-e", FOCUS_HARNESS], cwd=ROOT, text=True, capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr or result.stdout


def main() -> None:
    index = (ROOT / "frontend" / "index.html").read_text(encoding="utf-8")
    utils = (ROOT / "frontend" / "js" / "shared" / "utils.js").read_text(
        encoding="utf-8"
    )
    trip_plans = (
        ROOT / "frontend" / "js" / "modules" / "trip-plans.js"
    ).read_text(encoding="utf-8")
    trip_visits = (
        ROOT / "frontend" / "js" / "modules" / "trip-visit-actions.js"
    ).read_text(encoding="utf-8")
    user_menu = (
        ROOT / "frontend" / "js" / "modules" / "user-menu.js"
    ).read_text(encoding="utf-8")
    css = (ROOT / "frontend" / "css" / "style.css").read_text(encoding="utf-8")

    for modal_id, title_id in (
        ("login-modal", "login-modal-title"),
        ("activation-modal", "activation-modal-title"),
        ("coordinate-modal", "coordinate-modal-title"),
    ):
        marker = f'id="{modal_id}"'
        declaration = index[index.index(marker):index.index(marker) + 180]
        assert 'role="dialog"' in declaration
        assert 'aria-modal="true"' in declaration
        assert f'aria-labelledby="{title_id}"' in declaration

    assert 'id="login-error" role="alert" aria-live="assertive"' in index
    assert index.count('role="menuitem"') >= 3
    assert 'id="user-footer" role="button" tabindex="0"' in index
    assert 'id="user-menu" role="menu"' in index
    assert 'id="dashboard-status"' in index and 'aria-live="polite"' in index
    assert 'id="json-import-btn"' in index and "disabled" in index[
        index.index('id="json-import-btn"'):index.index('id="json-import-btn"') + 180
    ]

    assert "modalFocusOrigins" in utils
    assert "app.inert = true" in utils and "app.inert = false" in utils
    assert "event.key !== 'Tab'" in utils

    # A dialog that was display:none a moment ago cannot take focus yet, so
    # the first open used to leave focus on the page behind it.
    assert "modal.contains(document.activeElement)" in utils
    assert "focusInside" in utils
    company = index[index.index('id="new-inquiry-company"'):]
    assert "autofocus" in company[:company.index(">")], company[:160]

    # Escape leaves a dialog the way its Cancel button does, and only where
    # there is one: the sign-in and activation dialogs are the way in, not
    # something to dismiss.
    assert "event.key !== 'Escape'" in utils
    assert "[data-modal-dismiss]" in utils
    for modal_id, dismissible in (
        ("action-picker-modal", True),
        ("new-inquiry-modal", True),
        ("coordinate-modal", True),
        ("login-modal", False),
        ("activation-modal", False),
    ):
        start = index.index(f'id="{modal_id}"')
        end = index.index('<div id="', start + 10) if '<div id="' in index[start + 10:] else len(index)
        body = index[start:min(end, start + 4000)]
        assert ("data-modal-dismiss" in body) is dismissible, modal_id

    # A short window (or 125% zoom) must not push Save and Cancel out of the
    # panel: the tab strip scrolls in one row instead of wrapping into three,
    # the content may shrink, and the footer keeps its height.
    def rule(selector: str) -> str:
        start = css.index(selector)
        return css[start:css.index("}", start)]

    tabs = rule(".panel-tabs {")
    assert "flex-wrap: nowrap" in tabs and "overflow-x: auto" in tabs, tabs
    content = rule("\n.panel-content {")
    assert "min-height: 0" in content, content
    footer = rule(".panel-footer {")
    assert "flex: 0 0 auto" in footer, footer

    assert "window.archiveTripPlan" in trip_plans
    assert "ApiClient.archiveTripPlan(planId, rowVersion)" in trip_plans
    assert 'class="trip-plan-archive"' in trip_plans
    assert "files.slice(uploaded)" in trip_visits
    assert "if (input) input.value = ''" in trip_visits
    assert user_menu.count("PanelDirtyState.confirmDiscard()") >= 3

    check_a_dialog_takes_focus_even_when_the_first_try_is_too_early()
    print("PASS: stable UX, modal accessibility, archive and retry contracts")


if __name__ == "__main__":
    main()
