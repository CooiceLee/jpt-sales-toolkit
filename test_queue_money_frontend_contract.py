"""What the reader is shown: whole lists, honest totals, real grades.

Four things were being read off the screen and believed. A queue that had only
fetched its first page reported that page as the whole picture. A sum of
several currencies was printed under a dollar sign. Every card wore a C because
the grade never reached it. And an average cycle time that nothing computed sat
at zero.

These run the real modules rather than checking them for the right words.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def run(script: str, label: str) -> None:
    result = subprocess.run(
        ["node", "-e", script], cwd=ROOT, text=True, capture_output=True, check=False,
    )
    assert result.returncode == 0, f"{label}: {result.stderr or result.stdout}"


PAGING = r"""
const fs = require('fs');
const vm = require('vm');
const assert = require('assert');

const context = { console };
context.window = context;
vm.createContext(context);
vm.runInContext(fs.readFileSync('frontend/js/modules/paged-fetch.js', 'utf8'), context);

(async () => {
  // The page-size boundaries: one short of a page, exactly a page, one over,
// and the audit's 105.
for (const total of [99, 100, 101, 105]) {
  const rows = Array.from({ length: total }, (_, index) => ({ id: index }));
  const read = await context.PagedFetch.all(
    ({ limit, offset }) => Promise.resolve(rows.slice(offset, offset + limit)),
    { pageSize: 100 },
  );
  assert.strictEqual(read.items.length, total, `${total} rows read as ${read.items.length}`);
  assert.strictEqual(read.complete, true, `${total} rows reported as truncated`);
  assert.strictEqual(new Set(read.items.map(item => item.id)).size, total,
    `${total} rows: a row came back twice`);
}

// A page that fails is not a shorter list: it has to raise, so the caller can
// say "unable to load" instead of showing part of a queue as all of it.
let raised = null;
try {
  await context.PagedFetch.all(({ offset }) => (offset > 0
    ? Promise.reject(new Error('page 2 is unavailable'))
    : Promise.resolve(Array.from({ length: 100 }, (_, i) => ({ id: i })))),
    { pageSize: 100 });
} catch (error) { raised = error; }
assert.ok(raised, 'a failed second page was swallowed and the list looked complete');

// 105 rows behind a 100-row default: the shape that lost four customers.
  const rows = Array.from({ length: 105 }, (_, index) => ({ id: index }));
  const asked = [];
  const read = await context.PagedFetch.all(({ limit, offset }) => {
    asked.push({ limit, offset });
    return Promise.resolve(rows.slice(offset, offset + limit));
  }, { pageSize: 40 });
  assert.strictEqual(read.items.length, 105, 'the list stopped short');
  assert.strictEqual(read.complete, true, 'a complete read reported itself as partial');
  assert.strictEqual(new Set(read.items.map(item => item.id)).size, 105,
    'a row came back twice');
  assert.ok(asked.length >= 3, `only ${asked.length} pages were asked for`);
  assert.deepStrictEqual(asked[0], { limit: 40, offset: 0 });
  assert.deepStrictEqual(asked[1], { limit: 40, offset: 40 });

  // A list longer than the ceiling must say so rather than look complete.
  const endless = await context.PagedFetch.all(
    ({ limit }) => Promise.resolve(Array.from({ length: limit }, (_, i) => ({ id: i }))),
    { pageSize: 10, ceiling: 30 },
  );
  assert.strictEqual(endless.complete, false,
    'a read that hit its ceiling reported itself as complete');
  assert.strictEqual(endless.items.length, 30);

  // An endpoint that caps the page size below what was asked for must not end
  // the read: a full page that looks short is exactly how the rest of a list
  // disappears while the read calls itself complete.
  const capped = Array.from({ length: 105 }, (_, index) => ({ id: index }));
  const cappedRead = await context.PagedFetch.all(({ offset }) =>
    Promise.resolve(capped.slice(offset, offset + 10)), { pageSize: 500 });
  assert.strictEqual(cappedRead.items.length, 105,
    `a capped endpoint ended the read after ${cappedRead.items.length} rows`);
  assert.strictEqual(cappedRead.complete, true);
  assert.strictEqual(new Set(cappedRead.items.map(item => item.id)).size, 105);

  // An exact multiple of the page size still asks once more before finishing.
  const exact = Array.from({ length: 80 }, (_, index) => ({ id: index }));
  const readExact = await context.PagedFetch.all(
    ({ limit, offset }) => Promise.resolve(exact.slice(offset, offset + limit)),
    { pageSize: 40 },
  );
  assert.strictEqual(readExact.items.length, 80);
  assert.strictEqual(readExact.complete, true);
})().catch(error => { console.error(error); process.exitCode = 1; });
"""

MONEY = r"""
const fs = require('fs');
const vm = require('vm');
const assert = require('assert');

const context = { console, I18n: { t: (text, params = {}) =>
  String(text).replace(/\{(\w+)\}/g, (_, key) => params[key] ?? `{${key}}`) },
  document: { addEventListener() {}, getElementById: () => null,
              querySelector: () => null, querySelectorAll: () => [] },
  navigator: { language: 'en' } };
