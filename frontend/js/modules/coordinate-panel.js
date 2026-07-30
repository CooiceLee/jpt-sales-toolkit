window.openCoordinateCorrectionFromMap = function(customerId) {
    const point = (State.mapData?.points || []).find(item => item.customer_id === customerId);
    if (!point) {
        alert(coordinateText('Customer location data is no longer available. Please refresh the map.'));
        return;
    }
    if (!point.can_edit) return;

    openCoordinateCorrection(
        point.customer_id,
        point.customer_name,
        point.lat,
        point.lng,
        {
            address: point.address,
            city: point.city,
            postal_code: point.postal_code,
            country: point.country,
            normalized_address: point.normalized_address,
            row_version: point.customer_row_version
        }
    );
};

window.openCoordinateCorrection = async function(customerId, customerName, currentLat, currentLng, details = {}) {
    const generation = beginCoordinateEdit(customerId, customerName, details.row_version);
    coordinateEditState.normalizedAddress = details.normalized_address || null;
    ensureCoordinateGeocodeControls();
    resetCoordinateEditorLocks();
    resetCoordinateGeocodeButton();
    resetCoordinateSaveButton();

    // Set initial values
    document.getElementById('coord-customer-name').textContent = customerName;
    document.getElementById('coord-lat').value = currentLat ?? '';
    document.getElementById('coord-lng').value = currentLng ?? '';
    setCoordinateField('coord-address', details.address);
    setCoordinateField('coord-city', details.city);
    setCoordinateField('coord-postal-code', details.postal_code);
    setCoordinateField('coord-country', details.country);
    setCoordinateGeocodeResult('');
    renderCoordinateCandidates([]);

    // Show modal
    showModal('coordinate-modal');

    // Initialize map picker after modal is visible
    setTimeout(() => initCoordinatePickerMap(
        currentLat, currentLng, customerId, generation
    ), 100);
};

function initCoordinatePickerMap(lat, lng, customerId, generation) {
    if (coordinateEditState.customerId !== customerId
        || coordinateEditState.generation !== generation) return;
    const mapContainer = document.getElementById('coord-map-picker');
    if (!mapContainer) return;

    // Clear existing map
    if (coordinatePickerMap) {
        coordinatePickerMap.remove();
        coordinatePickerMap = null;
        coordinatePickerMarker = null;
    }

    // Default to center if no coordinates
    const existingPair = MapSupport.coordinatePair(lat, lng);
    const hasCoordinates = !!existingPair;
    const centerLat = hasCoordinates ? existingPair[0] : 35;
    const centerLng = hasCoordinates ? existingPair[1] : 20;
    const zoom = hasCoordinates ? 10 : 2;

    coordinatePickerMap = L.map('coord-map-picker').setView([centerLat, centerLng], zoom);
    MapSupport.addTileLayer(coordinatePickerMap, {
        containerId: 'coord-map-picker',
        style: 'standard'
    });

    // Add marker if coordinates exist
    if (hasCoordinates) {
        coordinatePickerMarker = L.marker([centerLat, centerLng], { draggable: true }).addTo(coordinatePickerMap);
        bindCoordinateMarkerDrag(coordinatePickerMarker);
    }

    // Click to place/move marker
    coordinatePickerMap.on('click', function(e) {
        if (isCoordinateSaveInFlight()) return;
        const { lat, lng } = e.latlng;
        clearCoordinateGeocodeResult();
        document.getElementById('coord-lat').value = lat.toFixed(6);
        document.getElementById('coord-lng').value = lng.toFixed(6);

        if (coordinatePickerMarker) {
            coordinatePickerMarker.setLatLng([lat, lng]);
        } else {
            coordinatePickerMarker = L.marker([lat, lng], { draggable: true }).addTo(coordinatePickerMap);
            bindCoordinateMarkerDrag(coordinatePickerMarker);
        }
    });

    // Force map to recalculate size
    coordinatePickerMap.invalidateSize();
}
