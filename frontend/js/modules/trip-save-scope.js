/** What a save on the route card did *not* cover.
 *
 * One card carries three different boundaries: the agreed time writes itself to
 * the server, the stay duration lives in the route draft until the route is
 * calculated and saved, and the visit's own details are saved by this button.
 * "Saved" on its own therefore answers the wrong question - the reader wants to
 * know which part, and what is still waiting.
 *
 * Every sentence here is derived from real state. Saying "something else is
 * unsaved" when nothing is would be the same fault in the other direction.
 */
(function () {
    'use strict';

    const t = (key, params) => (window.I18n?.t ? I18n.t(key, params) : key);

    function pendingDuration(stopId) {
        const draft = window.TripPlanningDraft?.get?.();
        const stop = (State.currentTripPlan?.stops || [])
            .find(item => String(item.id) === String(stopId));
        const wanted = draft?.stopDurations?.[stopId]?.half_days;
        if (!stop || wanted == null) return 0;
        const saved = window.TripDuration?.readStopDuration?.(stop);
        return Number(wanted) === Number(saved) ? 0 : Number(wanted);
    }

    /** The other unsaved work, named, or nothing at all. */
    function note(stopId) {
        const parts = [];
        const half = pendingDuration(stopId);
        if (half) {
            parts.push(t('The stay of {count} days is still in the route draft; '
                + 'calculate and save the route to apply it.', {
                count: window.TripDuration?.toDisplayDays?.(half) ?? half }));
        }
        (window.TripOpenEditors?.list?.() || [])
            .filter(editor => editor.kind !== 'visit' || String(editor.stopId) !== String(stopId))
            .forEach(editor => parts.push(t('Still unsaved: {what}', { what: editor.label })));
        return parts.length ? ` · ${parts.join(' ')}` : '';
    }

    window.TripSaveScope = Object.freeze({ note, pendingDuration });
})();