context.window = context;
vm.createContext(context);
vm.runInContext(fs.readFileSync('frontend/js/modules/money-totals-view.js', 'utf8'), context);
vm.runInContext(fs.readFileSync('frontend/js/shared/utils.js', 'utf8'), context);

const { MoneyTotals, formatMoney } = context;

// Four deals of 10,000 EUR and one of 1,200 USD. There is no single total, and
// nothing may print one.
const mixed = MoneyTotals.text({ EUR: 40000, USD: 1200 });
assert.ok(mixed.includes('EUR'), `no currency named: ${mixed}`);
assert.ok(mixed.includes('USD'), `a currency went missing: ${mixed}`);
assert.ok(!mixed.includes('$'), `a dollar sign over unconverted amounts: ${mixed}`);
assert.ok(!/41[,.]?200/.test(mixed) && !mixed.includes('41K'),
  `the currencies were added together: ${mixed}`);

// An amount nobody gave a currency stays visible as exactly that.
const unspecified = MoneyTotals.text({ UNSPECIFIED: 500 });
assert.ok(!unspecified.includes('UNSPECIFIED'),
  `an internal marker reached the screen: ${unspecified}`);
assert.ok(unspecified.toLowerCase().includes('no currency'), unspecified);

// Deals recorded at zero are a different fact from no deals at all, and the
// two used to print the same em dash.
const realZero = MoneyTotals.text({ EUR: 0 });
assert.notStrictEqual(realZero, '—',
  'a subtotal of zero was shown as if nothing had been recorded');
assert.ok(realZero.includes('EUR') && realZero.includes('0'), realZero);
const zeroBeside = MoneyTotals.text({ EUR: 0, USD: 5 });
assert.ok(zeroBeside.includes('EUR'),
  `a zero subtotal disappeared next to a non-zero one: ${zeroBeside}`);

// A total is printed in a unit the reader can take in at a glance. Everything
// above a thousand used to be printed in thousands, so 4.16 trillion came out
// as "4,164,615,261K": eleven digits to count through, wrapping mid-number
// across three lines of a 36px value.
assert.strictEqual(MoneyTotals.compact(4164615261345), '4.16T',
  `a trillion printed as ${MoneyTotals.compact(4164615261345)}`);
assert.strictEqual(MoneyTotals.compact(413453466), '413M');
assert.strictEqual(MoneyTotals.compact(40000), '40K');
assert.strictEqual(MoneyTotals.compact(40500), '40.5K');
assert.strictEqual(MoneyTotals.compact(500), '500');
assert.ok(!MoneyTotals.compact(4164615261345).includes(',000'),
  'the unit did not keep up with the size of the number');

// A settled order, by currency code, with the amount nobody gave a currency
// last. Sorted by size instead, the biggest *number* came first and the card
// gave it the headline - so JPY 1,000,000 outranked EUR 100,000 and read as
// the larger piece of business, which is a comparison nothing here can make.
const order = MoneyTotals.entries({
  JPY: 1000000, EUR: 100000, UNSPECIFIED: 5000, CNY: 4300000,
}).map(([code]) => code).join(',');
assert.strictEqual(order, 'CNY,EUR,JPY,UNSPECIFIED',
  `the currencies are ranked by their unconverted numbers: ${order}`);

// And the subtotals stay available apart, so a card can lay them out instead
// of wrapping one long string.
const rows = MoneyTotals.rows({ USD: 413453466, EUR: 4164615261345 });
assert.strictEqual(rows.map(row => row.code).join(','), 'EUR,USD', JSON.stringify(rows));
assert.strictEqual(rows[0].amount, '4.16T');
assert.deepEqual(MoneyTotals.rows({}), []);
assert.strictEqual(MoneyTotals.rows({ UNSPECIFIED: 5 })[0].code.toLowerCase(),
  'no currency');

assert.strictEqual(MoneyTotals.text({}), '—', 'nothing recorded must not read as zero');
assert.strictEqual(MoneyTotals.text(null), '—');
assert.strictEqual(MoneyTotals.missingNote(0), '');
assert.ok(MoneyTotals.missingNote(3).includes('3'));

// The shared formatter must not label a number with a currency it was not
// given, and must use the one it was.
assert.ok(!formatMoney(1234).includes('$'), formatMoney(1234));
assert.ok(formatMoney(1234, 'eur').startsWith('EUR'), formatMoney(1234, 'eur'));
assert.strictEqual(formatMoney(0), '-');
"""

GRADE = r"""
const fs = require('fs');
const vm = require('vm');
const assert = require('assert');

