(function() {
    function dateLabel(value) {
        return value ? formatDate(value) : '-';
    }

    function timestampLabel(value) {
        if (!value) return '-';
        try { return new Date(value).toLocaleString(); } catch { return value; }
    }

    window.renderAuthorizationOverview = function(status, members) {
        const activeMembers = members.filter(member => member.active).length;
        const boundMembers = members.filter(member => member.activeDevice).length;
        const modeLabels = {
            offline: 'Offline signed packages',
            legacy: 'Legacy migration mode',
            remote: 'Remote authorization',
            setup: 'First-run setup'
        };
        setText('authorization-mode', modeLabels[status.mode] || status.mode);
        setText('authorization-member-count', activeMembers);
        setText('authorization-device-count', boundMembers);
        setText('authorization-current-device', status.deviceId || '-');
        setText('authorization-fingerprint', status.issuer.fingerprint || 'Not initialized');
        setText('authorization-trusted-fingerprint', status.issuer.fingerprint || 'Unknown');

        document.getElementById('authorization-issuer-setup')?.classList.toggle('hidden', !status.issuer.canInitialize);
        document.getElementById('authorization-issuer-ready')?.classList.toggle('hidden', !status.issuer.initialized);
        document.getElementById('authorization-issuer-unavailable')?.classList.toggle(
            'hidden', status.issuer.initialized || !status.issuer.trusted
        );
        const issueButton = document.getElementById('authorization-issue-btn');
        if (issueButton) issueButton.disabled = !status.issuer.initialized;
    };

    window.renderAuthorizationMembers = function(members) {
        const container = document.getElementById('authorization-members');
        if (!container) return;
        if (!members.length) {
            container.innerHTML = '<div class="empty-state compact">No team members yet.</div>';
            return;
        }
        container.innerHTML = `
            <div class="authorization-table-wrap">
                <table class="data-table compact-table">
                    <thead><tr><th>Member</th><th>Role</th><th>Region</th><th>Device</th><th>Expiry</th><th>Status</th><th>Actions</th></tr></thead>
                    <tbody>${members.map(member => `
                        <tr>
                            <td><strong>${escapeHtml(member.displayName)}</strong><small>${escapeHtml(member.username)}</small></td>
                            <td>${escapeHtml(AuthorizationModel.ROLE_LABELS[member.role])}</td>
                            <td>${escapeHtml(member.region || '-')}</td>
                            <td>${escapeHtml(AuthorizationModel.deviceLabel(member.activeDevice))}</td>
                            <td>${escapeHtml(dateLabel(member.expiresAt))}</td>
                            <td><span class="authorization-status ${member.active ? 'active' : 'inactive'}">${member.active ? 'Active' : 'Inactive'}</span></td>
                            <td><div class="authorization-row-actions">
                                <button type="button" class="text-link" data-member-action="edit" data-member-id="${escapeHtml(member.id)}">Edit</button>
                                ${member.active ? `<button type="button" class="text-link" data-member-action="issue" data-member-id="${escapeHtml(member.id)}">Issue</button>` : ''}
                                <button type="button" class="table-mini-link" data-member-action="${member.active ? 'deactivate' : 'reactivate'}" data-member-id="${escapeHtml(member.id)}">${member.active ? 'Deactivate' : 'Reactivate'}</button>
                            </div></td>
                        </tr>
                    `).join('')}</tbody>
                </table>
            </div>`;
    };

    window.renderAuthorizationEvents = function(events, members = []) {
        const container = document.getElementById('authorization-events');
        if (!container) return;
        if (!events.length) {
            container.innerHTML = '<div class="empty-state compact">No authorization events yet.</div>';
            return;
        }
        const names = new Map(members.map(member => [String(member.id), member.displayName]));
        container.innerHTML = `
            <div class="authorization-table-wrap">
                <table class="data-table compact-table">
                    <thead><tr><th>Time</th><th>Event</th><th>Member</th><th>Device</th><th>Details</th></tr></thead>
                    <tbody>${events.slice(0, 100).map(event => `
                        <tr>
                            <td>${escapeHtml(timestampLabel(event.createdAt))}</td>
                            <td>${escapeHtml(formatLabel(event.type))}</td>
                            <td>${escapeHtml(names.get(String(event.userId)) || event.userId || event.actorId || '-')}</td>
                            <td>${escapeHtml(event.deviceId || '-')}</td>
                            <td>${escapeHtml(AuthorizationModel.detailLabel(event.details))}</td>
                        </tr>
                    `).join('')}</tbody>
                </table>
            </div>`;
    };

    window.populateAuthorizationIssueMembers = function(members) {
        const select = document.getElementById('authorization-issue-member');
        if (!select) return;
        const previous = select.value;
        const activeMembers = members.filter(member => member.active);
        select.innerHTML = '<option value="">Select member</option>' + activeMembers.map(member =>
            `<option value="${escapeHtml(member.id)}">${escapeHtml(member.displayName)} · ${escapeHtml(AuthorizationModel.ROLE_LABELS[member.role])}</option>`
        ).join('');
        if (activeMembers.some(member => String(member.id) === previous)) select.value = previous;
    };
})();
