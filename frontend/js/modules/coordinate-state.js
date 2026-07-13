// ===== Coordinate Correction =====
let coordinatePickerMap = null;
let coordinatePickerMarker = null;
let coordinateEditState = { customerId: null, customerName: null, normalizedAddress: null };

function setCoordinateField(id, value) {
    const field = document.getElementById(id);
    if (field) {
        field.value = value ?? '';
    }
}

function readCoordinateAddressFields() {
    return {
        address: document.getElementById('coord-address')?.value?.trim() || '',
        city: document.getElementById('coord-city')?.value?.trim() || '',
        country: document.getElementById('coord-country')?.value?.trim() || ''
    };
}

function setCoordinateGeocodeResult(message, status = '') {
    const resultEl = document.getElementById('coord-geocode-result');
    if (!resultEl) return;
    resultEl.textContent = message || '';
    resultEl.className = `coord-geocode-result${status ? ` ${status}` : ''}`;
}

window.clearCoordinateGeocodeResult = function() {
    coordinateEditState.normalizedAddress = null;
    setCoordinateGeocodeResult('');
};

function buildCountryDisplayLookup() {
    const lookup = {
        codeToName: {},
        nameToName: {},
        aliases: { UK: 'GB', UAE: 'AE', USA: 'US' }
    };
    const regions = State.config?.regions?.regions || {};

    Object.values(regions).forEach(region => {
        Object.entries(region.countries || {}).forEach(([code, country]) => {
            const name = country?.name || code;
            lookup.codeToName[code.toUpperCase()] = name;
            if (country?.name) lookup.nameToName[country.name.toLowerCase()] = name;
            if (country?.name_cn) lookup.nameToName[country.name_cn.toLowerCase()] = name;
        });
    });

    return lookup;
}

function normalizeCoordinateCountryForSave(country) {
    const raw = String(country || '').trim();
    if (!raw) return '';

    const lookup = buildCountryDisplayLookup();
    const upper = raw.toUpperCase();
    const code = lookup.aliases[upper] || upper;
    if (lookup.codeToName[code]) return lookup.codeToName[code];

    return lookup.nameToName[raw.toLowerCase()] || raw;
}

function bindCoordinateMarkerDrag(marker) {
    marker.on('dragend', function(e) {
        const pos = e.target.getLatLng();
        document.getElementById('coord-lat').value = pos.lat.toFixed(6);
        document.getElementById('coord-lng').value = pos.lng.toFixed(6);
    });
}

