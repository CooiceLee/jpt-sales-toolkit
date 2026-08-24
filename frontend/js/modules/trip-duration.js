/** Half-day duration contract shared by customer and personal itinerary stops. */
(function() {
    const MIN = 1;
    const MAX = 60;

    function normalizeHalfDays(value, fallback = MIN) {
        const number = Number(value);
        if (!Number.isFinite(number)) return normalizeHalfDays(fallback, MIN);
        return Math.max(MIN, Math.min(MAX, Math.round(number)));
    }

    function fromDisplayDays(value, fallback = MIN) {
        const number = Number(value);
        return Number.isFinite(number)
            ? normalizeHalfDays(number * 2, fallback)
            : normalizeHalfDays(fallback);
    }

    function parseDisplayDays(value) {
        const raw = String(value ?? '').trim();
        if (!raw) return null;
        const number = Number(raw);
        const slots = number * 2;
        return Number.isFinite(number) && number >= MIN / 2 && number <= MAX / 2
            && Number.isInteger(slots) ? slots : null;
    }

    function normalizeTravelHalfDays(value, fallback = 0) {
        const number = Number(value);
        if (!Number.isFinite(number)) {
            const safeFallback = Number(fallback);
            return Number.isFinite(safeFallback) ? Math.max(0, Math.min(MAX, Math.round(safeFallback))) : 0;
        }
        return Math.max(0, Math.min(MAX, Math.round(number)));
    }

    function fromDisplayTravelDays(value, fallback = 0) {
        const number = Number(value);
        return Number.isFinite(number)
            ? normalizeTravelHalfDays(number * 2, fallback)
            : normalizeTravelHalfDays(fallback);
    }

    function parseDisplayTravelDays(value) {
        const raw = String(value ?? '').trim();
        if (!raw) return null;
        const number = Number(raw);
        const slots = number * 2;
        return Number.isFinite(number) && number >= 0 && number <= MAX / 2
            && Number.isInteger(slots) ? slots : null;
    }

    function toDisplayTravelDays(value, fallback = 0) {
        return normalizeTravelHalfDays(value, fallback) / 2;
    }

    function toDisplayDays(value, fallback = MIN) {
        return normalizeHalfDays(value, fallback) / 2;
    }

    function readStopDuration(stop = {}, fallback = MIN) {
        if (stop.duration_half_days != null) {
            return normalizeHalfDays(stop.duration_half_days, fallback);
        }
        if (stop.stay_days != null) {
            return fromDisplayDays(stop.stay_days, fallback);
        }
        return normalizeHalfDays(fallback);
    }

    function label(value) {
        return I18n.t('{count} days', { count: toDisplayDays(value) });
    }

    function transportPriority(value, legacyMode, modes, defaults) {
        const items = Array.isArray(value) ? value : [];
        const clean = [...new Set(items.filter(item => modes.includes(item)))];
        if (clean.length) return clean;
        return modes.includes(legacyMode) ? [legacyMode] : [...defaults];
    }

    function cleanLegOverride(value = {}, modes = []) {
        const mode = modes.includes(value.selected_mode) ? value.selected_mode : null;
        const number = key => {
            if (value[key] == null || value[key] === '') return null;
            const parsed = Number(value[key]);
            return Number.isFinite(parsed) && parsed >= 0 ? parsed : null;
        };
        const legacyDays = number('manual_travel_days');
        const explicitHalfDays = number('manual_travel_half_days');
        return {
            selected_mode: mode,
            mode_locked: Boolean(value.mode_locked),
            manual_distance_km: number('manual_distance_km'),
            manual_time_hours: number('manual_time_hours'),
            manual_travel_half_days: explicitHalfDays == null
                ? (legacyDays == null ? null : fromDisplayTravelDays(legacyDays))
                : normalizeTravelHalfDays(explicitHalfDays),
            notes: String(value.notes || '').trim() || null,
        };
    }

    window.TripDuration = Object.freeze({
        MIN, MAX, normalizeHalfDays, fromDisplayDays, parseDisplayDays, toDisplayDays,
        normalizeTravelHalfDays, fromDisplayTravelDays, parseDisplayTravelDays, toDisplayTravelDays,
        readStopDuration, label,
    });
    window.TripRouteValues = Object.freeze({ transportPriority, cleanLegOverride });
})();
