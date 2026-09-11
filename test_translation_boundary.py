"""Translation must not rewrite text it did not write.

Reading a finished sentence backwards to work out which template produced it is
a guess, and it was an unrestricted one. `{count} won` matched "Overdue
follow-up, Quoted but not won" and rendered "…but not 个已赢单". `{start} to
{end}` turned the browser's own "Failed to fetch" into "Failed 至 fetch", and a
customer's "Shanghai to Berlin" into "Shanghai 至 Berlin".

A placeholder that holds a number now matches only a number, and one that holds
a date only matches something that begins like a date. And the browser's own
words for "the program is not running" never reach the screen at all: the API
client says that in a sentence of its own.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent

HARNESS = r"""
const fs = require('fs');
const vm = require('vm');
const assert = require('assert');

function i18n(language) {
  const context = {
    console,
    CustomEvent: class { constructor(type, init) { this.type = type; Object.assign(this, init); } },
    document: {
      addEventListener() {}, getElementById: () => null,
      querySelectorAll: () => [], documentElement: { lang: 'en' }, body: null,
    },
    navigator: { language },
    localStorage: { getItem: () => null, setItem() {} },
    MutationObserver: function () { this.observe = () => {}; },
    dispatchEvent() {}, addEventListener() {},
  };
  context.window = context;
  vm.createContext(context);
  vm.runInContext(fs.readFileSync('frontend/js/i18n.js', 'utf8'), context);
  context.I18n.setLanguage(language);
  return context.I18n;
}

const zh = i18n('zh-CN');

// Text the application did not write must come back exactly as it went in.
const untouched = [
  'Failed to fetch',
  'Overdue follow-up, Quoted but not won',
  'Shanghai to Berlin',
  'ACME Laser GmbH',
  'Customer said the quote was won by a competitor',
  'Load failed: connection to host lost',
  'Deliver to Berlin, then to Hamburg',
];
for (const text of untouched) {
  assert.strictEqual(zh.t(text), text,
    `translation rewrote text it did not write: ${JSON.stringify(text)} -> ${JSON.stringify(zh.t(text))}`);
}

// Dates come in several shapes here, and all of them still resolve.
assert.ok(zh.t('Sent: Jul 17, 2026').includes('发送时间'),
  `a date written as words was rejected: ${zh.t('Sent: Jul 17, 2026')}`);

// The templates themselves still work, with the values they were made for.
assert.strictEqual(zh.t('{count} leads', { count: 3 }), '3 个商机');
assert.strictEqual(zh.t('{count} leads', { count: 0 }), '0 个商机',
  'a count of zero stopped being rendered');
assert.notStrictEqual(zh.t('2026-09-15 AM to 2026-09-16 PM'),
  '2026-09-15 AM to 2026-09-16 PM',
  'a real date range is no longer recognised');
assert.ok(zh.t('2026-09-15 AM to 2026-09-16 PM').includes('至'),
  zh.t('2026-09-15 AM to 2026-09-16 PM'));

// Reading a rendered count back is only allowed when it really is a count.
assert.strictEqual(zh.t('484 leads'), '484 个商机');
assert.strictEqual(zh.t('many leads'), 'many leads',
  'a word was read back as a number');

// A round trip through both languages leaves business text byte for byte.
const en = i18n('en');
for (const text of untouched) {
  assert.strictEqual(en.t(zh.t(text)), text,
    `a language round trip changed business text: ${JSON.stringify(text)}`);
}
"""

NETWORK = r"""
const fs = require('fs');
const vm = require('vm');
const assert = require('assert');

const context = {
  console,
  CustomEvent: class { constructor(type, init) { this.type = type; Object.assign(this, init); } },
  document: { addEventListener() {} },
  localStorage: { getItem: () => null, setItem() {}, removeItem() {} },
  sessionStorage: { getItem: () => null, setItem() {}, removeItem() {} },
  fetch: async () => { throw new TypeError('Failed to fetch'); },
  dispatchEvent() {}, addEventListener() {},
  location: { origin: 'http://127.0.0.1:8000' },
};
context.window = context;
vm.createContext(context);
const ApiClient = vm.runInContext(
  fs.readFileSync('frontend/js/api-client.js', 'utf8') + '\nApiClient;', context);

