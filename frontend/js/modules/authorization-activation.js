(function() {
    let activationStatus = null;
    let joiningFromSetup = false;

    function setActivationMessage(message, error = false, params = {}) {
        const element = document.getElementById('activation-message');
        if (!element) return;
        element.textContent = message ? I18n.t(message, params) : '';
        element.classList.toggle('error-state', error);
        element.style.display = message ? 'block' : 'none';
    }

    function renderStatus(status) {
        const setupMode = status.mode === 'setup';
        setText('activation-modal-title', I18n.t(
            setupMode ? 'Set Up JPT Sales Toolkit' : 'Activate JPT Sales Toolkit'
        ));
        document.getElementById('activation-bootstrap-section')?.classList.toggle(
            'hidden', !setupMode || joiningFromSetup
        );
        document.getElementById('activation-member-section')?.classList.toggle(
            'hidden', setupMode && !joiningFromSetup
        );
        document.getElementById('activation-back-to-setup')?.classList.toggle(
            'hidden', !setupMode || !joiningFromSetup
        );
        document.getElementById('activation-leader-recovery')?.classList.toggle(
            'hidden', setupMode || !status.issuer.initialized || status.activated
        );
        setText('activation-device-id', status.deviceId || 'Generated on request');
        const member = status.member;
        setText('activation-member', member
            ? `${member.display_name || member.username || 'Member'} · ${AuthorizationModel.ROLE_LABELS[member.role] || member.role}`
            : 'No authorization imported');
    }

    window.AuthorizationActivation = {
        status() { return activationStatus; },
        message: setActivationMessage,
        setStatus(rawStatus) {
            activationStatus = AuthorizationModel.status(rawStatus);
            renderStatus(activationStatus);
            return activationStatus;
        },
        chooseMemberActivation(enabled) {
            joiningFromSetup = enabled;
            renderStatus(activationStatus);
        },
        complete(username) {
            hideModal('activation-modal');
            setActivationMessage('');
            if (username) document.getElementById('login-username').value = username;
            showModal('login-modal');
            document.getElementById('login-password')?.focus();
        }
    };

    // Nothing on this screen can help, so nothing on it is offered.
    function blockStartup(title, message, params = {}) {
        ApiClient.clearAuth();
        document.getElementById('app').style.display = 'none';
        hideModal('login-modal');
        ['activation-bootstrap-section', 'activation-member-section', 'activation-back-to-setup',
            'activation-leader-recovery'].forEach(id => document.getElementById(id)?.classList.add('hidden'));
        setText('activation-modal-title', I18n.t(title));
        setActivationMessage(message, true, params);
        showModal('activation-modal');
        return false;
    }

    window.initAuthorizationActivation = async function() {
        try {
            AuthorizationActivation.setStatus(await ApiClient.getAuthorizationStatus());
        } catch (err) {
            console.error('Authorization status unavailable; login remains blocked.', err);
            activationStatus = null;
            return blockStartup(
                'Authorization Check Failed',
                'Unable to verify authorization status. Restart JPT and try again.'
            );
        }
        // The machine itself could not be identified. An activation file would
        // not change that, and a password box would refuse every password
        // without saying why, so this is said here instead.
        if (AuthorizationModel.unidentified(activationStatus)) {
            setText('activation-device-id', I18n.t('Could not be read'));
            return blockStartup(
                'This computer could not be identified',
                'JPT cannot check this computer\'s authorization until it can identify '
                + 'the computer itself. A new authorization file will not help. Restart '
                + 'JPT; if this keeps happening, send the line below to your Leader.\n{reason}',
                { reason: activationStatus.deviceError }
            );
        }
        if (!AuthorizationModel.requiresActivation(activationStatus)) return true;
        ApiClient.clearAuth();
        document.getElementById('app').style.display = 'none';
        hideModal('login-modal');
        renderStatus(activationStatus);
        showModal('activation-modal');
        return false;
    };

    window.downloadAuthorizationDeviceRequest = async function() {
        const button = document.getElementById('activation-request-btn');
        try {
            button.disabled = true;
            setActivationMessage('Generating device request...');
            const result = await ApiClient.createDeviceRequest();
            downloadBlob(result.blob, result.filename);
            AuthorizationActivation.setStatus(await ApiClient.getAuthorizationStatus());
            setActivationMessage('Device request downloaded: {filename}', false, {
                filename: result.filename
            });
        } catch (err) {
            setActivationMessage(err.message || 'Unable to generate device request.', true);
        } finally {
            button.disabled = false;
        }
    };

    window.activateAuthorization = async function() {
        const file = document.getElementById('activation-file')?.files?.[0];
        const password = document.getElementById('activation-password')?.value || '';
        const confirmation = document.getElementById('activation-password-confirm')?.value || '';
        const issuerFingerprint = document.getElementById('activation-fingerprint')?.value || '';
        const button = document.getElementById('activation-submit-btn');
        if (!file) return setActivationMessage('Select the .jptauth file supplied by your Leader.', true);
        if (password.length < 8) return setActivationMessage('Use a password with at least 8 characters.', true);
        if (password !== confirmation) return setActivationMessage('The two passwords do not match.', true);
        if (activationStatus?.trustRequired && !issuerFingerprint.trim()) {
            return setActivationMessage('Enter the Leader verification code supplied through a separate channel.', true);
        }

        try {
            button.disabled = true;
            setActivationMessage('Verifying authorization and activating this device...');
            const rawStatus = await ApiClient.activateAuthorization(file, password, issuerFingerprint);
            AuthorizationActivation.setStatus(rawStatus);
            if (AuthorizationModel.requiresActivation(activationStatus)) {
                throw new Error('Authorization was not activated. Check the file and try again.');
            }
            ApiClient.clearAuth();
            const activatedUsername = activationStatus.member?.username || '';
            document.getElementById('activation-file').value = '';
            document.getElementById('activation-fingerprint').value = '';
            document.getElementById('activation-password').value = '';
            document.getElementById('activation-password-confirm').value = '';
            AuthorizationActivation.complete(activatedUsername);
        } catch (err) {
            setActivationMessage(err.message || 'Activation failed.', true);
        } finally {
            button.disabled = false;
        }
    };
})();
