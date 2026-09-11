/** What is happening to the reader's edits, said in one place.
 *
 * A form that looks the same whether the work is unsaved, being written,
 * written, or refused teaches people to press Save twice and to distrust what
 * they see. These four states are the ones a person actually meets, and they
 * are shown next to the button that causes them.
 */
(function () {
    'use strict';

    const tr = (text, params) => window.I18n?.t(text, params) || text;
    const STATES = {
        clean: { text: '', tone: '' },
        dirty: { text: 'Unsaved changes', tone: 'is-dirty' },
        saving: { text: 'Saving…', tone: 'is-busy' },
        saved: { text: 'Saved', tone: 'is-done' },
        failed: { text: 'Not saved', tone: 'is-failed' },
    };

    function element() {
        return document.getElementById('panel-save-state');
    }

    function show(state, detail) {
        const target = element();
        if (!target) return state;
        const chosen = STATES[state] || STATES.clean;
        target.className = `panel-save-state ${chosen.tone}`.trim();
        target.textContent = chosen.text
            ? (detail ? `${tr(chosen.text)} · ${detail}` : tr(chosen.text))
            : '';
        // A failure has to be reachable by a screen reader the moment it
        // happens; the other states are quiet updates.
        target.setAttribute('role', state === 'failed' ? 'alert' : 'status');
        return state;
    }

    // Follows the form itself, so a field edited anywhere in the panel reports
    // the same thing as the Save button.
    function watch() {
        const content = document.getElementById('panel-content');
        if (!content || content.dataset.saveStateBound) return;
        content.dataset.saveStateBound = '1';
        ['input', 'change'].forEach(name => content.addEventListener(name, event => {
            if (event.target?.matches?.('input, select, textarea')) show('dirty');
        }));
    }

    window.PanelSaveState = Object.freeze({ show, watch, STATES });
    document.addEventListener('DOMContentLoaded', watch, { once: true });
})();
