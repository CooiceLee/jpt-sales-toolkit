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

    function compact(value) {
        const amount = Number(value) || 0;
        if (Math.abs(amount) >= 1000) {
            return `${Math.round(amount / 1000).toLocaleString()}K`;
        }
        return Math.round(amount).toLocaleString();
    }

    function label(code) {
        return code === UNSPECIFIED ? tr('no currency') : code;
    }

    // Largest first: with several currencies there is no single total, so the
    // reader is shown each one rather than one of them standing for all.
    //
    // A subtotal of zero is kept. Deals recorded at zero are a different fact
    // from no deals at all, and dropping the zero made the two read the same.
    function entries(byCurrency) {
        return Object.entries(byCurrency || {})
            .filter(([, value]) => Number.isFinite(Number(value)))
            .sort((left, right) => Math.abs(right[1]) - Math.abs(left[1]));
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

    window.MoneyTotals = Object.freeze({ text, missingNote, compact, entries });
})();
