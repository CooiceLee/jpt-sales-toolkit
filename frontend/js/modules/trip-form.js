function getTripFilters() {
    return {
        region: document.getElementById('trip-candidate-region')?.value || '',
        sales_stage: document.getElementById('trip-stage')?.value || '',
        limit: State.tripCandidatePagination.limit,
        offset: State.tripCandidatePagination.offset
    };
}

function readTripPlanFormPayload() {
    const routeDraft = window.TripPlanningDraft?.get?.();
    // The visible form is the final source for header fields. A user may save
    // immediately after typing, before a change/blur handler has copied the
    // value into the in-memory route draft.
    const header = readTripPlanHeaderFormPayload();
    return {
        ...header,
        travel_mode: 'auto',
        route_order_mode: routeDraft?.routeOrderMode
            || (document.getElementById('trip-route-order-mode')?.value === 'manual' ? 'manual' : 'auto'),
        transport_mode_priority: routeDraft?.transportModePriority || ['flight', 'drive', 'ground_public'],
        departure_window_start: routeDraft
            ? routeDraft.departureWindowStart || null
            : document.getElementById('trip-departure-window-start')?.value || null,
        departure_window_end: routeDraft
            ? routeDraft.departureWindowEnd || null
            : document.getElementById('trip-departure-window-end')?.value || null,
        return_window_start: routeDraft
            ? routeDraft.returnWindowStart || null
            : document.getElementById('trip-return-window-start')?.value || null,
        return_window_end: routeDraft
            ? routeDraft.returnWindowEnd || null
            : document.getElementById('trip-return-window-end')?.value || null,
    };
}

function readTripPlanHeaderFormPayload() {
    const titleInput = document.getElementById('trip-title');
    return {
        title: titleInput ? titleInput.value.trim()
            || I18n.t('Trip Plan {date}', { date: formatDate(toDateInput(new Date())) }) : null,
        start_date: document.getElementById('trip-start-date')?.value || null,
        end_date: document.getElementById('trip-end-date')?.value || null,
        region: document.getElementById('trip-plan-region')?.value || null,
        planning_mode: document.getElementById('trip-planning-mode')?.value || 'legacy',
        origin_name: document.getElementById('trip-origin-name')?.value?.trim() || null,
        origin_lat: numericOrNull(document.getElementById('trip-origin-lat')?.value),
        origin_lng: numericOrNull(document.getElementById('trip-origin-lng')?.value),
        destination_name: document.getElementById('trip-destination-name')?.value?.trim() || null,
        destination_lat: numericOrNull(document.getElementById('trip-destination-lat')?.value),
        destination_lng: numericOrNull(document.getElementById('trip-destination-lng')?.value),
        avoid_weekends: Boolean(document.getElementById('trip-avoid-weekends')?.checked),
        holiday_dates: parseHolidayInput(document.getElementById('trip-holidays')?.value || ''),
        description: document.getElementById('trip-description')?.value?.trim() || null,
    };
}

function populateTripPlanForm(plan, options = {}) {
    if (!plan) return;
    const routeDraft = window.TripPlanningDraft?.hydrate?.(plan, options);
    const header = routeDraft?.header || plan;
    setInputValue('trip-title', header.title || '');
    setInputValue('trip-start-date', header.start_date || '');
    setInputValue('trip-end-date', header.end_date || '');
    setInputValue('trip-plan-region', header.region || '');
    setInputValue('trip-planning-mode', header.planning_mode || 'legacy');
    // A team trip runs between the plan's own dates, and a member who leaves on
    // their own day says so on their own row. Two more windows saying the same
    // thing for everybody at once only gave the reader a second place to look.
    document.querySelectorAll('[data-single-traveller-only]').forEach(node => {
        node.hidden = header.planning_mode === 'team';
    });
    setInputValue('trip-origin-name', header.origin_name || '');
    setInputValue('trip-origin-lat', header.origin_lat ?? '');
    setInputValue('trip-origin-lng', header.origin_lng ?? '');
    setInputValue('trip-destination-name', header.destination_name || '');
    setInputValue('trip-destination-lat', header.destination_lat ?? '');
    setInputValue('trip-destination-lng', header.destination_lng ?? '');
    setInputValue('trip-origin-preset', window.TripChinaHubs?.detect?.(header.origin_lat, header.origin_lng) || 'custom');
    setInputValue('trip-destination-preset', window.TripChinaHubs?.detect?.(
        header.destination_lat, header.destination_lng
    ) || 'custom');
    setInputValue('trip-travel-mode', 'auto');
    setInputValue('trip-route-order-mode', routeDraft?.routeOrderMode || plan.route_order_mode || 'auto');
    setInputValue('trip-departure-window-start', tripDateTimeLocalValue(
        routeDraft ? routeDraft.departureWindowStart : plan.departure_window_start
    ));
    setInputValue('trip-departure-window-end', tripDateTimeLocalValue(
        routeDraft ? routeDraft.departureWindowEnd : plan.departure_window_end
    ));
    setInputValue('trip-return-window-start', tripDateTimeLocalValue(
        routeDraft ? routeDraft.returnWindowStart : plan.return_window_start
    ));
    setInputValue('trip-return-window-end', tripDateTimeLocalValue(
        routeDraft ? routeDraft.returnWindowEnd : plan.return_window_end
    ));
    setInputValue('trip-holidays', (header.holiday_dates || []).join(', '));
    setInputValue('trip-description', header.description || '');
    const avoidWeekends = document.getElementById('trip-avoid-weekends');
    if (avoidWeekends) avoidWeekends.checked = header.avoid_weekends !== false;
}

function parseHolidayInput(value) {
    return String(value || '')
        .split(/[\n,]+/)
        .map(item => item.trim())
        .filter(Boolean);
}

function readTripItineraryPayload() {
    const payload = {
        ...window.TripPlanningDraft?.itineraryPayload?.(),
        ...readTripPlanFormPayload(),
        stop_durations: readTripStopDurationPayload(),
    };
    // Calculating a route and choosing how the plan is planned are different
    // requests. The itinerary endpoints reject anything they do not declare, so
    // a plan-header field arriving here fails the whole preview.
    delete payload.planning_mode;
    return payload;
}

function numericOrNull(value) {
    if (value === undefined || value === null || value === '') return null;
    const number = Number(value);
    return Number.isFinite(number) ? number : null;
}
function tripDateTimeLocalValue(value) {
    const match = String(value || '').match(/^(\d{4}-\d{2}-\d{2})[T ](\d{2}):(\d{2})/);
    return match ? `${match[1]}T${match[2]}:${match[3]}` : '';
}

function setInputValue(id, value) {
    const el = document.getElementById(id);
    if (el) el.value = value;
}
