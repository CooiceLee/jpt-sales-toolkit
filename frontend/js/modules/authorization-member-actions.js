(function() {
    function memberForm() {
        return {
            username: document.getElementById('authorization-member-username')?.value.trim() || '',
            display_name: document.getElementById('authorization-member-name')?.value.trim() || '',
            role: document.getElementById('authorization-member-role')?.value || '',
            region: document.getElementById('authorization-member-region')?.value.trim() || null
        };
    }

    function setMemberForm(member = null) {
        AuthorizationCenterState.editingMemberId = member?.id || null;
        document.getElementById('authorization-member-username').value = member?.username || '';
        document.getElementById('authorization-member-name').value = member?.displayName || '';
        document.getElementById('authorization-member-role').value = member?.role || 'sales';
        document.getElementById('authorization-member-region').value = member?.region || '';
        setText('authorization-member-form-title', member ? 'Edit member' : 'Add member');
        setText('authorization-member-save-label', member ? 'Save changes' : 'Add member');
        document.getElementById('authorization-member-cancel')?.classList.toggle('hidden', !member);
    }

    function validMember(data) {
        if (!data.username || !data.display_name) {
            showAuthorizationCenterMessage('Username and display name are required.', true);
            return false;
        }
        if (!AuthorizationModel.ROLES.includes(data.role)) {
            showAuthorizationCenterMessage('Role must be Leader, Sales, or Tech.', true);
            return false;
        }
        return true;
    }

    window.saveAuthorizationMember = async function() {
        const data = memberForm();
        const button = document.getElementById('authorization-member-save');
        if (!validMember(data)) return;
        try {
            button.disabled = true;
            showAuthorizationCenterMessage('Saving member...');
            if (AuthorizationCenterState.editingMemberId) {
                await ApiClient.updateAuthorizationMember(AuthorizationCenterState.editingMemberId, data);
            } else {
                await ApiClient.createAuthorizationMember(data);
            }
            setMemberForm();
            await refreshAuthorizationCenter();
            notify('Member saved');
        } catch (err) {
            showAuthorizationCenterMessage(err.message || 'Unable to save member.', true);
        } finally {
            button.disabled = false;
        }
    };

    window.editAuthorizationMember = function(memberId) {
        const member = AuthorizationCenterState.members.find(item => String(item.id) === String(memberId));
        if (!member) return;
        setMemberForm(member);
        document.getElementById('authorization-member-form')?.scrollIntoView({ behavior: 'smooth', block: 'center' });
    };

    window.cancelAuthorizationMemberEdit = function() {
        setMemberForm();
        showAuthorizationCenterMessage('');
    };

    window.deactivateAuthorizationMember = async function(memberId) {
        const member = AuthorizationCenterState.members.find(item => String(item.id) === String(memberId));
        if (!member || !confirm(`Deactivate ${member.displayName}? Existing offline data will remain on their device.`)) return;
        try {
            showAuthorizationCenterMessage('Deactivating member...');
            await ApiClient.deactivateAuthorizationMember(member.id);
            if (String(AuthorizationCenterState.editingMemberId) === String(member.id)) setMemberForm();
            await refreshAuthorizationCenter();
            notify('Member deactivated');
        } catch (err) {
            showAuthorizationCenterMessage(err.message || 'Unable to deactivate member.', true);
        }
    };

    window.reactivateAuthorizationMember = async function(memberId) {
        try {
            showAuthorizationCenterMessage('Reactivating member...');
            await ApiClient.reactivateAuthorizationMember(memberId);
            await refreshAuthorizationCenter();
            notify('Member reactivated');
        } catch (err) {
            showAuthorizationCenterMessage(err.message || 'Unable to reactivate member.', true);
        }
    };

    window.selectAuthorizationMemberForIssue = function(memberId) {
        const select = document.getElementById('authorization-issue-member');
        select.value = memberId;
        document.getElementById('authorization-issue-panel')?.scrollIntoView({ behavior: 'smooth', block: 'center' });
    };
})();
