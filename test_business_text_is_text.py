"""What a customer wrote is text. It was written into the page as markup.

A follow-up's content, the customer's own feedback and the next action were
interpolated straight into the panel's HTML. Those fields arrive from the email
parser, the spreadsheet import and the JSON exchange as well as from typing, so
an enquiry body carrying `<img src=x onerror=...>` was built into the panel of
whoever opened that lead - it ran with their session, on their machine.

Escaping alone would flatten the line breaks somebody typed, so the stylesheet
keeps them (`white-space: pre-wrap`). Both halves are checked here: nothing the
customer writes becomes an element, and what they wrote still reads the way
they wrote it.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent
MODULES = ROOT / "frontend" / "js" / "modules"
CSS = (ROOT / "frontend" / "css" / "style.css").read_text(encoding="utf-8")

# Fields whose value is written by a person - a customer, a colleague, or an
# imported document - and therefore never markup.
WRITTEN_BY_A_PERSON = (
    "content", "customer_feedback", "next_action", "issue_description",
    "solution", "lessons_learned", "remarks", "notes", "result_notes",
    "description", "special_requirements", "request_description",
    "visit_purpose", "customer_satisfaction", "lost_reason_text",
)
# Wrappers that escape their argument. `row()` in sampling-task-details.js is
# one line long and does `escapeHtml(display(value))`; the check below keeps it
# honest by requiring that to still be true.
SAFE_CALLS = ("escapeHtml(", "h(", "esc(", "safe(", "value(", "display(", "row(")


def check_no_written_field_is_interpolated_as_markup() -> None:
    """Every one of those fields reaches the page through an escape."""
    pattern = re.compile(r"\$\{([^{}`]*)\}")
    offenders = []
    for path in sorted(MODULES.glob("*.js")):
        text = path.read_text(encoding="utf-8")
        for number, line in enumerate(text.splitlines(), 1):
            for expression in pattern.findall(line):
                field = next(
                    (name for name in WRITTEN_BY_A_PERSON
                     if re.search(rf"\.{name}\b", expression)), None,
                )
                if not field:
                    continue
                if any(call in expression for call in SAFE_CALLS):
                    continue
                offenders.append(f"{path.name}:{number}: {expression.strip()[:70]}")
    assert not offenders, (
        "these write somebody's own words into the page as markup: " + str(offenders)
    )


def check_the_escaping_wrappers_still_escape() -> None:
    """The list above trusts these by name, so their bodies are checked."""
    details = (MODULES / "sampling-task-details.js").read_text(encoding="utf-8")
    assert "escapeHtml(display(value))" in details, (
        "sampling-task-details.js no longer escapes the value it prints"
    )


def check_the_line_breaks_they_typed_survive() -> None:
    """Escaping without this turns a typed paragraph into one long line."""
    for selector in (".followup-content", ".followup-feedback", ".followup-next"):
        block = CSS[CSS.index(f"{selector} {{"):]
        block = block[:block.index("}")]
        assert "white-space: pre-wrap" in block, (
            f"{selector} escapes the text but drops the line breaks in it"
        )


HARNESS = r"""
const fs = require('fs');
const vm = require('vm');
const assert = require('assert/strict');

