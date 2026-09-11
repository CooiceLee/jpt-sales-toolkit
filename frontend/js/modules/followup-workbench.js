/** The follow-up list as a selector beside the lead it opened.
 *
 * The cards grid gave every lead the same weight and the same space, so the
 * work - reading one lead's history and writing the next step - happened in a
 * panel squeezed against the edge. Here the list answers one question ("which
 * one?") in a narrow column, and the lead's own panel gets the rest of the
 * width. Nothing about the data, the requests or who may see what changes;
 * selection still goes through the same [data-inquiry-card] contract, so the
 * panel, the drafts and the session identity are the production ones.
 */
(function () {
    'use strict';

    const tr = (text, params) => window.I18n?.t(text, params) || text;
    const h = value => escapeHtml(value ?? '');
    // The shape - which view, how dense, where the panel starts, what an empty
    // list says - is the same on every queue that uses it, so it is one module.
    // What is only true here is the grouping by when a lead is due.
    const shell = window.WorklistWorkbench.create('followup');

    function render(items, emptyCopy, options = {}) {
        const list = document.getElementById('followup-cards');
        if (!list) return;
        // Nothing to show, or the request failed: said once, above both views.
        // Written into the list only, it was invisible in the table - which is
        // where the reader would have been when the filter emptied.
        if (!items.length) return shell.drawEmpty(emptyCopy);
        const { BUCKETS, bucketOf, row, tableRow } = window.FollowupRows;
        const now = new Date();
        const grouped = new Map(BUCKETS.map(bucket => [bucket.key, []]));
        items.forEach(item => grouped.get(bucketOf(item, now)).push(item));
        // The order the list was handed keeps deciding: groups appear in the
        // order their first lead does, and inside a group the order is the one
        // WorklistSort produced. Fixing the group order instead would quietly
        // overrule the activity-time sort the filters promise.
        const order = [];
        items.forEach(item => {
            const key = bucketOf(item, now);
            if (!order.includes(key)) order.push(key);
        });
        // Due-date groups only where they agree with the sort. Ask "who has
        // gone quiet longest" and the order of the list *is* the answer:
        // grouping by due date moved the fourth-stalest lead up past the
        // second (measured D,B,G,C,E -> D,G,B,C,E) and put "overdue" last.
        // In that mode the list keeps the sort's own order under one heading
        // that says what the order means.
        const listHtml = options.groupByDueDate === false
            ? `<div class="wb-group"><span>${h(tr('Longest without activity first'))}</span>
                    <em>${items.length}</em></div>
                ${items.map(row).join('')}`
            : order
                .map(key => BUCKETS.find(bucket => bucket.key === key))
                .map(bucket => `
                <div class="wb-group"><span>${h(tr(bucket.label))}</span>
                    <em>${grouped.get(bucket.key).length}</em></div>
                ${grouped.get(bucket.key).map(row).join('')}`).join('');
        shell.draw({ items, emptyCopy, listHtml,
                     tableHtml: items.map(tableRow).join('') });
    }

    window.FollowupWorkbench = Object.freeze({ ...shell, render });
})();
