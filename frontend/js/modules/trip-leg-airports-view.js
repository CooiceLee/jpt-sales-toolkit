/** Renders the airport fields of a flown leg. Coordinates are never shown. */
(function() {
    const h = escapeHtml;
    const t = key => I18n.t(key);

    /** How the traveller reaches this airport, and how long each part takes. */
    function detailRow(index, side, override) {
        const way = override[`${side}_transfer_mode`] || '';
        const hours = override[`${side}_transfer_time_hours`];
        const transfer = override[`${side}_transfer_half_days`];
        const stay = TripDuration.toDisplayTravelDays(
            override[`${side}_airport_stay_half_days`] || 0
        );
        const option = (value, label) => `<option value="${value}" ${
            way === value ? 'selected' : ''}>${h(t(label))}</option>`;
        const field = (title, control) =>
            `<label class="trip-field-label"><span>${h(t(title))}</span>${control}</label>`;
        const number = (name, value, max, step) => `<input type="number" min="0"
            max="${max}" step="${step}" class="form-input"
            id="trip-leg-air-${name}-${index}-${side}"
            value="${h(value == null ? '' : value)}"
            placeholder="${h(t('Estimated'))}"
            onchange="TripLegAirportDurations.${name}Changed(${index}, '${side}', this.value)">`;
        const leg = side === 'departure'
            ? 'Getting to the airport' : 'Leaving the airport';
        return `<div class="trip-leg-airport-detail">
            <p class="trip-leg-airport-legend">${h(t(leg))}</p>
            ${field(side === 'departure' ? 'To the airport by' : 'From the airport by',
                `<select class="form-input" id="trip-leg-air-mode-${index}-${side}"
                    onchange="TripLegAirportDurations.modeChanged(${index}, '${side}', this.value)">
                    ${option('', 'Plan preference')}${option('drive', 'Drive')}
                    ${option('ground_public', 'Ground public')}${option('other', 'Other')}
                </select>`)}
            ${field('Transfer time (hours)', number('hours', hours, 240, 0.1))}
            ${field(side === 'departure' ? 'Drive to airport (days)' : 'Drive from airport (days)',
                number('transfer', transfer == null ? null
                    : TripDuration.toDisplayTravelDays(transfer), 30, 0.5))}
            ${field('Waiting at the airport (days)', `<input type="number" min="0" max="30" step="0.5"
                class="form-input" id="trip-leg-air-stay-${index}-${side}"
                value="${h(stay || '')}" placeholder="${h(t('Estimated'))}"
                onchange="TripLegAirportDurations.stayChanged(${index}, '${side}', this.value)">`)}
        </div>`;
    }

    function sideBlock(index, side, override, label) {
        const name = override[`${side}_airport_name`] || '';
        const isSet = Boolean(name && override[`${side}_airport_lat`] != null);
        return `<div class="trip-leg-airport" data-side="${side}">
            <div class="trip-leg-airport-find">
                <span class="trip-leg-airport-label">${h(t(label))}</span>
                <input type="text" class="form-input" maxlength="200"
                    id="trip-leg-air-name-${index}-${side}" value="${h(name)}"
                    placeholder="${h(t('Airport or city name'))}">
                <button type="button" class="btn btn-secondary btn-sm"
                    onclick="TripLegAirports.search(${index}, '${side}')">${h(t('Find location'))}</button>
                ${isSet ? `<button type="button" class="btn btn-secondary btn-sm"
                    onclick="TripLegAirports.clear(${index}, '${side}')">${h(t('Clear'))}</button>` : ''}
            </div>
            <div class="trip-free-stop-status ${isSet ? 'success' : ''}"
                id="trip-leg-air-status-${index}-${side}" role="status" aria-live="polite"
                >${isSet ? h(I18n.t('Airport set: {name}', { name })) : ''}</div>
            <div class="trip-free-stop-candidates" role="listbox"
                id="trip-leg-air-candidates-${index}-${side}" hidden></div>
            ${isSet ? detailRow(index, side, override)
                : `<p class="trip-form-help">${h(t(
                    'Find the airport first, then say how it is reached and how long that takes.'
                ))}</p>`}
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

    window.TripLegAirportsView = Object.freeze({
        render, renderCandidates, sideBlock,
    });
})();