// Enough of a document to see whether an element was created.
const VOID = new Set(['input', 'br', 'img', 'hr', 'meta', 'link']);
function element(tag, attributes) {
  return {
    nodeType: 1, tagName: tag.toUpperCase(), attributes, children: [],
    parentElement: null,
    hasAttribute(name) { return name in this.attributes; },
    descendants() {
      const found = [];
      const visit = node => node.children.forEach(child => {
        found.push(child);
        if (child.nodeType === 1) visit(child);
      });
      visit(this);
      return found;
    },
  };
}
function parse(html) {
  const root = element('div', {});
  const stack = [root];
  const tags = /<\/?([a-zA-Z0-9]+)((?:\s+[a-zA-Z0-9-]+(?:="[^"]*")?)*)\s*\/?>/g;
  const append = (parent, child) => { child.parentElement = parent; parent.children.push(child); };
  const addText = raw => {
    if (raw) append(stack[stack.length - 1], { nodeType: 3, nodeValue: raw });
  };
  let cursor = 0, match;
  while ((match = tags.exec(html))) {
    addText(html.slice(cursor, match.index));
    cursor = match.index + match[0].length;
    const [full, tag, attributeText] = match;
    if (full.startsWith('</')) { if (stack.length > 1) stack.pop(); continue; }
    const attributes = {};
    for (const item of attributeText.matchAll(/([a-zA-Z0-9-]+)(?:="([^"]*)")?/g)) {
      if (item[1]) attributes[item[1]] = item[2] ?? '';
    }
    const node = element(tag, attributes);
    append(stack[stack.length - 1], node);
    if (!VOID.has(tag.toLowerCase()) && !full.endsWith('/>')) stack.push(node);
  }
  addText(html.slice(cursor));
  return root;
}
const unescape = value => value.replace(/&lt;/g, '<').replace(/&gt;/g, '>')
  .replace(/&quot;/g, '"').replace(/&#39;/g, "'").replace(/&amp;/g, '&');
const byClass = (root, name) => root.descendants().filter(node =>
  node.nodeType === 1 && String(node.attributes.class || '').split(/\s+/).includes(name));
const textOf = node => node.descendants()
  .filter(child => child.nodeType === 3).map(child => child.nodeValue).join('');

const context = {
  console,
  escapeHtml: value => String(value ?? '').replace(/&/g, '&amp;').replace(/</g, '&lt;')
    .replace(/>/g, '&gt;').replace(/"/g, '&quot;').replace(/'/g, '&#39;'),
  formatDate: value => String(value || '-'),
  I18n: { t: (text, params = {}) => Object.entries(params)
    .reduce((acc, [key, value]) => acc.replaceAll(`{${key}}`, value), text) },
};
context.window = context;
vm.createContext(context);
vm.runInContext(fs.readFileSync('frontend/js/modules/followups-view.js', 'utf8'), context);

// An enquiry body of the kind the parser and the import actually carry.
const HOSTILE = '<img src=x onerror="window.__ran = true">\nThey want <b>two</b> heads & a quote';
const html = context.renderFollowupsTab({
  follow_ups: [{
    date: '2026-07-17', method: '<script>bad()</script>Email',
    status: '<svg onload=1>pending', content: HOSTILE,
    customer_feedback: HOSTILE, next_action: HOSTILE,
    next_action_date: '2026-07-20',
  }],
});
const rendered = parse(html);

for (const [name, selector] of [
  ['跟进内容', 'followup-content'],
  ['客户反馈', 'followup-feedback'],
  ['下一步', 'followup-next'],
]) {
  const holder = byClass(rendered, selector)[0];
  assert.ok(holder, `${name}: not rendered at all`);
  const elements = holder.descendants().filter(node => node.nodeType === 1
    && !['LABEL', 'SPAN', 'STRONG'].includes(node.tagName));
  assert.deepEqual(elements.map(node => node.tagName), [],
    `${name}: the customer's words created ${elements.map(node => node.tagName)}`);
  assert.ok(unescape(textOf(holder)).includes(HOSTILE),
    `${name}: what they wrote is not shown as they wrote it: ${textOf(holder)}`);
}

// Neither is the enum shown beside them a way in.
assert.ok(!/<script>/.test(html), 'a stored method value carried a script tag through');
assert.ok(!/<svg/.test(html), 'a stored status value carried an element through');
// And the escaped text is still the text: nothing was dropped to make it safe.
assert.ok(html.includes('&lt;img src=x onerror=&quot;window.__ran = true&quot;&gt;'), html.slice(0, 400));
"""


def main() -> None:
    check_no_written_field_is_interpolated_as_markup()
    check_the_escaping_wrappers_still_escape()
    check_the_line_breaks_they_typed_survive()
    result = subprocess.run(
        ["node", "-e", HARNESS], cwd=ROOT, text=True, capture_output=True, check=False,
    )
    assert result.returncode == 0, result.stderr or result.stdout
    print("PASS: what a customer wrote is shown as text, and still reads as they wrote it")


if __name__ == "__main__":
    main()
