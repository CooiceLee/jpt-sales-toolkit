/** In-memory route draft. Preview is read-only; generate commits it atomically. */
(function() {
    const MODES = Object.freeze(['flight', 'drive', 'ground_public', 'other']);
    const DEFAULT_MODES = Object.freeze(['flight', 'drive', 'ground_public']);
    let draft = null;
    const priority = (value, legacyMode = 'auto') =>
        TripRouteValues.transportPriority(value, legacyMode, MODES, DEFAULT_MODES);
    const cleanOverride = value => TripRouteValues.cleanLegOverride(value, MODES);
    function returnedOverrides(plan) {
        const result = {};
        (plan?.legs || []).forEach(leg => {
            const source = { ...(leg.override || leg) };
            if (source.selected_mode === 'other') {
                source.manual_distance_km ??= leg.distance_km;
                source.manual_time_hours ??= leg.time_hours;
                source.manual_travel_half_days ??= leg.travel_half_days != null
                    ? leg.travel_half_days
                    : (leg.travel_days != null ? TripDuration.fromDisplayTravelDays(leg.travel_days) : null);
            }
            const manual = leg.has_override || leg.override_applied || source.mode_locked
                || source.manual_distance_km != null || source.manual_time_hours != null
                || source.manual_travel_half_days != null || source.manual_travel_days != null || source.notes;
            if (leg.leg_key && manual) result[leg.leg_key] = cleanOverride(source);
        });
        return result;
    }
    function fromPlan(plan) {
        const stops = plan?.stops || [];
        return {
            planId: plan?.id || null,
            header: {
                title: plan?.title || '',
                start_date: plan?.start_date || null,
                end_date: plan?.end_date || null,
                region: plan?.region || null,
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
            legOverrides: returnedOverrides(plan),
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
        const keys = new Set();
        if (draft.stopOrder.length) {
            keys.add(`origin>${draft.stopOrder[0]}`);
            draft.stopOrder.slice(1).forEach((id, index) => {
                keys.add(`${draft.stopOrder[index]}>${id}`);
            });
            keys.add(`${draft.stopOrder[draft.stopOrder.length - 1]}>destination`);
        }
        const returned = returnedOverrides(plan);
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
        durationFor: (id, fallback = 1) => TripDuration.normalizeHalfDays(
            draft?.stopDurations?.[id]?.half_days ?? fallback
        ),
        stayFor: (id, fallback = 1) => TripDuration.toDisplayDays(
            draft?.stopDurations?.[id]?.half_days ?? TripDuration.fromDisplayDays(fallback)
        ),
    });
})();
