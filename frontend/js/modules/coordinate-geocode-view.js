function ensureCoordinateGeocodeControls() {
    const countryGroup = document.getElementById('coord-country')?.closest('.form-group');
    if (countryGroup && !document.getElementById('coord-postal-code')) {
        const group = document.createElement('div');
        group.className = 'form-group';
        group.innerHTML = `
            <label class="form-label">${coordinateText('Postal Code')}</label>
            <input type="text" id="coord-postal-code" class="form-input"
                placeholder="${coordinateText('Postal Code')}" oninput="clearCoordinateGeocodeResult()">
        `;
        countryGroup.parentElement.insertBefore(group, countryGroup);
    }
    const actions = document.querySelector('#coordinate-modal .coord-address-actions');
    if (actions && !document.getElementById('coord-geocode-candidates')) {
        const candidates = document.createElement('div');
        candidates.id = 'coord-geocode-candidates';
        candidates.hidden = true;
        candidates.setAttribute('role', 'listbox');
        candidates.setAttribute('aria-label', coordinateText('Address candidates'));
        candidates.style.cssText = 'margin:-4px 0 14px;display:grid;gap:6px;max-height:150px;overflow:auto;';
        actions.insertAdjacentElement('afterend', candidates);
    }
}

function setCoordinateGeocodeResult(message, status = '') {
    const result = document.getElementById('coord-geocode-result');
    if (!result) return;
    result.textContent = message || '';
    result.className = `coord-geocode-result${status ? ` ${status}` : ''}`;
}

function resetCoordinateGeocodeButton() {
    const button = document.getElementById('coord-geocode-btn');
    if (!button) return;
    button.textContent = coordinateText('Find on map');
    delete button.dataset.coordinateRequestEpoch;
    syncCoordinateActionButtons();
}

function coordinateSaveButton() {
    return document.querySelector('#coordinate-modal .modal-footer .btn-primary');
}

function resetCoordinateSaveButton() {
    const button = coordinateSaveButton();
    if (!button) return;
    delete button.dataset.coordinateSaveEpoch;
    syncCoordinateActionButtons();
}

window.clearCoordinateGeocodeResult = function() {
    invalidateCoordinateGeocode();
    coordinateEditState.normalizedAddress = null;
    coordinateEditState.geocodeProvider = null;
    coordinateEditState.candidates = [];
    setCoordinateGeocodeResult('');
    renderCoordinateCandidates([]);
    resetCoordinateGeocodeButton();
};

function renderCoordinateCandidates(candidates) {
    const container = document.getElementById('coord-geocode-candidates');
    if (!container) return;
    container.hidden = !candidates.length;
    container.style.display = candidates.length ? 'grid' : 'none';
    container.innerHTML = candidates.map((candidate, index) => `
        <button type="button" class="btn btn-secondary btn-sm"
            role="option" onclick="applyCoordinateCandidate(${index})"
            style="text-align:left;justify-content:flex-start;white-space:normal;">
            ${escapeHtml(candidate.normalized_address || `${candidate.lat}, ${candidate.lng}`)}
            · ${escapeHtml(candidate.confidence || '')}
        </button>
    `).join('');
}

window.applyCoordinateCandidate = function(index) {
    if (isCoordinateSaveInFlight()) return;
    const candidate = coordinateEditState.candidates[index];
    if (!candidate) return;
    const lat = Number(candidate.lat);
    const lng = Number(candidate.lng);
    if (!Number.isFinite(lat) || !Number.isFinite(lng)) return;
    setCoordinateField('coord-lat', lat.toFixed(6));
    setCoordinateField('coord-lng', lng.toFixed(6));
    coordinateEditState.normalizedAddress = candidate.normalized_address || null;
    updateCoordinateMarker(true);
    const label = candidate.normalized_address || `${lat.toFixed(6)}, ${lng.toFixed(6)}`;
    const provider = coordinateEditState.geocodeProvider;
    setCoordinateGeocodeResult(
        provider
            ? coordinateText('Selected via {provider}: {address}', { provider, address: label })
            : coordinateText('Selected: {address}', { address: label }),
        'success'
    );
};

function bindCoordinateMarkerDrag(marker) {
    marker.on('dragend', event => {
        if (isCoordinateSaveInFlight()) return;
        const position = event.target.getLatLng();
        clearCoordinateGeocodeResult();
        document.getElementById('coord-lat').value = position.lat.toFixed(6);
        document.getElementById('coord-lng').value = position.lng.toFixed(6);
    });
}
