"""Static and runtime contracts for worklist selection, search and panel safety."""

from __future__ import annotations

import subprocess
from pathlib import Path


ROOT = Path(__file__).parent
FRONTEND = ROOT / "frontend"
MODULES = FRONTEND / "js" / "modules"


def main() -> None:
    index = (FRONTEND / "index.html").read_text(encoding="utf-8")
    cards = (MODULES / "cards.js").read_text(encoding="utf-8")
    card_template = (MODULES / "card-template.js").read_text(encoding="utf-8")
    panel = (MODULES / "inquiry-panel.js").read_text(encoding="utf-8")
    panel_data = (MODULES / "inquiry-panel-data.js").read_text(encoding="utf-8")
    search = (MODULES / "global-search.js").read_text(encoding="utf-8")
    navigation = (MODULES / "lead-navigation.js").read_text(encoding="utf-8")
    css = (FRONTEND / "css" / "style.css").read_text(encoding="utf-8")
    utils = (FRONTEND / "js" / "shared" / "utils.js").read_text(encoding="utf-8")

    for source in ("worklist-ui.js", "panel-dirty-state.js", "global-search.js", "inquiry-panel-data.js"):
        assert source in index
    assert 'role="button" tabindex="0" aria-pressed="false"' in card_template
    assert "['Enter', ' ']" in cards and "WorklistUI.syncCards(container)" in cards
    assert "data-quality-tab-badge" in panel
    assert "PanelDirtyState.confirmDiscard()" in panel
    assert "InquiryPanelData.load" in panel
    assert ".catch(() => [])" not in panel_data
    assert "listLeads({ search: query, limit: 20 })" in search
    assert "ArrowDown" in search and "ArrowUp" in search and "Escape" in search
    assert "jumpToCustomerStageCards" in search
    assert "window.PanelDirtyState.confirmDiscard()" in search
    assert search.index("window.PanelDirtyState.confirmDiscard()") < search.index("input().value = '';")
    assert "await loadModuleData(module)" not in navigation
    assert "worklist-toolbar" in css and 'grid-template-areas: "primary controls summary action"' in css
    assert "global-search-results" in css and "panel-tab-badge" in css
    assert "toast.setAttribute('aria-live', 'polite')" in utils
    for source in (
        "followups-form.js", "aftersales-form.js", "files-form.js",
        "sampling-form-controller.js",
    ):
        assert "PanelDirtyState?.reset?.()" in (
            MODULES / source
        ).read_text(encoding="utf-8")
    for source in ("inquiry-save.js", "followups-actions.js", "aftersales-actions.js", "files-actions.js"):
        assert "disabled = true" in (MODULES / source).read_text(encoding="utf-8")

    harness = r"""
const fs = require('fs');
const vm = require('vm');
const assert = require('assert');

function classes(initial = []) {
  const values = new Set(initial);
  return {
    values,
    toggle(name, enabled) { enabled ? values.add(name) : values.delete(name); },
    contains(name) { return values.has(name); },
  };
}
function card(id) {
  return {
    dataset: { inquiryId: id }, classList: classes(), attributes: {},
    setAttribute(name, value) { this.attributes[name] = value; },
  };
}
function badge() {
  return {
    textContent: '', classList: classes(['hidden']), attributes: {},
    setAttribute(name, value) { this.attributes[name] = value; },
  };
}
const cards = [card('lead-1'), card('lead-2')];
const cardBadge = badge();
const tabBadge = badge();
const contentHandlers = {};
const content = {
  dataset: {},
  addEventListener(name, handler) { contentHandlers[name] = handler; },
};
let confirmResult = true;
const domReady = [];
const context = {
  console,
  CSS: { escape: value => value },
  State: { selectedLeadId: '', selectedCardContext: '', currentInquiry: null },
  I18n: { t: (text, params = {}) => text.replace(/\{(\w+)\}/g, (_, key) => params[key]) },
  confirm: () => confirmResult,
  document: {
    addEventListener(name, handler) { if (name === 'DOMContentLoaded') domReady.push(handler); },
    getElementById(id) { return id === 'panel-content' ? content : null; },
    querySelectorAll(selector) {
      if (selector === '[data-inquiry-card]') return cards;
      if (selector.includes('[data-inquiry-id=')) return [cardBadge];
      if (selector === '[data-quality-tab-badge]') return [tabBadge];
      return [];
    },
  },
};
context.window = context;
vm.createContext(context);
vm.runInContext(fs.readFileSync('frontend/js/modules/worklist-ui.js', 'utf8'), context);
context.WorklistUI.select('lead-2', 'deal');
assert.strictEqual(cards[0].classList.contains('active'), false);
assert.strictEqual(cards[1].classList.contains('active'), true);
assert.strictEqual(cards[1].attributes['aria-pressed'], 'true');
context.State.currentInquiry = { id: 'lead-2', _lead: { quality_issue_count: 2 } };
context.WorklistUI.syncQualityCount('lead-2', 1);
assert.strictEqual(cardBadge.textContent, '1 to review');
assert.strictEqual(tabBadge.textContent, '1');
assert.strictEqual(tabBadge.classList.contains('hidden'), false);
context.WorklistUI.clear();
assert.strictEqual(cards[1].classList.contains('active'), false);

vm.runInContext(fs.readFileSync('frontend/js/modules/panel-dirty-state.js', 'utf8'), context);
context.PanelDirtyState.init();
contentHandlers.input({ target: { matches: () => true } });
assert.strictEqual(context.PanelDirtyState.isDirty(), true);
confirmResult = false;
assert.strictEqual(context.PanelDirtyState.confirmDiscard(), false);
confirmResult = true;
assert.strictEqual(context.PanelDirtyState.confirmDiscard(), true);
assert.strictEqual(context.PanelDirtyState.isDirty(), false);
"""
    result = subprocess.run(
        ["node", "-e", harness], cwd=ROOT, text=True, capture_output=True, check=False
    )
    assert result.returncode == 0, result.stderr or result.stdout
    print("PASS: worklist selection, quality badge, global search and panel safety contracts")


if __name__ == "__main__":
    main()
