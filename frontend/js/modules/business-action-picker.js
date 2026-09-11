/** Choose which lead an action is about, then do it there.
 *
 * "Create quote", "Log issue", "New pre-sales task" used to switch module and
 * ask the reader to find a card themselves - and the card lists they were sent
 * to were filtered to leads that already had that kind of record, so the first
 * quote, the first issue and the first task could not be started at all. The
 * picker searches the leads the reader may see, not the ones already carrying
 * the record being created.
 */
(function () {
    'use strict';

    const tr = (text, params) => window.I18n?.t(text, params) || text;
    let pending = null;

    function describe(lead) {
        return [
            lead.display_id,
            lead.customer?.display_name || lead.company_name,
            lead.title,
            lead.sales_stage,
        ].filter(Boolean).join(' · ');
    }

    function renderResults(leads) {
        const target = document.getElementById('action-picker-results');
        if (!target) return;
        if (!leads.length) {
            target.innerHTML = `<p class="empty-state compact">${escapeHtml(
                tr('No lead you can open matches that search.'))}</p>`;
            return;
        }
        target.innerHTML = `<ul class="action-picker-list">${leads.map((lead, index) => `
            <li>
                <button type="button" class="btn btn-secondary btn-sm" data-business
                    onclick="BusinessActionPicker.choose(${index})">
                    ${escapeHtml(describe(lead))}
                </button>
            </li>`).join('')}</ul>`;
    }

    async function search() {
        const term = String(document.getElementById('action-picker-search')?.value || '').trim();
        const status = document.getElementById('action-picker-status');
        if (status) status.textContent = tr('Searching…');
        try {
            const page = await ApiClient.listAllLeads(term ? { search: term } : {});
            pending.leads = page.items;
            renderResults(pending.leads);
            if (status) {
                status.textContent = [
                    tr('{count} leads', { count: pending.leads.length }),
                    PagedFetch.note(page),
                ].filter(Boolean).join(' · ');
            }
        } catch (error) {
            if (status) {
                status.textContent = tr('Could not search: {error}',
                    { error: error?.message || tr('Unknown error') });
            }
        }
    }

    // Opened with a lead already in hand, the picker steps aside: the reader
    // has said which one, and being asked again would be noise.
    async function open(action) {
        pending = { action, leads: [] };
        const current = State.currentInquiry?.id;
        if (current) return choose(null, current);
        document.getElementById('action-picker-title').textContent = tr(action.title);
        document.getElementById('action-picker-search').value = '';
        document.getElementById('action-picker-results').innerHTML = '';
        document.getElementById('action-picker-status').textContent = '';
        showModal('action-picker-modal');
        await search();
    }

    async function choose(index, leadId) {
        const id = leadId || pending?.leads?.[index]?.id;
        const action = pending?.action;
        if (!id || !action) return false;
        hideModal('action-picker-modal');
        // Only the panel can say whether the lead that was chosen is the one
        // now on screen. Treating "the request finished" as "my lead is open"
        // ran the form against whoever the reader had opened meanwhile.
        const opened = await openInquiryPanel(id, action.context);
        if (opened !== true || State.currentInquiry?.id !== id) return false;
        action.then?.();
        return true;
    }

    function close() {
        hideModal('action-picker-modal');
        pending = null;
    }

    window.BusinessActionPicker = Object.freeze({
        open, choose, search, close, describe,
    });
})();
