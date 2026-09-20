/** What is true about this plan's route, derived from what already exists.
 *
 * Three places used to judge it and they judged it differently: the settings
 * card looked only at the local draft and said "Route settings match the saved
 * plan" while the server had marked the itinerary out of date, and the export
 * panel - which does check that - refused the download. A reader who had just
 * been told everything matched then met a disabled button.
 *
 * So the judgement is made once, here, from the values that already exist: the
 * plan the server sent, the local draft, and the editors that are open. Nothing
 * is stored; there is no second copy to keep in step.
 *
 * It is not one "can I act" flag either. Being busy, holding an unsaved editor
 * and having an out-of-date route are three different situations that can all
 * be true at once, and each action has its own reason to be refused.
 */
(function () {
    'use strict';

    const tr = (text, params) => window.I18n?.t(text, params) || text;

    // Risks the saved route cannot honour: an agreed visit nobody can reach, a
    // person booked in two places, a return landing after the trip ends. A
    // route holding one of these is saved, but not "ready".
    const BLOCKING_RISKS = new Set([
        'cannot_reach_booked_visit',
        'member_double_booked',
        'member_return_overrun',
        'member_departure_after_plan_end',
        'participant_not_in_trip_team',
    ]);

    function facts(plan, draft) {
        const summary = plan?.itinerary_summary || {};
        const serverStale = summary.stale === true || summary.valid === false;
        return {
            planId: plan?.id || null,
            hasItinerary: Boolean(plan?.itinerary_generated_at) && !serverStale,
            serverStale: Boolean(plan?.id) && serverStale,
            staleReason: (summary.warnings || [])[0]
                || 'The itinerary is out of date. Preview and save it again.',
            draftDirty: Boolean(draft?.dirty),
            previewReady: Boolean(draft?.previewReady),
            busy: typeof State !== 'undefined' && Boolean(State?.tripBusy),
            risks: Array.isArray(summary.risks) ? summary.risks : [],
            blockingRisks: (Array.isArray(summary.risks) ? summary.risks : [])
                .filter(risk => BLOCKING_RISKS.has(risk?.kind)),
            editors: window.TripOpenEditors?.list?.() || [],
        };
    }

    // One sentence, in the order a reader needs it: what is happening now, then
    // what is unfinished, then what is true.
    function headline(state) {
        if (!state.planId) return { text: tr('Create or select a plan'), tone: 'idle' };
        if (state.busy) return { text: tr('Working…'), tone: 'busy' };
        if (state.draftDirty && state.previewReady) {
            return { text: tr('Showing a preview. Not saved yet.'), tone: 'warn' };
        }
        if (state.draftDirty) {
            return { text: tr('Unsaved route changes'), tone: 'warn' };
        }
        if (state.serverStale) {
            // The change itself was saved. The route it invalidated was not.
            return { text: tr('Saved. The route needs recalculating.'), tone: 'warn' };
        }
        if (!state.hasItinerary) {
            return { text: tr('No route calculated yet'), tone: 'idle' };
        }
        if (state.blockingRisks.length) {
            // Saved, and still not a trip anybody can make: a green "saved"
            // over an agreed visit nobody can reach is the wrong sentence.
            return {
                text: tr('Route saved, but {count} bookings do not work',
                    { count: state.blockingRisks.length }),
                tone: 'warn',
            };
        }
        return { text: tr('Route saved'), tone: 'ok' };
    }

    function actions(state) {
        const busyReason = state.busy ? tr('A route request is already running.') : null;
        const editorReason = state.editors.length
            ? tr('Finish or cancel first: {editors}',
                { editors: state.editors.map(item => item.label).join('、') })
            : null;
        const preview = busyReason || editorReason
            || (state.planId ? null : tr('Select a saved itinerary first.'));
        const save = preview;
        let exportReason = busyReason
            || (state.planId ? null : tr('Select a saved itinerary to download.'));
        if (!exportReason && state.draftDirty) {
            exportReason = tr('Save the current route draft before exporting it.');
        }
        if (!exportReason && state.serverStale) {
            exportReason = tr('This route is out of date. Recalculate and save it before exporting.');
        }
        if (!exportReason && !state.hasItinerary) {
            exportReason = tr('Calculate and save the route before exporting it.');
        }
        return {
            preview: { enabled: !preview, reason: preview },
            save: { enabled: !save, reason: save },
            download: { enabled: !exportReason, reason: exportReason },
        };
    }

    function derive(plan, draft) {
        const state = facts(
            plan || (typeof State === 'undefined' ? null : State?.currentTripPlan),
            draft || window.TripPlanningDraft?.get?.()
        );
        return Object.freeze({
            ...state,
            headline: headline(state),
            actions: actions(state),
            // What the reader should do next, when there is something to do.
            nextStep: state.editors.length
                ? { kind: 'editor', editor: state.editors[0] }
                : state.busy ? null
                : state.draftDirty && !state.previewReady ? { kind: 'preview' }
                : state.draftDirty ? { kind: 'save' }
                : state.serverStale ? { kind: 'preview' }
                : state.blockingRisks.length ? { kind: 'risks' }
                : null,
        });
    }

    window.TripRouteState = Object.freeze({
        derive, openEditors: () => window.TripOpenEditors?.list?.() || [],
        // The one list of what "does not work" means. The member card shows the
        // same risks per person, and two lists would disagree about a booking
        // the customer already agreed to.
        blocks: kind => BLOCKING_RISKS.has(kind),
    });
})();
