// ===== v0.7 Data Review =====
function applyReviewPeriod() {
    const period = document.getElementById('review-period')?.value || 'all';
    const fromInput = document.getElementById('review-date-from');
    const toInput = document.getElementById('review-date-to');
    const today = new Date();
    let from = '';
    let to = '';

    if (period === 'this_month') {
        from = toDateInput(new Date(today.getFullYear(), today.getMonth(), 1));
        to = toDateInput(today);
    } else if (period === 'last_month') {
        from = toDateInput(new Date(today.getFullYear(), today.getMonth() - 1, 1));
        to = toDateInput(new Date(today.getFullYear(), today.getMonth(), 0));
    } else if (period === 'this_quarter') {
        const quarterStartMonth = Math.floor(today.getMonth() / 3) * 3;
        from = toDateInput(new Date(today.getFullYear(), quarterStartMonth, 1));
        to = toDateInput(today);
    } else if (period === 'custom') {
        loadDataReview();
        return;
    }

    if (fromInput) fromInput.value = from;
    if (toInput) toInput.value = to;
    loadDataReview();
}

function getReviewFilters() {
    return {
        date_from: document.getElementById('review-date-from')?.value || '',
        date_to: document.getElementById('review-date-to')?.value || '',
        region: document.getElementById('review-region')?.value || '',
        sales_stage: document.getElementById('review-stage')?.value || ''
    };
}

window.loadDataReview = async function() {
    const tableIds = [
        'review-stage-table',
        'review-owner-table',
        'review-region-table',
        'review-risk-table',
        'review-value-table'
    ];
    try {
        setText('review-brief', 'Loading review data...');
        tableIds.forEach(id => setPanelLoading(id, 'Loading...'));
        const data = await ApiClient.getAnalysis(getReviewFilters());
        const summary = data.summary || {};

        setText('review-open', summary.open_leads || 0);
        setText('review-won', summary.won_leads || 0);
        setText('review-won-value', formatK(summary.won_value || 0));
        setText('review-win-rate', Math.round((summary.win_rate || 0) * 100));
        setText('review-overdue', summary.overdue_followups || 0);
        setText('review-brief', data.brief || '');

        renderReviewTable('review-stage-table', [
            ['Stage', 'stage'],
            ['Count', 'count'],
            ['Value', row => formatMoney(row.value)]
        ], data.stage_breakdown || []);

        renderReviewTable('review-owner-table', [
            ['Owner', 'label'],
            ['Open', 'open'],
            ['Won', 'won'],
            ['Win', row => `${Math.round((row.win_rate || 0) * 100)}%`],
            ['Pipeline', row => formatMoney(row.pipeline_value)]
        ], data.owner_breakdown || []);

        renderReviewTable('review-region-table', [
            ['Region', 'label'],
            ['Total', 'total'],
            ['Open', 'open'],
            ['Won Value', row => formatMoney(row.won_value)]
        ], data.region_breakdown || []);

        renderLeadReviewTable('review-risk-table', data.risk_leads || [], true);
        renderLeadReviewTable('review-value-table', data.high_value_open_leads || [], false);
    } catch (err) {
        console.error('Data review error:', err);
        setText('review-brief', 'Data review unavailable');
        tableIds.forEach(id => setPanelError(id, 'Unable to load data'));
    }
};

