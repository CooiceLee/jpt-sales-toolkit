/** Search-only airport entry for a flown leg. Coordinates are never typed. */
(function() {
    const SIDES = ['departure', 'arrival'];
    const FIELDS = SIDES.flatMap(side => [
        `${side}_airport_name`, `${side}_airport_lat`,
        `${side}_airport_lng`, `${side}_airport_stay_half_days`,
    ]);
    const candidates = new Map();
    const el = id => document.getElementById(id);
    const key = (index, side) => `${index}:${side}`;

    function pick(override = {}) {
        const kept = {};
        FIELDS.forEach(field => {
            if (override?.[field] != null) kept[field] = override[field];
        });
        return kept;
    }
    function legFor(index) { return State.currentTripPlan?.legs?.[index] || null; }
    function status(index, side, message, kind = '') {
        const node = el(`trip-leg-air-status-${index}-${side}`);
        if (!node) return;
        node.className = `trip-free-stop-status ${kind}`.trim();
        node.textContent = message ? I18n.t(message) : '';
    }
    function renderCandidates(index, side, items = [], provider = '') {
        candidates.set(key(index, side), items);
        TripLegAirportsView.renderCandidates(index, side, items, provider,
            (message, kind) => status(index, side, message, kind));
    }
    function anchorRegion(leg, side) {
        // The country is only a hint: a traveller may fly into a neighbouring
        // country, so it must never exclude an otherwise valid airport.
        const stopId = side === 'departure' ? leg.from_stop_id : leg.to_stop_id;
        const stop = (State.currentTripPlan?.stops || []).find(
            item => String(item.id) === String(stopId)
        );
        return { city: stop?.city || '', country: stop?.country || '' };
    }
    async function search(index, side) {
        const leg = legFor(index);
        const text = el(`trip-leg-air-name-${index}-${side}`)?.value?.trim();
        if (!leg || !text) {
            status(index, side, 'Enter an airport or city name first.', 'error');
            return;
        }
        const region = anchorRegion(leg, side);
        if (typeof navigator !== 'undefined' && navigator.onLine === false) {
            status(index, side, 'Location search is unavailable offline.', 'error');
            return;
        }
        status(index, side, 'Searching location...', 'loading');
        renderCandidates(index, side, []);
        // A city name finds every airport that serves it, which is what a
        // traveller actually wants; the country only helps some places, so it is
        // one attempt among several rather than a hard filter.
        const bare = text.replace(/机场|機場|airport/gi, '').trim() || text;
        const attempts = [
            { address: `${bare} airport`, country: region.country },
            { address: `${bare} airport` },
            { address: text, country: region.country },
            { address: text },
        ];
        try {
            let provider = '';
            let found = [];
            let lastError = null;
            for (const query of attempts) {
                const result = await ApiClient.searchGeocode(query, 5)
                    .catch(error => { lastError = error; return null; });
                if (!result) continue;
                provider = provider || result.provider || '';
                found = airportsFirst(result.candidates || []);
                if (found.some(item => item.place_type === 'aerodrome')) break;
            }
            renderCandidates(index, side, found.slice(0, 8), provider);
            if (found.length) return;
            // Never let a failing request look like an empty result.
            if (lastError) throw lastError;
            status(index, side, 'No matching airport found. Try the city name, or the English or IATA name.', 'error');
        } catch (error) {
            console.error('Airport search error:', error);
            status(index, side, 'Location search failed. Check the network.', 'error');
        }
    }
    function airportsFirst(items) {
        const seen = new Set();
        return items
            .filter(item => {
                const lat = Number(item.lat);
                const lng = Number(item.lng);
                if (!Number.isFinite(lat) || !Number.isFinite(lng)) return false;
                const token = `${lat.toFixed(4)},${lng.toFixed(4)}`;
                if (seen.has(token)) return false;
                seen.add(token);
                return true;
            })
            .sort((left, right) => (right.place_type === 'aerodrome')
                - (left.place_type === 'aerodrome'));
    }
    function choose(index, side, position) {
        const leg = legFor(index);
        const item = (candidates.get(key(index, side)) || [])[position];
        if (!leg || !item) return;
        const label = el(`trip-leg-air-name-${index}-${side}`)?.value?.trim()
            || item.normalized_address;
        TripPlanningDraft.change(draft => {
            const current = draft.legOverrides[leg.leg_key] || {};
            draft.legOverrides[leg.leg_key] = {
                ...current,
                selected_mode: current.selected_mode || 'flight',
                [`${side}_airport_name`]: label,
                [`${side}_airport_lat`]: Number(Number(item.lat).toFixed(6)),
                [`${side}_airport_lng`]: Number(Number(item.lng).toFixed(6)),
            };
        });
        status(index, side, I18n.t('Airport set: {name}', { name: label }), 'success');
        renderCandidates(index, side, []);
        TripTransportActions.schedulePreview();
    }
    function clear(index, side) {
        const leg = legFor(index);
        if (!leg) return;
        TripPlanningDraft.change(draft => {
            const current = { ...(draft.legOverrides[leg.leg_key] || {}) };
            [`${side}_airport_name`, `${side}_airport_lat`, `${side}_airport_lng`,
             `${side}_airport_stay_half_days`].forEach(field => { current[field] = null; });
            draft.legOverrides[leg.leg_key] = current;
        });
        status(index, side, '');
        TripTransportActions.schedulePreview();
    }
    function stayChanged(index, side, raw) {
        const leg = legFor(index);
        const halfDays = TripDuration.parseDisplayTravelDays(raw);
        if (!leg) return;
        if (raw !== '' && halfDays == null) {
            status(index, side, 'Stay must be 0 to 30 days in 0.5-day steps.', 'error');
            return;
        }
        TripPlanningDraft.change(draft => {
            draft.legOverrides[leg.leg_key] = {
                ...(draft.legOverrides[leg.leg_key] || {}),
                [`${side}_airport_stay_half_days`]: halfDays || 0,
            };
        });
        TripTransportActions.schedulePreview();
    }
    window.TripLegAirports = Object.freeze({
        pick, search, choose, clear, stayChanged, FIELDS,
    });
})();
