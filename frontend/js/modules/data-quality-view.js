/** Human review workflow for imported lead fields. */
const DataQualityModule = (function() {
    let activeLeadId = null;
    let activeStatus = 'open';

    const tr = (text, params) => window.I18n?.t(text, params) || text;
    const root = () => document.getElementById('panel-content');
    const role = () => String(State.user?.role || '').toLowerCase();

    function actions(issue) {
        if (issue.status !== 'open') {
            return `<button type="button" class="btn btn-secondary btn-sm" data-quality-action="open"
                data-issue-id="${escapeHtml(issue.id)}">${escapeHtml(tr('Reopen'))}</button>`;
        }
        const ignore = role() === 'leader' ? `<button type="button" class="btn btn-text btn-sm"
            data-quality-action="ignored" data-issue-id="${escapeHtml(issue.id)}">${escapeHtml(tr('Ignore'))}</button>` : '';
        return `<button type="button" class="btn btn-primary btn-sm" data-quality-action="resolved"
            data-issue-id="${escapeHtml(issue.id)}">${escapeHtml(tr('Mark resolved'))}</button>${ignore}`;
    }

    function sourceDetails(issue) {
        let value = issue.raw_value || '';
        let ref = {};
        try {
            const parsed = JSON.parse(value);
            value = parsed.value ?? '';
            ref = parsed.source_ref || {};
        } catch { /* Older issues may contain a plain source value. */ }
        const row = ref.sheet && ref.row ? tr('{sheet} row {row}', { sheet: ref.sheet, row: ref.row }) : '';
        return { value, label: [issue.source_filename, row, issue.external_key].filter(Boolean).join(' · ') };
    }

    function issueCard(issue) {
        const source = sourceDetails(issue);
        const heading = issue.field_name ? formatLabel(issue.field_name) : (issue.issue_code || 'Imported field');
        return `<article class="quality-issue quality-${escapeHtml(issue.severity || 'warning')}">
            <div class="quality-issue-heading">
                <strong>${escapeHtml(tr(heading))}</strong>
                <span>${escapeHtml(tr(issue.severity || 'warning'))}</span>
            </div>
            <p>${escapeHtml(tr(issue.message || 'This imported value requires review.'))}</p>
            ${source.value ? `<div class="quality-raw">${escapeHtml(tr('Source value: {value}', { value: source.value }))}</div>` : ''}
            ${source.label ? `<small>${escapeHtml(source.label)}</small>` : ''}
            <div class="quality-actions">${actions(issue)}</div>
        </article>`;
    }

    function shell(items) {
        const filters = ['open', 'resolved', 'ignored'].map(status =>
            `<button type="button" class="btn btn-sm ${status === activeStatus ? 'btn-primary' : 'btn-secondary'}"
                data-quality-filter="${status}">${escapeHtml(tr(status[0].toUpperCase() + status.slice(1)))}</button>`
        ).join('');
        const content = items.length
            ? items.map(issueCard).join('')
            : `<div class="empty-state compact">${escapeHtml(tr('No data-quality items in this status.'))}</div>`;
        return `<section class="quality-review"><div class="quality-toolbar">${filters}</div>${content}</section>`;
    }

    function bind() {
        root()?.querySelectorAll('[data-quality-filter]').forEach(button => {
            button.addEventListener('click', () => render(activeLeadId, button.dataset.qualityFilter));
        });
        root()?.querySelectorAll('[data-quality-action]').forEach(button => {
            button.addEventListener('click', () => update(button.dataset.issueId, button.dataset.qualityAction));
        });
    }

    async function syncBadge() {
        const lead = await ApiClient.getLead(activeLeadId);
        if (State.currentInquiry?.id === activeLeadId) State.currentInquiry._lead = lead;
        WorklistUI.syncQualityCount(activeLeadId, lead.quality_issue_count);
    }

    async function update(issueId, status) {
        const label = status === 'open' ? 'Reason for reopening' : 'Resolution note';
        const note = window.prompt(`${tr(label)}:`);
        if (note === null) return;
        try {
            await ApiClient.updateDataQualityIssue(issueId, { status, resolution_note: note.trim() });
            await Promise.all([render(activeLeadId, activeStatus), syncBadge()]);
            notify(tr('Data-quality status updated'));
        } catch (error) {
            alert(error.message || tr('Unable to update this data-quality item.'));
        }
    }

    async function render(leadId, status = activeStatus) {
        activeLeadId = leadId;
        activeStatus = status;
        root().innerHTML = `<div class="loading-state">${escapeHtml(tr('Loading data-quality items...'))}</div>`;
        try {
            const result = await ApiClient.listDataQualityIssues({
                status, entity_type: 'leads', entity_id: leadId,
            });
            root().innerHTML = shell(result.items || []);
            bind();
        } catch (error) {
            root().innerHTML = `<div class="empty-state compact error-state">${escapeHtml(error.message)}</div>`;
        }
    }

    return { render };
})();
