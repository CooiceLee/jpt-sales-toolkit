/** Protect unsaved detail-panel form changes during tab, card and module changes. */
(function () {
    'use strict';
    let dirty = false;

    const tr = text => window.I18n?.t(text) || text;
    const isField = target => target?.matches?.('input, select, textarea');

    function init() {
        const content = document.getElementById('panel-content');
        if (!content || content.dataset.dirtyStateBound) return;
        content.dataset.dirtyStateBound = '1';
        ['input', 'change'].forEach(eventName => content.addEventListener(eventName, event => {
            if (isField(event.target)) dirty = true;
        }));
    }

    function reset() { dirty = false; }
    function isDirty() { return dirty; }
    function confirmDiscard() {
        if (!dirty) return true;
        if (!window.confirm(tr('Discard unsaved changes?'))) return false;
        reset();
        return true;
    }

    window.PanelDirtyState = { init, reset, isDirty, confirmDiscard };
    document.addEventListener('DOMContentLoaded', init, { once: true });
})();
