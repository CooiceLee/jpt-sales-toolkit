(function() {
    window.applyAuthorizationSessionNotice = function() {
        const banner = document.getElementById('authorization-expiry-banner');
        const days = AuthorizationActivation.status()?.authorization?.daysRemaining;
        if (!banner || days === null || days === undefined || days > 30) {
            banner?.classList.add('hidden');
            return;
        }
        banner.textContent = `Authorization expires in ${days} day${days === 1 ? '' : 's'}. Ask your Leader to renew it.`;
        banner.classList.toggle('urgent', days <= 7);
        banner.classList.remove('hidden');
    };
})();
