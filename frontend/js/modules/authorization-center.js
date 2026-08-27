(function() {
    const center = {
        status: null,
        members: [],
        events: [],
        editingMemberId: null,
        bound: false,
        loading: false
    };
    window.AuthorizationCenterState = center;

    function isLeader() {
        return State.user?.role === 'leader';
    }

    function setVisibility() {
        document.querySelectorAll('.authorization-leader-only').forEach(element => {
            element.classList.toggle('hidden', !isLeader());
        });
        if (!isLeader() && document.getElementById('module-authorization')?.classList.contains('active')) {
            switchModule('dashboard');
        }
    }

    function setCenterMessage(message, error = false) {
        const element = document.getElementById('authorization-center-message');
        if (!element) return;
        // Server messages arrive here as English text, so they are translated
        // like any other label rather than shown as they came.
        element.textContent = message ? I18n.t(message) : '';
        element.classList.toggle('error-state', error);
        element.style.display = message ? 'block' : 'none';
    }

    function bindMemberActions() {
        const table = document.getElementById('authorization-members');
        table?.addEventListener('click', event => {
            const button = event.target.closest('button[data-member-action]');
            if (!button) return;
            const memberId = button.dataset.memberId;
            const action = button.dataset.memberAction;
            if (action === 'edit') editAuthorizationMember(memberId);
            if (action === 'issue') selectAuthorizationMemberForIssue(memberId);
            if (action === 'deactivate') deactivateAuthorizationMember(memberId);
            if (action === 'reactivate') reactivateAuthorizationMember(memberId);
        });
    }

    window.initAuthorizationCenter = function() {
        setVisibility();
        if (center.bound) return;
        bindMemberActions();
        center.bound = true;
    };

    window.refreshAuthorizationCenter = async function(message = '') {
        if (!isLeader() || center.loading) return;
        center.loading = true;
        setCenterMessage(message || 'Loading authorization data...');
        try {
            const [rawStatus, rawMembers, rawEvents] = await Promise.all([
                ApiClient.getAuthorizationStatus(),
                ApiClient.listAuthorizationMembers(),
                ApiClient.listAuthorizationEvents()
            ]);
            center.status = AuthorizationModel.status(rawStatus);
            center.members = AuthorizationModel.members(rawMembers);
            center.events = AuthorizationModel.events(rawEvents);
            renderAuthorizationOverview(center.status, center.members);
            renderAuthorizationMembers(center.members);
            renderAuthorizationEvents(center.events, center.members);
            populateAuthorizationIssueMembers(center.members);
            setCenterMessage('');
        } catch (err) {
            console.error('Authorization center load error:', err);
            setCenterMessage(err.message || 'Unable to load authorization data.', true);
        } finally {
            center.loading = false;
        }
    };

    window.loadAuthorizationCenter = async function() {
        setVisibility();
        if (!isLeader()) return;
        await refreshAuthorizationCenter();
    };

    window.showAuthorizationCenterMessage = setCenterMessage;
})();
