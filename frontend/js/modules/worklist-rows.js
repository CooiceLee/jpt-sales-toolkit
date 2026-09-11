/** One lead as a row, in the words the page it is on cares about.
 *
 * The card grid gave every queue the same three-column block whatever the
 * question was. A row is narrow, so what goes in it has to be chosen: who,
 * which lead, and the two or three facts this queue is actually sorted and
 * decided on. The rest stays in the panel, one click away.
 *
 * Selection is the production contract - [data-inquiry-card] with the lead's
 * id - so the panel, its drafts and its session identity are the real ones.
 */
(function () {
    'use strict';

    const tr = (text, params) => window.I18n?.t(text, params) || text;
    const h = value => escapeHtml(value ?? '');
    const dash = value => (value === null || value === undefined || value === ''
        ? tr('Not set') : value);

    function shortDate(value) {
        if (!value) return '';
        const date = new Date(String(value).length <= 10 ? `${value}T00:00:00` : value);
        if (Number.isNaN(date.getTime())) return String(value);
        return new Intl.DateTimeFormat(window.I18n?.locale?.() || 'en-US',
            { month: '2-digit', day: '2-digit' }).format(date);
    }

    // Per currency, never added up, and a zero is not a missing amount.
    function money(item) {
        const booked = !(item.deal_amount === null || item.deal_amount === undefined
            || item.deal_amount === '');
        const value = booked ? item.deal_amount : item.estimated_value;
        if (value === null || value === undefined || value === ''
            || !Number.isFinite(Number(value))) return tr('not quoted');
        const code = String(item.currency || '').trim().toUpperCase() || 'UNSPECIFIED';
        return `${tr(booked ? 'Deal' : 'Est.')} `
            + window.MoneyTotals.text({ [code]: Number(value) });
    }

    // What each queue is decided on. Two or three facts, in its own words.
    const FIELDS = Object.freeze({
        handler: item => [
            ['stage', tr(item.stage || 'New')],
            ['date', shortDate(item.inquiry_date || item.created_at)],
            ['note', dash(item.product_category)],
            ['money', money(item)],
        ],
        sampling: item => [
            ['stage', tr(item.sample_status || 'Not provided')],
            ['date', item.sample_due_date ? shortDate(item.sample_due_date) : tr('Not set')],
            ['note', dash(item.pre_sales_owner)],
            ['money', dash(item.sample_progress)],
        ],
        deal: item => [
            ['stage', tr(item.stage || 'Quoted')],
            ['date', item.po_date ? shortDate(item.po_date) : tr('Not set')],
            ['note', dash(item.quotation_id)],
            ['money', money(item)],
        ],
        // "Expected delivery" is not a field this database has - it only
        // survives in the extra fields of an import - so the row says the PO
        // date, which is the date this page actually holds.
        fulfillment: item => [
            ['stage', tr(item.fulfillment_status || 'Not Started')],
            ['date', item.po_date ? shortDate(item.po_date) : tr('Not set')],
            ['note', dash(item.po_number)],
            ['money', money(item)],
        ],
        aftersales: item => [
            ['stage', tr(item.service_status || 'None')],
            ['date', tr('{count} issues', { count: item.after_sales_count || 0 })],
            ['note', dash(item.po_number)],
            ['money', dash(item.owner_name)],
        ],
    });

    // What the two lines under the customer are called on this page.
    const LABELS = Object.freeze({
        handler: ['Current Stage', 'Product'],
        sampling: ['Task status', 'Current progress'],
        deal: ['Current Stage', 'Quotation'],
        fulfillment: ['Status', 'PO'],
        aftersales: ['Service status', 'PO'],
    });

    const HEADS = Object.freeze({
        handler: ['Customer', 'Lead', 'Current Stage', 'Inquiry date', 'Product', 'Amount'],
        sampling: ['Customer', 'Lead', 'Task status', 'Due', 'Pre-sales', 'Current progress'],
        deal: ['Customer', 'Lead', 'Current Stage', 'PO date', 'Quotation', 'Amount'],
        fulfillment: ['Customer', 'Lead', 'Status', 'PO date', 'PO', 'Amount'],
        aftersales: ['Customer', 'Lead', 'Service status', 'Issues', 'PO', 'Owner'],
    });

    function stageDot(stage) {
        const known = { New: 'other', Following: 'following', Quoted: 'quoted' };
        return known[stage] || 'other';
    }

    function row(item, type) {
        const fields = (FIELDS[type] || FIELDS.handler)(item);
        const value = key => (fields.find(entry => entry[0] === key) || [])[1] || '';
        const labels = LABELS[type] || LABELS.handler;
        const grade = item.quality_rating;
        return `
            <article class="wb-row" data-inquiry-card tabindex="0"
                data-inquiry-id="${h(item.id)}" data-card-context="${h(type)}"
                role="button" aria-pressed="false"
                aria-label="${h(tr('Open lead {id} for {company}', {
                    id: item.inquiry_id || item.id,
                    company: item.company_name || tr('Unknown Company'),
                }))}">
                <div class="wb-main">
                    <span class="wb-dot wb-dot-${stageDot(item.stage)}" aria-hidden="true"></span>
                    <b class="wb-company" data-business>${h(item.company_name || tr('Unknown Company'))}</b>
                    <span class="wb-id" data-business>${h(item.inquiry_id || '')}</span>
                    ${grade ? `<span class="grade-badge grade-${h(String(grade).toLowerCase())}"
                        title="${h(tr('Lead quality grade'))}">${h(grade)}</span>` : ''}
                    <div class="wb-amount"><b data-business>${h(value('money'))}</b></div>
                </div>
                <div class="wb-next"><span class="wb-lead">${h(tr(labels[0]))}</span>
                    <b data-business>${h(value('stage'))}</b>
                    <span class="wb-text" data-business>${h(value('date'))}</span></div>
                <div class="wb-last"><span class="wb-lead">${h(tr(labels[1]))}</span>
                    <span class="wb-text" data-business>${h(value('note'))}</span></div>
            </article>`;
    }

    function tableRow(item, type) {
        const fields = (FIELDS[type] || FIELDS.handler)(item);
        const cells = fields.map(([key, content]) =>
            `<td class="wb-cell-${key}" data-business>${h(content)}</td>`).join('');
        return `
            <tr data-inquiry-card tabindex="0" data-inquiry-id="${h(item.id)}"
                data-card-context="${h(type)}" role="button" aria-pressed="false">
                <td class="wb-cell-name" data-business>${h(item.company_name || tr('Unknown Company'))}</td>
                <td class="wb-cell-id" data-business>${h(item.inquiry_id || '')}</td>
                ${cells}
            </tr>`;
    }

    function head(type) {
        return (HEADS[type] || HEADS.handler)
            .map(label => `<th>${h(tr(label))}</th>`).join('');
    }

    window.WorklistRows = Object.freeze({ row, tableRow, head, money, shortDate });
})();
