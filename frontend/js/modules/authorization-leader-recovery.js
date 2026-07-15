(function() {
    window.recoverLeaderAuthorization = async function() {
        const username = document.getElementById('recovery-username')?.value.trim() || '';
        const password = document.getElementById('recovery-password')?.value || '';
        const issuerPassphrase = document.getElementById('recovery-issuer-passphrase')?.value || '';
        const button = document.getElementById('recovery-submit-btn');
        const message = AuthorizationActivation.message;
        if (!username || password.length < 8 || issuerPassphrase.length < 12) {
            return message('Enter the Leader username, login password, and issuer passphrase.', true);
        }
        try {
            button.disabled = true;
            message('Recovering the Leader authorization on this computer...');
            const status = await ApiClient.recoverLeaderAuthorization({
                username,
                password,
                issuer_passphrase: issuerPassphrase
            });
            AuthorizationActivation.setStatus(status);
            AuthorizationActivation.complete(username);
        } catch (err) {
            message(err.message || 'Leader recovery failed.', true);
        } finally {
            button.disabled = false;
        }
    };
})();
