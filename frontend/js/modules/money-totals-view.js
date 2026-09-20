/** Show a total in the currency it was actually agreed in.
 *
 * Amounts add up only within one currency. Four deals of 10,000 EUR were added
 * into one number and printed under a dollar sign, which is not a rounding
 * error: it is a figure nobody agreed to, standing where somebody decides
 * something. Nothing here converts anything - a conversion needs a rate, a
 * date and a source.
 */
(function () {
    'use strict';

    const tr = (text, params) => window.I18n?.t(text, params) || text;
    const UNSPECIFIED = 'UNSPECIFIED';

    // One unit per size. Everything above a thousand used to be printed in
    // thousands, so a total of 4.16 trillion came out as "4,164,615,261K":
    // eleven digits the reader has to count through to find out how big it is.
    const UNITS = [[1e12, 'T'], [1e9, 'B'], [1e6, 'M'], [1e3, 'K']];

    function compact(value) {
        const amount = Number(value) || 0;
        const unit = UNITS.find(([size]) => Math.abs(amount) >= size);
        if (!unit) return Math.round(amount).toLocaleString();
        const scaled = amount / unit[0];
        // Decimals only while they still say something: 4.16T is a different
        // number from 4.17T, 413M and 413.4M are the same number twice.
        const room = Math.abs(scaled) < 10 ? 2 : Math.abs(scaled) < 100 ? 1 : 0;
        return scaled.toLocaleString(undefined, {
            minimumFractionDigits: 0, maximumFractionDigits: room,
        }) + unit[1];
    }

    function label(code) {
        return code === UNSPECIFIED ? tr('no currency') : code;
    }

    // In a settled order, by currency code, with the amount nobody gave a
    // currency last.
    //
    // Sorted by size instead, the biggest *number* came first and a card gave
    // it the headline - so JPY 1,000,000 outranked EUR 100,000 and read as the
    // larger piece of business. Nothing here converts anything, so nothing here
    // can say which subtotal is the bigger one.
    //
    // A subtotal of zero is kept. Deals recorded at zero are a different fact
    // from no deals at all, and dropping the zero made the two read the same.
    function entries(byCurrency) {
        return Object.entries(byCurrency || {})
            .filter(([, value]) => Number.isFinite(Number(value)))
            .sort(([left], [right]) => {
                if (left === UNSPECIFIED) return 1;
                if (right === UNSPECIFIED) return -1;
                return left.localeCompare(right);
            });
    }

    function text(byCurrency, options = {}) {
        const rows = entries(byCurrency);
        if (!rows.length) return options.empty || '—';
        return rows
            .map(([code, value]) => `${label(code)} ${compact(value)}`)
            .join(' · ');
    }

    function missingNote(missing) {
        const count = Number(missing) || 0;
        if (!count) return '';
        return tr('{count} without an amount', { count });
    }

    // The same subtotals text() joins into a sentence, kept apart - so a card
    // can put the largest on its own line and the rest under it, rather than
    // running one string past its own width and wrapping mid-number.
    function rows(byCurrency) {
        return entries(byCurrency).map(([code, value]) => ({
            code: label(code), amount: compact(value),
        }));
    }

    window.MoneyTotals = Object.freeze({ text, missingNote, compact, entries, rows });
})();