const context = {
  console,
  escapeHtml: value => String(value ?? ''),
  I18n: { t: text => text },
  State: { user: { id: 'u1', role: 'leader' } },
  getLeadPrimaryContact: () => null,
  formatDate: value => String(value ?? ''),
  formatMoney: value => String(value ?? ''),
  daysBetween: () => 0,
};
context.window = context;
vm.createContext(context);
vm.runInContext(fs.readFileSync('frontend/js/modules/lead-navigation.js', 'utf8'), context);
vm.runInContext(fs.readFileSync('frontend/js/modules/card-template.js', 'utf8'), context);

const lead = (grade) => ({
  id: 'lead-1', display_id: 'JPT-1', sales_stage: 'Quoted',
  customer: { display_name: 'Customer' }, quality_grade: grade,
  assignments: [], owner_id: 'u1',
});

// The grade somebody recorded is the grade the card shows.
const gradedA = context.leadToCardItem(lead('A'));
assert.strictEqual(gradedA.quality_rating, 'A',
  'the card adapter dropped the grade, so every card fell back to C');
const cardA = context.renderInquiryCard(gradedA, 'handler');
assert.ok(/grade-a/.test(cardA), `an A-graded lead did not render as A: ${cardA.slice(0, 400)}`);
assert.ok(!/grade-c/.test(cardA), 'an A-graded lead still rendered a C badge');

// A lead nobody has graded says so, instead of wearing the lowest grade.
const ungraded = context.leadToCardItem(lead(null));
assert.strictEqual(ungraded.quality_rating, null);
const cardNone = context.renderInquiryCard(ungraded, 'handler');
assert.ok(!/grade-c/.test(cardNone),
  'an ungraded lead was shown as grade C, which is a judgement nobody made');
assert.ok(/grade-none/.test(cardNone), `no ungraded state: ${cardNone.slice(0, 400)}`);

// The two are different things and must not be confused with each other.
const withIssues = context.leadToCardItem({ ...lead('B'), quality_issue_count: 4 });
assert.strictEqual(withIssues.quality_rating, 'B');
assert.strictEqual(withIssues.quality_issue_count, 4);
"""

CYCLE = r"""
const fs = require('fs');
const vm = require('vm');
const assert = require('assert');

const context = { console, I18n: { t: (text, params = {}) =>
  String(text).replace(/\{(\w+)\}/g, (_, key) => params[key] ?? `{${key}}`) } };
context.window = context;
vm.createContext(context);
vm.runInContext(fs.readFileSync('frontend/js/modules/deal-cycle.js', 'utf8'), context);
const { DealCycle } = context;

// Two won deals, 10 and 20 days from enquiry to order: fifteen days, from two
// of the three won deals, and the third is not counted as zero.
const measured = DealCycle.measure([
  { sales_stage: 'Won', inquiry_date: '2026-01-01', po_date: '2026-01-11' },
  { sales_stage: 'Won', inquiry_date: '2026-02-01', po_date: '2026-02-21' },
  { sales_stage: 'Won', inquiry_date: '2026-03-01', po_date: null },
  { sales_stage: 'Quoted', inquiry_date: '2026-01-01', po_date: '2026-01-05' },
]);
assert.strictEqual(measured.days, 15, `average is ${measured.days}`);
assert.strictEqual(measured.counted, 2, 'a deal with no PO date was counted');
assert.strictEqual(measured.wonCount, 3, 'the sample size is not the won count');
assert.ok(DealCycle.note(measured).includes('2'), DealCycle.note(measured));
assert.ok(DealCycle.note(measured).includes('3'), DealCycle.note(measured));

// Nothing to measure is not zero days.
const empty = DealCycle.measure([
  { sales_stage: 'Won', inquiry_date: null, po_date: '2026-01-11' },
]);
assert.strictEqual(empty.days, null, 'a cycle nobody can compute came back as a number');
assert.strictEqual(DealCycle.text(empty), '—',
  'an unmeasurable cycle was shown as a figure');
assert.ok(DealCycle.note(empty).length > 0, 'nothing explained the empty cycle');
assert.strictEqual(DealCycle.measure([]).days, null);

// An enquiry answered with an order the same day is a real zero-day cycle,
// not a missing one.
const sameDay = DealCycle.measure([
  { sales_stage: 'Won', inquiry_date: '2026-04-01', po_date: '2026-04-01' },
]);
assert.strictEqual(sameDay.days, 0, 'a same-day order was not counted');
assert.strictEqual(sameDay.counted, 1, 'a same-day order was excluded as missing');
assert.notStrictEqual(DealCycle.text(sameDay), '—',
  'a real zero-day cycle was shown as "no data"');

// An order dated before its own enquiry is not a negative cycle.
const backwards = DealCycle.measure([
  { sales_stage: 'Won', inquiry_date: '2026-05-01', po_date: '2026-04-01' },
]);
assert.strictEqual(backwards.days, null, 'a PO before its enquiry was averaged in');
"""


def main() -> None:
    run(PAGING, "paged reads")
    run(MONEY, "money totals")
    run(GRADE, "quality grade")
    run(CYCLE, "deal cycle")
    print("PASS: whole lists, per-currency totals, real grades and a real cycle")


if __name__ == "__main__":
    main()
