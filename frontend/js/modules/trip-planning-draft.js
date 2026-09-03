/** In-memory route draft. Preview is read-only; generate commits it atomically. */
(function() {
    const MODES = Object.freeze(['flight', 'drive', 'ground_public', 'other']);
    const DEFAULT_MODES = Object.freeze(['flight', 'drive', 'ground_public']);
    let draft = null;
    const priority = (value, legacyMode = 'auto') =>
        TripRouteValues.transportPriority(value, legacyMode, MODES, DEFAULT_MODES);
    function fromPlan(plan) {
        const stops = plan?.stops || [];
        return {
            planId: plan?.id || null,
            header: {
                title: plan?.title || '',
                start_date: plan?.start_date || null,
                end_date: plan?.end_date || null,
                region: plan?.region || null,
                // Without this the form falls back to single-traveller and
                // the next header save turns a team trip solo.
                planning_mode: plan?.planning_mode === 'team' ? 'team' : 'legacy',
                origin_name: plan?.origin_name || null,
                origin_lat: plan?.origin_lat ?? null,
                origin_lng: plan?.origin_lng ?? null,
                destination_name: plan?.destination_name || null,
                destination_lat: plan?.destination_lat ?? null,
                destination_lng: plan?.destination_lng ?? null,
                avoid_weekends: plan?.avoid_weekends !== false,
                holiday_dates: [...(plan?.holiday_dates || [])],
                description: plan?.description || null,
            },
            routeOrderMode: plan?.route_order_mode === 'manual' ? 'manual' : 'auto',
            transportModePriority: priority(plan?.transport_mode_priority, plan?.travel_mode),
            departureWindowStart: plan?.departure_window_start || '',
            departureWindowEnd: plan?.departure_window_end || '',
            returnWindowStart: plan?.return_window_start || '',
            returnWindowEnd: plan?.return_window_end || '',
            stopOrder: stops.map(stop => stop.id),
            stopDurations: Object.fromEntries(stops.map(stop => [stop.id, {
                half_days: TripDuration.readStopDuration(stop),
                preferred_period: ['auto', 'AM', 'PM'].includes(stop.preferred_period) ? stop.preferred_period : 'auto',
                locked: Boolean(stop.schedule_locked),
            }])),
            legOverrides: TripLegOverrides.fromPlan(plan, MODES),
            dirty: false,
            previewReady: false,
            revision: 0,
        };
    }
    function reconcile(plan) {
        const ids = (plan?.stops || []).map(stop => stop.id);
        draft.stopOrder = draft.routeOrderMode === 'manual' ? [
            ...draft.stopOrder.filter(id => ids.includes(id)),
            ...ids.filter(id => !draft.stopOrder.includes(id)),
        ] : [...ids];
        const durations = {};
        (plan?.stops || []).forEach(stop => {
            const current = draft.stopDurations[stop.id] || {};
            durations[stop.id] = {
                half_days: TripDuration.normalizeHalfDays(current.half_days ?? TripDuration.readStopDuration(stop)),
                preferred_period: ['auto', 'AM', 'PM'].includes(current.preferred_period)
                    ? current.preferred_period : (stop.preferred_period || 'auto'),
                locked: current.locked == null ? Boolean(stop.schedule_locked) : Boolean(current.locked),
            };
        });
        draft.stopDurations = durations;
        // Which connections still exist. A calculated leg counts when both of
        // its ends are still on the plan - that drops the ones through a stop
        // just removed, and keeps each member's own chain, which the single run
        // through every stop below cannot describe.
        const alive = new Set([...ids, 'origin', 'destination']);
        const keys = new Set((plan?.legs || [])
            .map(leg => leg.leg_key)
            .filter(key => key && String(key).split('>').every(
                part => alive.has(part))));
        if (draft.stopOrder.length) {
            keys.add(`origin>${draft.stopOrder[0]}`);
            draft.stopOrder.slice(1).forEach((id, index) => {
                keys.add(`${draft.stopOrder[index]}>${id}`);
            });
            keys.add(`${draft.stopOrder[draft.stopOrder.length - 1]}>destination`);
        }
        const returned = TripLegOverrides.fromPlan(plan, MODES);
        draft.legOverrides = Object.fromEntries(
            Object.entries({ ...returned, ...draft.legOverrides }).filter(([key]) => keys.has(key))
        );
    }
    function hydrate(plan, options = {}) {
        const switchingPlan = (draft?.planId || null) !== (plan?.id || null);
        if (switchingPlan) window.TripFreeStopForm?.close?.({ force: true });
        window.TripSuggestionState?.resetForPlan?.(plan?.id || null);
        if (!plan?.id) draft = null;
        else if (!draft || draft.planId !== plan.id || options.committed || !draft.dirty) draft = fromPlan(plan);
        else reconcile(plan);
        window.TripTransportView?.render(plan, draft);
        return draft;
    }
    /** Record something the server already has, without marking work unsaved.

    Renaming a plan saves at once, so the route it describes is exactly as
    saved as it was a moment before. Going through `change` would mark it
    unsaved, which refuses the export and asks for a route nobody altered.
    */
    function adopt(mutator) {
        if (!draft) return;
        mutator(draft);
        window.TripTransportView?.render(State.currentTripPlan, draft);
    }

    function change(mutator) {
        if (!draft) return;
        mutator(draft);
        draft.dirty = true;
        draft.previewReady = false;
        draft.revision += 1;
        window.TripTransportView?.render(State.currentTripPlan, draft);
    }
    function itineraryPayload() {
        if (!draft) return {};
        return {
            ...draft.header,
            route_order_mode: draft.routeOrderMode,
            transport_mode_priority: [...draft.transportModePriority],
            departure_window_start: draft.departureWindowStart || null,
            departure_window_end: draft.departureWindowEnd || null,
            return_window_start: draft.returnWindowStart || null,
            return_window_end: draft.returnWindowEnd || null,
            stop_order: draft.routeOrderMode === 'manual' ? [...draft.stopOrder] : null,
            stop_durations: Object.fromEntries(Object.entries(draft.stopDurations)
                .map(([id, value]) => [id, { ...value }])),
            leg_overrides: { ...draft.legOverrides },
        };
    }

    function previewApplied(plan, revision) {
        if (!draft || revision !== draft.revision) return false;
        reconcile(plan);
        // A preview replaces the on-screen itinerary but never writes it. Keep
        // the draft explicitly unsaved until generate/save succeeds, even when
        // the route fields themselves were unchanged before previewing.
        draft.dirty = true;
        draft.previewReady = true;
        window.TripTransportView?.render(plan, draft);
        return true;
    }

    window.TripPlanningDraft = Object.freeze({
        MODES, hydrate, get: () => draft, itineraryPayload,
        revision: () => draft?.revision || 0,
        isCurrentRevision: value => value === (draft?.revision || 0),
        previewApplied,
        change,
        adopt,
        durationFor: (id, fallback = 1) => TripDuration.normalizeHalfDays(
            draft?.stopDurations?.[id]?.half_days ?? fallback
        ),
        stayFor: (id, fallback = 1) => TripDuration.toDisplayDays(
            draft?.stopDurations?.[id]?.half_days ?? TripDuration.fromDisplayDays(fallback)
        ),
    });
})();
