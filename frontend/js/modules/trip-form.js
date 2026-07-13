// ===== v0.7 Trip Planner =====
function getTripFilters() {
    return {
        region: document.getElementById('trip-region')?.value || '',
        sales_stage: document.getElementById('trip-stage')?.value || '',
        limit: State.tripCandidatePagination.limit,
        offset: State.tripCandidatePagination.offset
    };
}

function readTripPlanFormPayload() {
    return {
        title: document.getElementById('trip-title')?.value?.trim() || `Trip Plan ${new Date().toLocaleDateString('en-US')}`,
        start_date: document.getElementById('trip-start-date')?.value || null,
        end_date: document.getElementById('trip-end-date')?.value || null,
        region: document.getElementById('trip-region')?.value || null,
        origin_name: document.getElementById('trip-origin-name')?.value?.trim() || null,
        origin_lat: numericOrNull(document.getElementById('trip-origin-lat')?.value),
        origin_lng: numericOrNull(document.getElementById('trip-origin-lng')?.value),
        destination_name: document.getElementById('trip-destination-name')?.value?.trim() || null,
        destination_lat: numericOrNull(document.getElementById('trip-destination-lat')?.value),
        destination_lng: numericOrNull(document.getElementById('trip-destination-lng')?.value),
        travel_mode: document.getElementById('trip-travel-mode')?.value || 'auto',
        avoid_weekends: Boolean(document.getElementById('trip-avoid-weekends')?.checked),
        holiday_dates: parseHolidayInput(document.getElementById('trip-holidays')?.value || ''),
        description: document.getElementById('trip-description')?.value?.trim() || null
    };
}

function populateTripPlanForm(plan) {
    if (!plan) return;
    setInputValue('trip-title', plan.title || '');
    setInputValue('trip-start-date', plan.start_date || '');
    setInputValue('trip-end-date', plan.end_date || '');
    setInputValue('trip-origin-name', plan.origin_name || '');
    setInputValue('trip-origin-lat', plan.origin_lat ?? '');
    setInputValue('trip-origin-lng', plan.origin_lng ?? '');
    setInputValue('trip-destination-name', plan.destination_name || '');
    setInputValue('trip-destination-lat', plan.destination_lat ?? '');
    setInputValue('trip-destination-lng', plan.destination_lng ?? '');
    setInputValue('trip-travel-mode', plan.travel_mode || 'auto');
    setInputValue('trip-holidays', (plan.holiday_dates || []).join(', '));
    setInputValue('trip-description', plan.description || '');
    const avoidWeekends = document.getElementById('trip-avoid-weekends');
    if (avoidWeekends) avoidWeekends.checked = plan.avoid_weekends !== false;
}

function parseHolidayInput(value) {
    return String(value || '')
        .split(/[\n,]+/)
        .map(item => item.trim())
        .filter(Boolean);
}

function readTripStopStayPayload() {
    const stays = {};
    (State.currentTripPlan?.stops || []).forEach(stop => {
        const value = Number(document.getElementById(`stop-stay-${stop.id}`)?.value || stop.stay_days || 1);
        stays[stop.id] = Number.isFinite(value) ? Math.max(1, Math.min(30, Math.round(value))) : 1;
    });
    return stays;
}

function numericOrNull(value) {
    if (value === undefined || value === null || value === '') return null;
    const number = Number(value);
    return Number.isFinite(number) ? number : null;
}

function setInputValue(id, value) {
    const el = document.getElementById(id);
    if (el) el.value = value;
}

