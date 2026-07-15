/** Human review workflow for imported lead fields. */
const DataQualityModule = (function() {
    let activeLeadId = null;
    let activeStatus = 'open';

    const root = () => document.getElementById('panel-content');
    const role = () => String(State.user?.role || '').toLowerCase();

    function actions(issue) {
        if (issue.status !== 'open') {
            return `<button type="button" class="btn btn-secondary btn-sm" data-quality-action="open"
                data-issue-id="${escapeHtml(issue.id)}">Reopen</button>`;
        }
        const ignore = role() === 'leader' ? `<button type="button" class="btn btn-text btn-sm"
            data-quality-action="ignored" data-issue-id="${escapeHtml(issue.id)}">Ignore</button>` : '';
        return `<button type="button" class="btn btn-primary btn-sm" data-quality-action="resolved"
            data-issue-id="${escapeHtml(issue.id)}">Mark resolved</button>${ignore}`;
    }

    function sourceDetails(issue) {
        let value = issue.raw_value || '';
        let ref = {};
        try {
            const parsed = JSON.parse(value);
            value = parsed.value ?? '';
            ref = parsed.source_ref || {};
        } catch { /* Older issues may contain a plain source value. */ }
        const row = ref.sheet && ref.row ? `${ref.sheet} row ${ref.row}` : '';
        return { value, label: [issue.source_filename, row, issue.external_key].filter(Boolean).join(' · ') };
    }

    function issueCard(issue) {
        const source = sourceDetails(issue);
        return `<article class="quality-issue quality-${escapeHtml(issue.severity || 'warning')}">
            <div class="quality-issue-heading">
                <strong>${escapeHtml(issue.field_name || issue.issue_code || 'Imported field')}</strong>
                <span>${escapeHtml(issue.severity || 'warning')}</span>
            </div>
            <p>${escapeHtml(issue.message || 'This imported value requires review.')}</p>
            ${source.value ? `<div class="quality-raw">Source value: ${escapeHtml(source.value)}</div>` : ''}
            ${source.label ? `<small>${escapeHtml(source.label)}</small>` : ''}
            <div class="quality-actions">${actions(issue)}</div>
        </article>`;
    }

    function shell(items) {
        const filters = ['open', 'resolved', 'ignored'].map(status =>
            `<button type="button" class="btn btn-sm ${status === activeStatus ? 'btn-primary' : 'btn-secondary'}"
                data-quality-filter="${status}">${status[0].toUpperCase() + status.slice(1)}</button>`
        ).join('');
        const content = items.length
            ? items.map(issueCard).join('')
            : '<div class="empty-state compact">No data-quality items in this status.</div>';
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
        document.querySelectorAll(`[data-inquiry-id="${CSS.escape(activeLeadId)}"] .quality-badge`).forEach(badge => {
            const count = Number(lead.quality_issue_count) || 0;
            badge.textContent = `${count} to review`;
            badge.classList.toggle('hidden', count === 0);
        });
    }

    async function update(issueId, status) {
        const label = status === 'open' ? 'Reason for reopening' : 'Resolution note';
        const note = window.prompt(`${label}:`);
        if (note === null) return;
        try {
            await ApiClient.updateDataQualityIssue(issueId, { status, resolution_note: note.trim() });
            await Promise.all([render(activeLeadId, activeStatus), syncBadge()]);
            notify('Data-quality status updated');
        } catch (error) {
            alert(error.message || 'Unable to update this data-quality item.');
        }
    }

    async function render(leadId, status = activeStatus) {
        activeLeadId = leadId;
        activeStatus = status;
        root().innerHTML = '<div class="loading-state">Loading data-quality items...</div>';
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
