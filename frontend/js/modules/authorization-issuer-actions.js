(function() {
    window.initializeAuthorizationIssuer = async function() {
        const passphrase = document.getElementById('authorization-issuer-passphrase')?.value || '';
        const confirmation = document.getElementById('authorization-issuer-confirm')?.value || '';
        const button = document.getElementById('authorization-issuer-btn');
        if (passphrase.length < 12) {
            return showAuthorizationCenterMessage('Issuer passphrase must contain at least 12 characters.', true);
        }
        if (passphrase !== confirmation) {
            return showAuthorizationCenterMessage('Issuer passphrases do not match.', true);
        }
        if (!confirm('Initialize this device as an authorization issuer? Keep the issuer passphrase secure.')) return;

        try {
            button.disabled = true;
            showAuthorizationCenterMessage('Initializing authorization issuer...');
            await ApiClient.initializeAuthorizationIssuer(passphrase);
            document.getElementById('authorization-issuer-passphrase').value = '';
            document.getElementById('authorization-issuer-confirm').value = '';
            await refreshAuthorizationCenter();
            notify('Authorization issuer initialized');
        } catch (err) {
            showAuthorizationCenterMessage(err.message || 'Unable to initialize issuer.', true);
        } finally {
            button.disabled = false;
        }
    };

    window.renewLocalLeaderAuthorization = async function() {
        const passphrase = document.getElementById('authorization-renew-passphrase')?.value || '';
        const button = document.getElementById('authorization-renew-btn');
        if (passphrase.length < 12) {
            return showAuthorizationCenterMessage('Enter the issuer passphrase to renew this Leader device.', true);
        }
        try {
            button.disabled = true;
            showAuthorizationCenterMessage('Renewing this Leader device for 90 days...');
            await ApiClient.renewLocalLeaderAuthorization(passphrase);
            document.getElementById('authorization-renew-passphrase').value = '';
            await refreshAuthorizationCenter();
            notify('Leader authorization renewed for 90 days');
        } catch (err) {
            showAuthorizationCenterMessage(err.message || 'Unable to renew Leader authorization.', true);
        } finally {
            button.disabled = false;
        }
    };

    window.issueMemberAuthorization = async function() {
        const memberId = document.getElementById('authorization-issue-member')?.value || '';
        const requestFile = document.getElementById('authorization-request-file')?.files?.[0];
        const passphrase = document.getElementById('authorization-issue-passphrase')?.value || '';
        const days = Number(document.getElementById('authorization-issue-days')?.value || 90);
        const button = document.getElementById('authorization-issue-btn');
        if (!memberId) return showAuthorizationCenterMessage('Select the member receiving this authorization.', true);
        if (!requestFile) return showAuthorizationCenterMessage('Select the member\'s .jptreq device request.', true);
        if (!passphrase) return showAuthorizationCenterMessage('Enter the issuer passphrase.', true);
        if (days !== 90) {
            return showAuthorizationCenterMessage('Authorization period is fixed at 90 days.', true);
        }

        try {
            button.disabled = true;
            showAuthorizationCenterMessage('Signing member authorization...');
            const result = await ApiClient.issueAuthorization(memberId, requestFile, passphrase, days);
            downloadBlob(result.blob, result.filename);
            document.getElementById('authorization-request-file').value = '';
            document.getElementById('authorization-issue-passphrase').value = '';
            await refreshAuthorizationCenter();
            notify(`Authorization downloaded: ${result.filename}`);
        } catch (err) {
            showAuthorizationCenterMessage(err.message || 'Unable to issue authorization.', true);
        } finally {
            button.disabled = false;
        }
    };
})();
