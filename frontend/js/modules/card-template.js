(function () {
    'use strict';

    const tr = (text, params) => window.I18n?.t(text, params) || text;
    const money = item => item.deal_amount
        ? `${escapeHtml(item.currency || 'USD')} ${Number(item.deal_amount).toLocaleString()}`
        : '-';
    const value = input => escapeHtml(input || '-');
    const enumValue = input => escapeHtml(tr(input || 'Not provided'));
    const dateValue = input => input ? escapeHtml(formatDate(input)) : '-';
    const activityAgeValue = item => {
        if (!Number.isFinite(item.activity_age_days)) return '-';
        const templates = {
            follow_up: '{count} days inactive',
            inquiry: '{count} days since inquiry (no formal follow-up)',
            created: '{count} days since creation (no formal follow-up)',
        };
        return escapeHtml(tr(templates[item.activity_date_source] || '{count} days inactive', {
            count: item.activity_age_days,
        }));
    };

    function renderDetails(item, type) {
        const rows = {
            handler: [
                ['Product', value(item.product_category)],
                ['Amount', money(item)],
            ],
            followup: [
                ['Follow-ups', item.follow_ups_count || 0],
                ['Latest follow-up', item.latest_follow_up_at
                    ? dateValue(item.latest_follow_up_at)
                    : escapeHtml(tr('No formal follow-up'))],
                ['Inactive for', activityAgeValue(item)],
                ['Next follow-up', dateValue(item.next_followup_date)],
            ],
            sampling: [
                ['Task status', enumValue(item.sample_status)],
                ['Pre-sales', value(item.pre_sales_owner)],
                ['Current progress', value(item.sample_progress)],
                ['Latest follow-up', item.latest_follow_up_at_raw
                    ? value(item.latest_follow_up_at_raw)
                    : dateValue(item.latest_follow_up_at)],
                ['Follow-up content', value(item.latest_follow_up_summary)],
                ['Due', dateValue(item.sample_due_date)],
            ],
            deal: [
                ['Quotation', value(item.quotation_id)],
                ['PO', value(item.po_number)],
                ['Close note', item.stage === 'Lost' ? value(item.lost_reason_text) : '-'],
                ['Amount', money(item)],
            ],
            fulfillment: [
                ['Status', value(item.fulfillment_status || 'Not Started')],
                ['Expected', dateValue(item.expected_delivery)],
            ],
            aftersales: [
                ['Issues', item.after_sales_count || 0],
                ['PO', value(item.po_number)],
            ],
        };
        const details = rows[type] || rows.handler;
        return `<div class="card-details">${details.map(([label, content]) => `
            <span class="card-label">${escapeHtml(tr(label))}</span>
            <span class="card-value" title="${String(content).replace(/<[^>]+>/g, '')}">${content}</span>
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
                          title="${escapeHtml(tr('Imported fields requiring review'))}">${escapeHtml(tr('{count} to review', {
                              count: Number(item.quality_issue_count) || 0
                          }))}</span>
                    <div class="grade-badge grade-${gradeClass}">${escapeHtml(grade)}</div>
                </div>
                <div class="card-company">${value(item.company_name || tr('Unknown Company'))}</div>
                <div class="card-contact">
                    <span>${escapeHtml(item.contact_name || '')}</span>
                    <span>${escapeHtml(item.country || '')}</span>
                </div>
                ${renderDetails(item, type)}
                <div class="card-footer">
                    <span class="stage-badge stage-${stageClass}">${escapeHtml(tr(stage))}</span>
                    <div class="progress-dots">${progress}</div>
                </div>
            </div>
        `;
    }

    window.renderInquiryCard = renderCard;
})();
