/** Which local editors are holding unsaved work right now.
 *
 * Four places in the trip page let somebody type without saving: a visit
 * preparation, a personal stop, a visit execution card, and one member's own
 * departure and return places. Each can stop a route action, and each has to be
 * reachable when it does - a greyed-out button with no way to the form holding
 * it is what the reader is left guessing about.
 *
 * Kept apart from the judgement that uses it so that adding a fifth editor is
 * one entry here rather than a change to how the route is judged.
 */
(function () {
    'use strict';

    const tr = (text, params) => window.I18n?.t(text, params) || text;

    // The editors holding something of their own. Each can stop a route action,
    // and each has to be reachable when it does.
    function openEditors() {
        const found = [];
        if (window.TripBriefingDraft?.isDirty?.()) {
            // Whose preparation it is: "an unsaved visit preparation" leaves
            // somebody with twenty-seven visits to find it by opening each.
            const stopId = window.TripBriefingDraft.getStopId?.() || null;
            const stop = (typeof State === 'undefined' ? null : State?.currentTripPlan?.stops || [])
                .find(item => String(item.id) === String(stopId));
            const name = stop?.customer_name || stop?.location_name || '';
            found.push({ kind: 'briefing', zone: 'briefing', stopId,
                label: name
                    ? tr('Unsaved visit preparation for {name}', { name })
                    : tr('An unsaved visit preparation') });
        }
        if (window.TripFreeStopDraft?.isDirty?.() || window.TripFreeStopForm?.isOpen?.()) {
            found.push({ kind: 'free-stop', zone: 'route', label: tr('An unsaved personal stop') });
        }
        // Execution has one card per stop, so the blocked action carries the
        // visit's id: "go to it" must arrive at the card being typed into.
        const visit = window.TripVisitDraft?.isDirty?.()
            ? window.TripVisitDraft.firstDirty?.() || {} : null;
        if (visit) {
            found.push({ kind: 'visit', zone: 'execution', stopId: visit.id || null,
                label: visit.name
                    ? tr('An unsaved visit record for {name}', { name: visit.name })
                    : tr('An unsaved visit record') });
        }
        // The visit purpose on the route card: typed, not saved, and belonging
        // to one visit - so it is named and reachable like the rest.
        const purpose = window.TripStopTyping?.isDirty?.()
            ? window.TripStopTyping.firstDirty?.() : null;
        if (purpose) {
            found.push({ kind: 'stop-purpose', zone: 'route', stopId: purpose.id,
                label: purpose.name
                    ? tr('Unsaved visit purpose for {name}', { name: purpose.name })
                    : tr('An unsaved visit purpose') });
        }
        // One member's own places, being edited in the team card: unsaved, the
        // route would be worked out from where they no longer leave from.
        const places = window.TripTeamEndpoints?.openEditor?.();
        if (places?.dirty) {
            found.push({ kind: 'member-places', zone: 'settings',
                userId: places.userId, label: tr(
                    'Unsaved departure and return places for {name}',
                    { name: places.name }) });
        }
        return found;
    }

    window.TripOpenEditors = Object.freeze({ list: openEditors });
})();
