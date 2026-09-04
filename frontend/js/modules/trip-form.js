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
        // Sent as nothing on every save, so a plan that still carries the old
        // windows is cleared the first time it is saved rather than being
        // scheduled around dates nobody can see any more.
        departure_window_start: null,
        departure_window_end: null,
        return_window_start: null,
        return_window_end: null,
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
        // One way to plan a trip: as a team, of one person or of six.
        planning_mode: 'team',
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
    // A trip runs between the plan's own dates. Two more windows saying the
    // same thing were a second place to look and a second thing to keep in
    // step, so they are gone: the plan's start and end are the only answer.
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
