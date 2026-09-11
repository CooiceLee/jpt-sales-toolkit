/** The two queues that ask the same question the follow-up page asks.
 *
 * "Which of these do I open next?" - so they get the same shape: a narrow list
 * that answers it, the lead's own panel beside it, and a table for the reader
 * who wants to compare a column rather than read a row. What differs is what
 * each row says, and that comes from the queue's own fields, not from a shared
 * card layout that gave every page the same three blocks.
 */
(function () {
    'use strict';

    function build(key, type) {
        const shell = window.WorklistWorkbench.create(key);
        function render(items, emptyCopy) {
            const rows = window.WorklistRows;
            shell.draw({
                items,
                emptyCopy,
                listHtml: items.map(item => rows.row(item, type)).join(''),
                tableHtml: items.map(item => rows.tableRow(item, type)).join(''),
            });
        }
        return Object.freeze({ ...shell, render });
    }

    window.HandlerWorkbench = build('handler', 'handler');
    window.SamplingWorkbench = build('sampling', 'sampling');
    window.DealWorkbench = build('deal', 'deal');
    window.FulfillmentWorkbench = build('fulfillment', 'fulfillment');
    window.AftersalesWorkbench = build('aftersales', 'aftersales');
})();
