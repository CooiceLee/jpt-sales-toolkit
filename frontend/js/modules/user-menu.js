// ===== User Menu =====
function initUserMenu() {
    const footer = document.getElementById('user-footer');
    if (!footer) return;

    footer.addEventListener('click', (e) => {
        if (e.target.closest('.user-menu')) return;
        document.getElementById('user-menu').classList.toggle('show');
    });

    document.addEventListener('click', (e) => {
        if (!e.target.closest('#user-footer')) {
            document.getElementById('user-menu')?.classList.remove('show');
        }
    });
}

window.switchAccount = function() {
    ApiClient.clearAuth();
    State.user = null;
    document.getElementById('app').style.display = 'none';
    showModal('login-modal');
};

window.logout = async function() {
    if (!confirm('Are you sure you want to logout?')) return;
    try {
        await ApiClient.logout();
        State.user = null;
        document.getElementById('app').style.display = 'none';
        showModal('login-modal');
    } catch (err) {
        console.error('Logout error:', err);
        // Still clear auth and show login on error
        ApiClient.clearAuth();
        State.user = null;
        document.getElementById('app').style.display = 'none';
        showModal('login-modal');
    }
};

function updateUserDisplay() {
    if (!State.user) return;

    // Support both old (user_name) and new (display_name) format
    const displayName = State.user.display_name || State.user.user_name || 'User';
    setText('user-avatar', displayName.charAt(0).toUpperCase());
    setText('user-name', displayName);

    const roleLabels = {
        leader: 'Sales Leader',
        sales: 'Sales',
        assistant: 'Assistant',
        tech: 'Technical',
        pre_sales: 'Pre-sales',
        after_sales: 'After-sales'
    };
    setText('user-role', roleLabels[State.user.role] || State.user.role || 'Sales');
}

