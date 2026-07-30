/** Recipient-scoped JSON package export for terminal data distribution. */
(function () {
    'use strict';
    const tr = text => window.I18n?.t(text) || text;
    let recipientsLoaded = false;

    async function ensureRecipients() {
        const field = document.getElementById('json-export-recipient-field');
        const select = document.getElementById('json-export-recipient');
        if (!field || !select) return;
        const isLeader = State.user?.role === 'leader';
        field.hidden = !isLeader;
        if (!isLeader || recipientsLoaded) return;
        try {
            const members = await ApiClient.listUsers('sales');
            select.innerHTML =
                `<option value="">${escapeHtml(tr('Select recipient salesperson'))}</option>` +
                (members || []).map(member =>
                    `<option value="${escapeHtml(member.id)}">` +
                    `${escapeHtml(member.display_name)}</option>`
                ).join('');
            recipientsLoaded = true;
        } catch (error) {
            select.innerHTML =
                `<option value="">${escapeHtml(tr('Unable to load recipients'))}</option>`;
        }
    }

    window.exportData = async function () {
        const recipient = State.user?.role === 'leader'
            ? document.getElementById('json-export-recipient')?.value
            : null;
        if (State.user?.role === 'leader' && !recipient) {
            alert(tr('Please select a recipient salesperson'));
            return;
        }
        try {
            const { blob, filename } = await ApiClient.exportData(null, recipient);
            const url = URL.createObjectURL(blob);
            const link = document.createElement('a');
            link.href = url;
            link.download = filename;
            document.body.appendChild(link);
            link.click();
            link.remove();
            URL.revokeObjectURL(url);
            const result = document.getElementById('export-result');
            result.style.display = 'block';
            result.className = 'wizard-inline-result success';
            result.textContent = `✓ ${tr('Export successful!')} ${filename}`;
        } catch (error) {
            alert(`${tr('Export failed')}: ${error.message || tr('Unknown error')}`);
        }
    };

    window.JsonExport = { ensureRecipients };
})();
