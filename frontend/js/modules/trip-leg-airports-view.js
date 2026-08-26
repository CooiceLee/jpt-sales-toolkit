/** Renders the airport fields of a flown leg. Coordinates are never shown. */
(function() {
    function sideBlock(index, side, override, label) {
        const name = override[`${side}_airport_name`] || '';
        const isSet = Boolean(name && override[`${side}_airport_lat`] != null);
        const stay = TripDuration.toDisplayTravelDays(
            override[`${side}_airport_stay_half_days`] || 0
        );
        const h = escapeHtml;
        const t = key => I18n.t(key);
        return `<div class="trip-leg-airport" data-side="${side}">
            <span class="trip-leg-airport-label">${h(t(label))}</span>
            <input type="text" class="form-input" maxlength="200"
                id="trip-leg-air-name-${index}-${side}" value="${h(name)}"
                placeholder="${h(t('Airport or city name'))}">
            <button type="button" class="btn btn-secondary btn-sm"
                onclick="TripLegAirports.search(${index}, '${side}')">${h(t('Find location'))}</button>
            <label class="trip-field-label"><span>${h(t('Stay (days)'))}</span>
                <input type="number" min="0" max="30" step="0.5" class="form-input"
                    id="trip-leg-air-stay-${index}-${side}" value="${h(stay || '')}"
                    ${isSet ? '' : 'disabled'}
                    onchange="TripLegAirports.stayChanged(${index}, '${side}', this.value)"></label>
            ${isSet ? `<button type="button" class="btn btn-secondary btn-sm"
                onclick="TripLegAirports.clear(${index}, '${side}')">${h(t('Clear'))}</button>` : ''}
            <div class="trip-free-stop-status ${isSet ? 'success' : ''}"
                id="trip-leg-air-status-${index}-${side}" role="status" aria-live="polite"
                >${isSet ? h(I18n.t('Airport set: {name}', { name })) : ''}</div>
            <div class="trip-free-stop-candidates" role="listbox"
                id="trip-leg-air-candidates-${index}-${side}" hidden></div>
        </div>`;
    }

    function render(index, override = {}, mode) {
        // Airports only make sense on a flown leg, and a leg only flies once the
        // traveller says so; other modes never route through an airport.
        if (mode !== 'flight') return '';
        return `<div class="trip-leg-airports">
            ${sideBlock(index, 'departure', override, 'Departure airport')}
            ${sideBlock(index, 'arrival', override, 'Arrival airport')}
        </div>`;
    }

    function renderCandidates(index, side, items = [], provider = '', report = () => {}) {
        const root = document.getElementById(`trip-leg-air-candidates-${index}-${side}`);
        if (!root) return;
        root.innerHTML = items.map((item, position) => {
            const isAirport = item.place_type === 'aerodrome';
            const badge = isAirport ? `<span class="trip-stop-kind">${escapeHtml(I18n.t('Airport'))}</span> ` : '';
            return `<button type="button" class="btn btn-secondary btn-sm" role="option"
                aria-selected="false" onclick="TripLegAirports.choose(${index}, '${side}', ${position})"
                >${badge}${escapeHtml(item.normalized_address || `${item.lat}, ${item.lng}`)}</button>`;
        }).join('');
        root.hidden = !items.length;
        if (items.length) {
            report(I18n.t('{count} locations found via {provider}. Choose the airport.',
                { count: items.length, provider: provider || I18n.t('External service') }), 'success');
        }
    }

    window.TripLegAirportsView = Object.freeze({ render, renderCandidates });
})();
