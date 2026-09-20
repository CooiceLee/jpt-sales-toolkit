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

// The same numbers the server puts in its own English brief, said in the
// reader's language. Composed from the counts, never by translating a finished
// sentence backwards.
function reviewBrief(summary) {
    if (!summary || summary.total_leads === undefined) return '';
    const money = value => MoneyTotals.text(value, { empty: I18n.t('none recorded') });
    return [
        I18n.t('Reviewed {total} leads: {open} open, {won} won, {lost} lost.', {
            total: summary.total_leads || 0, open: summary.open_leads || 0,
            won: summary.won_leads || 0, lost: summary.lost_leads || 0,
        }),
        I18n.t('Pipeline {pipeline}. Won {wonValue}.', {
            pipeline: money(summary.pipeline_value_by_currency),
            wonValue: money(summary.won_value_by_currency),
        }),
        I18n.t('{overdue} with follow-ups overdue, {stale} open with no activity for 30+ days.', {
            overdue: summary.overdue_followups || 0,
            stale: summary.stale_open_leads || 0,
        }),
    ].join(' ');
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
        paintMoneyValue('review-won-value', summary.won_value_by_currency);
        setText('review-win-rate', Math.round((summary.win_rate || 0) * 100));
        setText('review-overdue', summary.overdue_followups || 0);
        // Written here rather than printed as the server sent it: the server
        // composes one English sentence, and a sentence assembled from words is
        // the one thing the screen walker must never try to translate back.
        setText('review-brief', reviewBrief(summary));

        renderReviewTable('review-stage-table', [
            // The stage is one of this product's own six words, so it is
            // translated like the funnel's labels - the two are read together.
            ['Stage', 'stage', 'interface'],
            ['Count', 'count'],
            ['Value', row => MoneyTotals.text(row.value_by_currency)]
        ], data.stage_breakdown || []);

        renderReviewTable('review-owner-table', [
            ['Owner', 'label'],
            ['Open', 'open'],
            ['Won', 'won'],
            ['Win', row => `${Math.round((row.win_rate || 0) * 100)}%`],
            ['Pipeline', row => MoneyTotals.text(row.pipeline_value_by_currency)]
        ], data.owner_breakdown || []);

        renderReviewTable('review-region-table', [
            ['Region', 'label'],
            ['Total', 'total'],
            ['Open', 'open'],
            ['Won Value', row => MoneyTotals.text(row.won_value_by_currency)]
        ], data.region_breakdown || []);

        renderLeadReviewTable('review-risk-table', data.risk_leads || [], true);
        renderLeadReviewTable('review-value-table', data.high_value_open_leads || [], false);
    } catch (err) {
        console.error('Data review error:', err);
        setText('review-brief', 'Data review unavailable');
        tableIds.forEach(id => setPanelError(id, 'Unable to load data'));
    }
};

