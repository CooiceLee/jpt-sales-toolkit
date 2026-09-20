/** What happened to the agreed time you just typed - and what it will hold.
 *
 * The field saves itself the moment it changes: the calculation reads a
 * confirmed time from the stop, so holding it in a draft would mean the preview
 * ignored what was just entered. A field that writes to the server on change
 * has to say so, has to say when it is writing, and has to say when the write
 * failed; silence reads as "not saved" and a stale "saved" reads as a lie.
 *
 * It also has to say what the saved date will *do*. Only a time somebody
 * confirmed holds its place - the route keeps a locked visit where it is and
 * treats every other date as its own output, free to move on the next run
 * (backend: trip_team_adapter._is_locked). Typing a date and leaving the
 * confirmation box unticked therefore writes the date and then watches the next
 * preview move it, which looks exactly like a save that did not work. Rather
 * than ticking the box for the reader - nobody but them knows whether the
 * customer agreed - this says what is true and what would pin it.
 *
 * And saving the time is not saving the route: the trip around it is still
 * whatever the last calculation produced.
 */
(function () {
    'use strict';

    const t = (key, params) => (window.I18n?.t ? I18n.t(key, params) : key);

    function routeNote() {
        const route = window.TripRouteState?.derive?.();
        if (!route || (!route.serverStale && !route.draftDirty)) return '';
        return ` · ${t('Calculate and save the route to work the trip around it.')}`;
    }

    /** What this stop's agreed time means as the fields now stand. */
    function hint(stop) {
        if (!stop?.planned_date) return t('Saved as soon as you change it');
        if (stop.schedule_locked) return t('Confirmed, so the route is planned around it');
        return t('Saved, but not confirmed: the next route calculation can move this day. '
            + 'Tick "Customer confirmed this time" to hold it.');
    }

    /**
     * Say it where the field is, without redrawing the card.
     *
     * Redrawing would take the caret out of the date the reader is still
     * typing, and the state changes three times during one save.
     */
    function set(stopId, state) {
        const line = document.getElementById(`stop-agree-save-${stopId}`);
        if (!line) return;
        const stop = (State.currentTripPlan?.stops || [])
            .find(item => String(item.id) === String(stopId));
        if (state === 'saving') line.textContent = t('Saving…');
        else if (state === 'failed') line.textContent = t('Not saved. Try again.');
        else if (state === 'saved') {
            line.textContent = `${t('Agreed time saved')} · ${hint(stop)}${routeNote()}`;
        } else line.textContent = hint(stop);
        line.dataset.state = state || 'idle';
    }

    window.TripAgreeStatus = Object.freeze({ set, hint });
})();
