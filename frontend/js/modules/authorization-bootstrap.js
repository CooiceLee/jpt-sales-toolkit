(function() {
    window.showMemberActivationFromSetup = function() {
        AuthorizationActivation.chooseMemberActivation(true);
    };

    window.showLeaderSetupFromActivation = function() {
        AuthorizationActivation.chooseMemberActivation(false);
    };

    window.bootstrapFirstLeader = async function() {
        const username = document.getElementById('bootstrap-username')?.value.trim() || '';
        const displayName = document.getElementById('bootstrap-display-name')?.value.trim() || '';
        const region = document.getElementById('bootstrap-region')?.value.trim() || '';
        const password = document.getElementById('bootstrap-password')?.value || '';
        const confirmation = document.getElementById('bootstrap-password-confirm')?.value || '';
        const issuerPassphrase = document.getElementById('bootstrap-issuer-passphrase')?.value || '';
        const issuerConfirmation = document.getElementById('bootstrap-issuer-confirm')?.value || '';
        const button = document.getElementById('bootstrap-submit-btn');
        const message = AuthorizationActivation.message;
        if (!username || !displayName) return message('Username and display name are required.', true);
        if (!region) return message('Business region is required.', true);
        if (/\s/.test(username)) return message('Username cannot contain spaces.', true);
        if (password.length < 8) return message('Login password must contain at least 8 characters.', true);
        if (password !== confirmation) return message('Login passwords do not match.', true);
        if (issuerPassphrase.length < 12) return message('Issuer passphrase must contain at least 12 characters.', true);
        if (issuerPassphrase !== issuerConfirmation) return message('Issuer passphrases do not match.', true);

        try {
            button.disabled = true;
            message('Creating the first Leader and protected signing key...');
            const result = await ApiClient.bootstrapAuthorizationLeader({
                username,
                display_name: displayName,
                region,
                password,
                issuer_passphrase: issuerPassphrase
            });
            AuthorizationActivation.setStatus(result.status);
            AuthorizationActivation.complete(result.username || username);
        } catch (err) {
            message(err.message || 'First-run setup failed.', true);
        } finally {
            button.disabled = false;
        }
    };
})();
