// ===== User Menu =====
function initUserMenu() {
    const footer = document.getElementById('user-footer');
    if (!footer) return;

    ApiClient.getRuntimeStatus()
        .then(status => document.getElementById('desktop-exit')?.classList.toggle('hidden', !status.desktop))
        .catch(error => console.debug('Runtime status unavailable:', error));

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

window.exitApplication = async function() {
    if (!confirm('Exit JPT Sales Toolkit on this computer?')) return;
    try {
        await ApiClient.shutdownDesktop();
        document.body.innerHTML = '<main class="desktop-exit-message"><h1>JPT has stopped</h1><p>You can close this window safely.</p></main>';
    } catch (error) {
        alert(error.message || 'Unable to exit JPT.');
    }
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
        leader: 'Leader',
        sales: 'Sales',
        tech: 'Tech'
    };
    setText('user-role', roleLabels[State.user.role] || State.user.role || 'Sales');
}
