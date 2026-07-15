(function () {
    'use strict';

    const money = item => item.deal_amount
        ? `${escapeHtml(item.currency || 'USD')} ${Number(item.deal_amount).toLocaleString()}`
        : '-';
    const value = input => escapeHtml(input || '-');

    function renderDetails(item, type) {
        const rows = {
            handler: [
                ['Product', value(item.product_category)],
                ['Amount', money(item)],
            ],
            followup: [
                ['Follow-ups', item.follow_ups_count || 0],
                ['Next action', item.next_followup_date ? formatDate(item.next_followup_date) : '-'],
            ],
            sampling: [
                ['Task status', value(item.sample_status || 'Not Requested')],
                ['Pre-sales', value(item.pre_sales_owner)],
                ['Due', item.sample_due_date ? formatDate(item.sample_due_date) : '-'],
            ],
            deal: [
                ['Quotation', value(item.quotation_id)],
                ['PO', value(item.po_number)],
                ['Close note', item.stage === 'Lost' ? value(item.lost_reason_text) : '-'],
                ['Amount', money(item)],
            ],
            fulfillment: [
                ['Status', value(item.fulfillment_status || 'Not Started')],
                ['Expected', item.expected_delivery ? formatDate(item.expected_delivery) : '-'],
            ],
            aftersales: [
                ['Issues', item.after_sales_count || 0],
                ['PO', value(item.po_number)],
            ],
        };
        const details = rows[type] || rows.handler;
        return `<div class="card-details">${details.map(([label, content]) => `
            <span class="card-label">${label}</span>
            <span class="card-value">${content}</span>
        `).join('')}</div>`;
    }

    function renderCard(item, type) {
        const stage = item.stage || 'Inquiry';
        const stageClass = stage.toLowerCase().replace(/\s+/g, '-').replace(/[^a-z-]/g, '');
        const grade = item.quality_rating || 'C';
        const gradeClass = String(grade).toLowerCase().replace(/[^a-z0-9-]/g, '');
        const cardClasses = ['inquiry-card'];
        if (stage === 'Lost') cardClasses.push('is-lost');
        const stageIndex = ['New', 'Assigned', 'Following', 'Quoted', 'Won'].indexOf(stage);
        const progress = [0, 1, 2, 3, 4]
            .map(index => `<div class="progress-dot ${index <= stageIndex ? 'filled' : ''}"></div>`)
            .join('');

        return `
            <div class="${cardClasses.join(' ')}" data-inquiry-card
                 data-inquiry-id="${escapeHtml(item.id)}" data-card-context="${escapeHtml(type)}">
                <div class="card-header">
                    <div class="card-meta">
                        <span>${value(item.inquiry_id)}</span>
                        <span>${escapeHtml(formatDate(item.inquiry_date || item.created_at))}</span>
                    </div>
                    <span class="quality-badge ${item.quality_issue_count ? '' : 'hidden'}"
                          title="Imported fields requiring review">${Number(item.quality_issue_count) || 0} to review</span>
                    <div class="grade-badge grade-${gradeClass}">${escapeHtml(grade)}</div>
                </div>
                <div class="card-company">${value(item.company_name || 'Unknown Company')}</div>
                <div class="card-contact">
                    <span>${escapeHtml(item.contact_name || '')}</span>
                    <span>${escapeHtml(item.country || '')}</span>
                </div>
                ${renderDetails(item, type)}
                <div class="card-footer">
                    <span class="stage-badge stage-${stageClass}">${escapeHtml(stage)}</span>
                    <div class="progress-dots">${progress}</div>
                </div>
            </div>
        `;
    }

    window.renderInquiryCard = renderCard;
})();