(async () => {
  let raised = null;
  try {
    await ApiClient.login('someone', 'secret');
  } catch (error) {
    raised = error;
  }
  assert.ok(raised, 'a dead server produced no error at all');
  assert.ok(!/failed to fetch/i.test(raised.message),
    `the browser's own words reached the screen: ${raised.message}`);
  assert.ok(/running/i.test(raised.message),
    `the message does not say what to do: ${raised.message}`);

  // And that sentence has a translation, so it is not English on a Chinese
  // screen at exactly the moment something went wrong.
  const i18nSource = fs.readFileSync('frontend/js/i18n.js', 'utf8');
  assert.ok(i18nSource.includes(raised.message),
    `the unreachable-program message has no translation: ${raised.message}`);
})().catch(error => { console.error(error); process.exitCode = 1; });
"""


# A screen, not a string: what the walker does to a card that has been rendered
# from real customer data, in the DOM shape the renderer produces.
SCREEN = r"""
const fs = require('fs');
const vm = require('vm');
const assert = require('assert/strict');

// Enough of a document to walk: elements that know their parent, their
// attributes and their children. `closest` is what tells business content
// apart from interface text, so it is real here rather than stubbed.
const VOID = new Set(['input', 'br', 'img', 'hr', 'meta', 'link']);
function makeElement(tag, attributes) {
  const node = {
    nodeType: 1, tagName: tag.toUpperCase(), attributes, children: [],
    parentElement: null,
    getAttribute(name) { return name in this.attributes ? this.attributes[name] : null; },
    setAttribute(name, value) { this.attributes[name] = value; },
    hasAttribute(name) { return name in this.attributes; },
    closest(selector) {
      const name = selector.replace(/^\[|\]$/g, '');
      let current = this;
      while (current) {
        if (current.hasAttribute?.(name)) return current;
        current = current.parentElement;
      }
      return null;
    },
    querySelectorAll(selector) {
      const found = [];
      const visit = element => element.children.forEach(child => {
        if (child.nodeType !== 1) return;
        if (selector === '*' || child.hasAttribute(selector.replace(/^\[|\]$/g, ''))) {
          found.push(child);
        }
        visit(child);
      });
      visit(this);
      return found;
    },
  };
  return node;
}
function parse(html) {
  const root = makeElement('div', {});
  const stack = [root];
  const tags = /<\/?([a-zA-Z0-9]+)((?:\s+[a-zA-Z0-9-]+(?:="[^"]*")?)*)\s*\/?>/g;
  const append = (parent, child) => { child.parentElement = parent; parent.children.push(child); };
  let cursor = 0, match;
  const addText = raw => {
    if (!raw.trim()) return;
    append(stack[stack.length - 1], { nodeType: 3, nodeValue: raw });
  };
  while ((match = tags.exec(html))) {
    addText(html.slice(cursor, match.index));
    cursor = match.index + match[0].length;
    const [full, tag, attributeText] = match;
    if (full.startsWith('</')) { if (stack.length > 1) stack.pop(); continue; }
    const attributes = {};
    for (const attribute of attributeText.matchAll(/([a-zA-Z0-9-]+)(?:="([^"]*)")?/g)) {
      if (attribute[1]) attributes[attribute[1]] = attribute[2] ?? '';
    }
    const element = makeElement(tag, attributes);
    append(stack[stack.length - 1], element);
    if (!VOID.has(tag.toLowerCase()) && !full.endsWith('/>')) stack.push(element);
  }
  addText(html.slice(cursor));
  return root;
}
function textNodes(root) {
  const found = [];
  const visit = node => node.children?.forEach(child => {
    if (child.nodeType === 3) found.push(child); else visit(child);
  });
  visit(root);
  return found;
}
function byClass(root, className) {
  return root.querySelectorAll('*').filter(element =>
    String(element.attributes.class || '').split(/\s+/).includes(className));
}
function textOf(element) {
  return textNodes(element).map(node => node.nodeValue.trim()).filter(Boolean).join(' ');
}

function screen(language) {
  const context = {
    console,
    CustomEvent: class { constructor(type, init) { this.type = type; Object.assign(this, init); } },
    Node: { TEXT_NODE: 3, ELEMENT_NODE: 1, DOCUMENT_NODE: 9 },
    NodeFilter: { SHOW_TEXT: 4 },
    navigator: { language },
    localStorage: { getItem: () => null, setItem() {} },
    MutationObserver: function () { this.observe = () => {}; },
    dispatchEvent() {}, addEventListener() {},
    escapeHtml: value => String(value ?? '')
      .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;'),
    formatDate: value => (value ? 'Jul 17, 2026' : ''),
  };
  context.document = {
    addEventListener() {}, getElementById: () => null,
    querySelectorAll: () => [], documentElement: { lang: language },
    body: null,
    createTreeWalker(root) {
      const nodes = textNodes(root);
      let index = -1;
      return {
        get currentNode() { return nodes[index]; },
        nextNode() { index += 1; return index < nodes.length ? nodes[index] : null; },
      };
    },
  };
  context.window = context;
  vm.createContext(context);
  vm.runInContext(fs.readFileSync('frontend/js/i18n.js', 'utf8'), context);
  vm.runInContext(fs.readFileSync('frontend/js/modules/card-template.js', 'utf8'), context);
  context.I18n.setLanguage(language);
  return context;
}

// A company really called High, a product line whose name reads like a date
// range, and a note with a date in it. All three used to come out reworded.
const lead = {
  id: 'lead-1', inquiry_id: 'JPT-1', company_name: 'High',
  contact_name: 'Open', country: 'Germany', product_category: 'Laser 1 to Laser 2',
  stage: 'New', quality_rating: 'High', inquiry_date: '2026-07-17',
  latest_follow_up_summary: 'Customer appointment Jul 17, 2026',
  // A colleague whose name is also a word this interface uses.
  pre_sales_owner: 'Open',
};

const context = screen('zh-CN');
const card = parse(context.renderInquiryCard(lead, 'handler'));
context.I18n.apply(card);

assert.equal(textOf(byClass(card, 'card-company')[0]), 'High',
  'the customer name was translated into a quality grade');
assert.equal(textOf(byClass(card, 'card-contact')[0]), 'Open Germany',
  'a contact name was translated');
assert.equal(textOf(byClass(card, 'card-value')[0]), 'Laser 1 to Laser 2',
  'a product line was read as a date range');

// The interface around them is in Chinese: the labels the renderer asked for,
// and the badges that really are status words - including the grade badge,
// which says High about the same customer and means the grade.
assert.equal(textOf(byClass(card, 'card-label')[0]), '产品',
  'an interface label was left in English');
assert.notEqual(textOf(byClass(card, 'stage-badge')[0]), 'New',
  'a real status label stopped being translated');
assert.equal(textOf(byClass(card, 'grade-badge')[0]), '高',
  'the quality grade stopped being translated');

// A customer's own note, with a date in it, in the cell that shows it.
const sampled = parse(context.renderInquiryCard(lead, 'sampling'));
context.I18n.apply(sampled);
const note = byClass(sampled, 'card-value')
  .map(textOf).find(text => text.startsWith('Customer appointment'));
assert.equal(note, 'Customer appointment Jul 17, 2026',
  `a date inside a customer note was rewritten: ${note}`);

// And a detail cell holding a name that is also one of this interface's own
// words: the cell is data, so it stays as it was typed. The label beside it
// is ours, so it is in Chinese.
const detailLabels = byClass(sampled, 'card-label').map(textOf);
const owner = detailLabels.indexOf(context.I18n.t('Pre-sales'));
assert.ok(owner >= 0, `the pre-sales label was not translated: ${detailLabels}`);
assert.equal(textOf(byClass(sampled, 'card-value')[owner]), 'Open',
  'a name in a detail cell was translated into a status word');

// Switching back and forth does not wear the business text down either.
context.I18n.setLanguage('en');
context.I18n.apply(card);
context.I18n.setLanguage('zh-CN');
context.I18n.apply(card);
assert.equal(textOf(byClass(card, 'card-company')[0]), 'High');
assert.equal(textOf(byClass(card, 'card-value')[0]), 'Laser 1 to Laser 2');
assert.equal(textOf(byClass(card, 'card-label')[0]), '产品',
  'the labels stopped following the language');
assert.equal(textOf(byClass(card, 'grade-badge')[0]), '高',
  'the quality grade stopped following the language');

// Text nobody wrote a translation for is left alone wherever it appears - the
// walker no longer works backwards from a finished sentence at all.
const loose = { nodeType: 3, nodeValue: 'Customer appointment Jul 17, 2026',
                parentElement: null };
context.I18n.apply(loose);
assert.equal(loose.nodeValue, 'Customer appointment Jul 17, 2026',
  'a date inside a customer note was reformatted');

// And a sentence the interface builds itself still reads in the language now
// chosen, because it is drawn again rather than read back off the screen.
assert.equal(context.I18n.t('{count} leads', { count: 3 }), '3 个商机');
"""

# The counterpart to not guessing: the view that owns a built sentence draws it
# again when the language changes.
# What a customer is called can be any word at all, this interface's own words
# included. Only the renderer knows which it printed, so the renderer says so.
NAME_FIELDS = (
    "customer_name", "company_name", "display_name", "displayName",
    "contact_name", "user_name", "original_name",
)
# One place where the name shares an element with an interface word, and the
# element cannot hold children to separate them: a member picker option reads
# "Amy · Leader". The role word stays translatable there.
ALLOWED_UNMARKED = {
    ("authorization-center-view.js", "member.displayName"),
}


def check_every_printed_name_says_it_is_business_text() -> None:
    import re

    tag_with_value = re.compile(r"<([a-z]+)([^<>]{0,200})>\s*(\$\{[^{}`]*\})")
    unmarked = []
    for path in sorted((ROOT / "frontend" / "js").rglob("*.js")):
        text = path.read_text(encoding="utf-8")
        for tag, attributes, expression in tag_with_value.findall(text):
            field = next(
                (name for name in NAME_FIELDS
                 if re.search(rf"\b{re.escape(name)}\b", expression)), None,
            )
            if not field or "data-business" in attributes:
                continue
            if (path.name, f"member.{field}") in ALLOWED_UNMARKED:
                continue
            unmarked.append(f"{path.name}: <{tag}> prints {field}")
    assert not unmarked, (
        "a name typed by somebody is printed without saying it is theirs, so "
        "the language switch may translate it into one of this interface's "
        f"own words: {unmarked}"
    )


# Switching language now redraws the view that owns the sentence. What it must
# never do is redraw over somebody's unfinished work.
DRAFTS = r"""
const fs = require('fs');
const vm = require('vm');
const assert = require('assert/strict');

function build({ dirty = false, formOpen = false, inquiry = { id: 'A' },
                 activeModule = 'handler', tab = 'followup' } = {}) {
  const seen = { modules: [], panels: [], trip: [], counts: 0 };
  const context = {
    console: { log() {}, error() {} },
    I18n: { t: text => text },
    localStorage: { getItem: () => null, setItem() {} },
    setText() {}, escapeHtml: value => String(value ?? ''),
    notify() {}, alert() {}, confirm: () => true,
    showModal() {}, hideModal() {},
    PanelDirtyState: { isDirty: () => dirty, reset() {} },
    renderPanelContent: value => seen.panels.push(value),
    loadDashboard: async () => {}, loadHandler: async () => {},
    loadFollowup: async () => {}, loadSampling: async () => {},
    loadDeal: async () => {}, loadFulfillment: async () => {},
    loadAftersales: async () => {}, loadDataReview: async () => {},
    loadCoordinateReview: async () => {}, loadAuthorizationCenter: async () => {},
    loadTripPlanner: async options => { seen.trip.push(options); return true; },
    ApiClient: { isLoggedIn: () => false },
    RoleCapabilities: { canAccessModule: () => true, initialModule: () => 'handler' },
  };
  const handlers = {};
  context.document = {
    addEventListener() {},
    getElementById: () => null,
    querySelector: selector => {
      if (selector === '.module.active') return { id: `module-${activeModule}` };
      if (selector === '.panel-tab.active') return { dataset: { tab } };
      if (selector.includes('data-panel-form')) return formOpen ? {} : null;
      return null;
    },
    querySelectorAll: () => [],
  };
  context.window = context;
  context.addEventListener = (name, handler) => { handlers[name] = handler; };
  vm.createContext(context);
  vm.runInContext(fs.readFileSync('frontend/js/app.js', 'utf8'), context, { filename: 'app.js' });
  // `State` is declared with const, so it is not a property of the global
  // object - the same reason window.State is undefined in a browser.
  const state = vm.runInContext('State', context);
  state.user = { id: 'u1' };
  state.currentInquiry = inquiry;
  const original = context.loadModuleData;
  context.loadModuleData = async (module, options) => {
    seen.modules.push([module, options]);
    return original(module, options);
  };
  return { context, handlers, seen };
}

(async () => {
  // Clean panel, nothing open: redrawn in the new language.
  const clean = build();
  clean.handlers['language:changed']();
  await new Promise(resolve => setImmediate(resolve));
  assert.deepEqual(clean.seen.panels, ['followup'], 'a clean panel was not redrawn');
  assert.equal(JSON.stringify(clean.seen.modules),
    JSON.stringify([['handler', { automatic: true }]]));

  // Something typed in the panel: left alone.
  const typed = build({ dirty: true });
  typed.handlers['language:changed']();
  assert.deepEqual(typed.seen.panels, [], 'switching language discarded typed input');

  // An editor open but untouched - filled in from an existing record.
  const editing = build({ formOpen: true });
  editing.handlers['language:changed']();
  assert.deepEqual(editing.seen.panels, [],
    'switching language closed an open edit form');

  // The trip planner is reloaded as an automatic reload, so its own draft
  // guard stays silent instead of asking the reader to discard.
  const trip = build({ activeModule: 'trip-planner', inquiry: null });
  trip.handlers['language:changed']();
  await new Promise(resolve => setImmediate(resolve));
  assert.equal(JSON.stringify(trip.seen.trip), JSON.stringify([{ automatic: true }]),
    `the trip reload was not marked automatic: ${JSON.stringify(trip.seen.trip)}`);

  console.log('OK');
})().catch(error => { console.error(error); process.exitCode = 1; });
"""


def check_no_sentence_is_built_from_a_bare_english_label() -> None:
    """`Sent: ${date}` used to be translated by reading it back off the screen.

    That guess is gone, so a label glued to a value in a template literal would
    now stay English on a Chinese screen. The renderer has to ask for the whole
    sentence - I18n.t('Sent: {date}', {date}) - which is also the only form
    that can put the label after the value in another language.
    """
    import re

    label_then_value = re.compile(r">([^<>${}]*[A-Za-z][^<>${}]*)\$\{")
    ui_text = re.compile(r"^[A-Za-z][A-Za-z ]{1,30}:?$")
    built = []
    for path in sorted((ROOT / "frontend" / "js").rglob("*.js")):
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            for literal in label_then_value.findall(line):
                text = literal.strip()
                if not ui_text.match(text):
                    continue
                built.append(f"{path.name}:{number}: {text!r} + a value")
    assert not built, (
        "these build a sentence from an English label and a value, which "
        f"nothing translates any more: {built}"
    )


def check_the_screen_is_redrawn_on_a_language_change() -> None:
    source = (ROOT / "frontend" / "js" / "app.js").read_text(encoding="utf-8")
    listener = source[source.index("language:changed"):]
    listener = listener[:listener.index("\n});")]
    for expected, why in (
        ("loadModuleData", "the module on screen is never drawn again"),
        ("renderPanelContent", "an open panel keeps the language it was drawn in"),
        ("PanelDirtyState.isDirty()", "a language change discards an unsaved edit"),
    ):
        assert expected in listener, (
            f"language changes leave the screen behind: {why}"
        )


def run(script: str, label: str) -> None:
    result = subprocess.run(
        ["node", "-e", script], cwd=ROOT, text=True, capture_output=True, check=False,
    )
    assert result.returncode == 0, f"{label}: {result.stderr or result.stdout}"


def main() -> None:
    run(HARNESS, "template boundary")
    run(NETWORK, "unreachable program")
    run(SCREEN, "a rendered card")
    run(DRAFTS, "a language change over unfinished work")
    check_the_screen_is_redrawn_on_a_language_change()
    check_every_printed_name_says_it_is_business_text()
    check_no_sentence_is_built_from_a_bare_english_label()
    print("PASS: translation leaves business text alone and says when the program is gone")


if __name__ == "__main__":
    main()
