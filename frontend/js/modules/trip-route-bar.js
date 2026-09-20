/** The plan's status and its two route actions, visible from all four zones.
 *
 * They used to live inside the settings card, which three of the four zones
 * hide: somebody adjusting the order in the route zone could see that the
 * schedule had changed but had to go back to settings to do anything about it,
 * and the sentence telling them whether it was saved was on that same hidden
 * card.
 *
 * The buttons are the existing ones - preview and generate, with their own
 * validation, busy flag, request identity and conflict handling. Nothing here
 * saves anything by itself, and nothing here submits somebody's half-written
 * preparation form on their behalf.
 */
(function () {
    'use strict';

    const tr = (text, params) => window.I18n?.t(text, params) || text;
    const el = id => document.getElementById(id);

    function apply(state) {
        const status = el('trip-route-status');
        const next = el('trip-route-next');
        const preview = el('trip-route-preview');
        const save = el('trip-route-save');
        if (!status || !preview || !save) return;
        status.textContent = state.headline.text;
        status.className = `trip-route-status ${state.headline.tone}`;
        // Saying "recalculate" is what the button does: generate computes the
        // route again and writes the result. It is not a copy of the preview.
        preview.disabled = !state.actions.preview.enabled;
        save.disabled = !state.actions.save.enabled;
        preview.title = state.actions.preview.reason || '';
        save.title = state.actions.save.reason || '';
        if (next) {
            const blocked = state.actions.save.reason;
            const editor = state.nextStep?.kind === 'editor' ? state.nextStep.editor : null;
            // Looking at a preview is the one moment the two buttons read as a
            // sequence - try it, then save what I confirmed. Saving computes
            // again from the same settings rather than storing the preview, so
            // that is said here rather than left to be guessed.
            const previewing = !blocked && state.previewReady && state.draftDirty;
            next.className = `trip-route-next ${blocked ? 'blocked' : ''}`;
            next.textContent = blocked || (previewing
                ? tr('A trial is not saved; saving works the route out again.')
                : '');
            // The short sentence is what the bar has room for; the rest of the
            // answer - and it is the reader's actual question - is one hover or
            // one screen-reader stop away rather than cut off mid-word.
            if (previewing && !blocked) {
                next.title = tr('A trial does not write anything into the saved plan. Saving works the route out again from the settings as they are then, so a change made in between is included.');
            } else {
                next.removeAttribute('title');
            }
            // A greyed-out button with a sentence beside it still leaves the
            // reader looking for the form that is holding it. This is the way
            // there, and it is the only thing the bar does to somebody's draft.
            if (editor) {
                const go = document.createElement('button');
                go.type = 'button';
                go.className = 'btn btn-text btn-sm';
                go.textContent = tr('Go to it');
                go.onclick = () => window.TripRouteBar.goToBlocker();
                next.appendChild(document.createTextNode(' '));
                next.appendChild(go);
            }
        }
    }

    function render() {
        const state = window.TripRouteState?.derive?.();
        if (state) apply(state);
        // The download panel states the same reason in its own words, in
        // visible text rather than a tooltip nobody on a touchscreen can read.
        window.TripExportActions?.refresh?.(
            typeof State === 'undefined' ? null : State?.currentTripPlan);
        return state;
    }

    // Refused for a reason the reader can act on: take them to the editor that
    // is holding things up instead of leaving them to guess which one it is.
    function blockedByEditor(state) {
        const editor = state?.nextStep?.kind === 'editor' ? state.nextStep.editor : null;
        if (!editor) return false;
        notify(tr('Finish or cancel first: {editors}', { editors: editor.label }));
        window.TripZones?.show?.(editor.zone);
        window.TripRouteFocus?.focusEditor?.(editor.kind, editor.stopId || editor.userId);
        return true;
    }

    // Whether a route action can run depends on the editors in this module, and
    // they mark themselves dirty as the reader types. One delegated listener,
    // one redraw per frame - rather than a hook inside each editor.
    let queued = false;
    ['input', 'change'].forEach(type => document.addEventListener(type, event => {
        const host = document.getElementById('module-trip-planner');
        if (!host || !host.contains(event.target) || queued) return;
        queued = true;
        requestAnimationFrame(() => { queued = false; render(); });
    }, true));

    window.TripRouteBar = Object.freeze({
        render,
        // Take the reader to the editor that is refusing the route action.
        // Nothing is saved or discarded on the way.
        goToBlocker() {
            const state = window.TripRouteState?.derive?.();
            const editor = state?.nextStep?.kind === 'editor' ? state.nextStep.editor : null;
            if (!editor) return;
            window.TripZones?.show?.(editor.zone);
            window.TripRouteFocus?.focusEditor?.(editor.kind, editor.stopId || editor.userId);
        },
        preview() {
            const state = render();
            if (blockedByEditor(state)) return;
            if (!state?.actions.preview.enabled) {
                if (state?.actions.preview.reason) notify(state.actions.preview.reason);
                return;
            }
            window.previewCurrentTripItinerary?.();
        },
        save() {
            const state = render();
            if (blockedByEditor(state)) return;
            if (!state?.actions.save.enabled) {
                if (state?.actions.save.reason) notify(state.actions.save.reason);
                return;
            }
            window.generateCurrentTripItinerary?.();
        },
    });
})();
