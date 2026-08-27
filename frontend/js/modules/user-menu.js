// ===== User Menu =====
function initUserMenu() {
    const footer = document.getElementById('user-footer');
    if (!footer || footer.dataset.userMenuBound) return;
    footer.dataset.userMenuBound = '1';
    const menu = document.getElementById('user-menu');

    function setMenuOpen(open) {
        menu?.classList.toggle('show', open);
        footer.setAttribute('aria-expanded', String(open));
    }

    function toggleMenu() {
        setMenuOpen(!menu?.classList.contains('show'));
    }

    ApiClient.getRuntimeStatus()
        .then(status => {
            document.getElementById('desktop-exit')?.classList.toggle('hidden', !status.desktop);
            document.getElementById('install-location-warning')?.classList.toggle(
                'hidden', !status.running_from_disk_image
            );
            const version = document.getElementById('runtime-version');
            if (version) {
                // The server's version and the build the page's own scripts
                // came from are different facts. A tab left open across an
                // upgrade shows the new server and the old assets, which looks
                // exactly like a feature that was never fixed.
                const assets = version.dataset.assetBuild || '';
                const running = status.version || '—';
                const stale = assets && !assets.startsWith(running);
                version.textContent = `v${running}${stale ? ' ⚠' : ''}`;
                version.title = `${window.I18n?.t('Running version') || 'Running version'}: `
                    + `${running}\n${window.I18n?.t('Loaded assets') || 'Loaded assets'}: ${assets || '—'}`
                    + (stale ? `\n${window.I18n?.t('This page is out of date. Reload it.') || 'This page is out of date. Reload it.'}` : '');
            }
        })
        .catch(error => console.debug('Runtime status unavailable:', error));

    footer.addEventListener('click', (e) => {
        if (e.target.closest('.user-menu')) return;
        toggleMenu();
    });

    footer.addEventListener('keydown', (event) => {
        if (event.target.closest('.user-menu') && event.key !== 'Escape') return;
        if (event.key === 'Enter' || event.key === ' ') {
            event.preventDefault();
            toggleMenu();
        } else if (event.key === 'Escape') {
            setMenuOpen(false);
            footer.focus();
        }
    });

    document.addEventListener('click', (e) => {
        if (!e.target.closest('#user-footer')) {
            setMenuOpen(false);
        }
    });
}

window.switchAccount = function() {
    if (window.PanelDirtyState?.confirmDiscard && !window.PanelDirtyState.confirmDiscard()) return;
    ApiClient.clearAuth();
    State.user = null;
    document.getElementById('app').style.display = 'none';
    showModal('login-modal');
};

window.exitApplication = async function() {
    if (window.PanelDirtyState?.confirmDiscard && !window.PanelDirtyState.confirmDiscard()) return;
    if (!confirm(I18n.t('Exit JPT Sales Toolkit on this computer?'))) return;
    try {
        await ApiClient.shutdownDesktop();
        document.body.innerHTML = `<main class="desktop-exit-message"><h1>${
            I18n.t('JPT has stopped')
        }</h1><p>${I18n.t('You can close this window safely.')}</p></main>`;
    } catch (error) {
        alert(I18n.t('Unable to exit JPT: {error}', {
            error: I18n.t(error.message || 'Unknown error')
        }));
    }
};

window.logout = async function() {
    if (window.PanelDirtyState?.confirmDiscard && !window.PanelDirtyState.confirmDiscard()) return;
    if (!confirm(I18n.t('Are you sure you want to logout?'))) return;
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
