/** Independent unsaved boundary for the personal-stop editor. */
(function() {
    let dirty = false;
    const LOCATION_FIELDS = new Set([
        'trip-free-stop-address', 'trip-free-stop-city',
        'trip-free-stop-country', 'trip-free-stop-postal',
    ]);
    const EDITABLE_FIELDS = [
        'trip-free-stop-category', 'trip-free-stop-stay', 'trip-free-stop-name',
        'trip-free-stop-period', 'trip-free-stop-confirmation',
        ...LOCATION_FIELDS, 'trip-free-stop-lat', 'trip-free-stop-lng',
        'trip-free-stop-purpose', 'trip-free-stop-notes',
    ];
    function render() {
        const root = document.getElementById('trip-free-stop-draft-status');
        if (root) root.textContent = dirty ? I18n.t('Personal stop changes are not saved.') : '';
    }
    function mark() { dirty = true; render(); }
    function reset() { dirty = false; render(); }
    function confirmDiscard(message = 'Discard unsaved personal stop changes?') {
        return !dirty || confirm(I18n.t(message));
    }
    function guardRouteAction(automatic = false) {
        if (!dirty) return false;
        const message = I18n.t('Save or cancel personal stop changes before continuing with the route.');
        if (automatic) notify(message); else alert(message);
        return true;
    }
    function bind() {
        EDITABLE_FIELDS.forEach(id => {
            const field = document.getElementById(id);
            if (!field?.addEventListener) return;
            const event = field.tagName === 'SELECT' ? 'change' : 'input';
            field.addEventListener(event, () => {
                if (LOCATION_FIELDS.has(id)) window.TripFreeStopForm?.locationTextChanged?.();
                else mark();
            });
        });
    }
    window.TripFreeStopDraft = Object.freeze({ mark, reset, isDirty: () => dirty,
        confirmDiscard, guardRouteAction });
    if (document.readyState === 'loading' && document.addEventListener) {
        document.addEventListener('DOMContentLoaded', bind, { once: true });
    } else bind();
})();
