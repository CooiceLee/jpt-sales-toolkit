/** How long a won deal took, from the enquiry to the order.
 *
 * The figure on the card used to be the zero it was initialised with: nothing
 * ever computed it, so every reader saw "0d" and some of them believed it. An
 * average needs a start, an end and a stated sample - so this counts only the
 * won deals that carry both dates, and says how many that was.
 */
(function () {
    'use strict';

    const tr = (text, params) => window.I18n?.t(text, params) || text;
    const DAY = 24 * 60 * 60 * 1000;

    function day(value) {
        if (!value) return null;
        const parsed = Date.parse(String(value).slice(0, 10));
        return Number.isNaN(parsed) ? null : parsed;
    }

    // Start: the enquiry. End: the purchase order. Both are dates somebody
    // entered about the business, never the day a row was imported.
    function measure(leads) {
        const won = (leads || []).filter(lead => lead.sales_stage === 'Won');
        const spans = [];
        won.forEach(lead => {
            const start = day(lead.inquiry_date);
            const end = day(lead.po_date);
            if (start === null || end === null || end < start) return;
            spans.push(Math.round((end - start) / DAY));
        });
        if (!spans.length) {
            return { days: null, counted: 0, wonCount: won.length };
        }
        const total = spans.reduce((sum, value) => sum + value, 0);
        return {
            days: Math.round(total / spans.length),
            counted: spans.length,
            wonCount: won.length,
        };
    }

    function text(result) {
        return result.days === null ? '—' : tr('{count} days', { count: result.days });
    }

    function note(result) {
        if (!result.wonCount) return '';
        if (result.days === null) {
            return tr('No won deal has both an enquiry date and a PO date yet.');
        }
        return tr('From {counted} of {total} won deals with both dates.', {
            counted: result.counted,
            total: result.wonCount,
        });
    }

    window.DealCycle = Object.freeze({ measure, text, note });
})();
