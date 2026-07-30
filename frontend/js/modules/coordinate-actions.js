window.updateCoordinateMarker = function(preserveGeocodeResult = false) {
    if (isCoordinateSaveInFlight()) return;
    if (!preserveGeocodeResult) clearCoordinateGeocodeResult();
    const lat = parseFloat(document.getElementById('coord-lat').value);
    const lng = parseFloat(document.getElementById('coord-lng').value);

    if (isNaN(lat) || isNaN(lng) || !coordinatePickerMap) return;

    if (coordinatePickerMarker) {
        coordinatePickerMarker.setLatLng([lat, lng]);
    } else {
        coordinatePickerMarker = L.marker([lat, lng], { draggable: true }).addTo(coordinatePickerMap);
        bindCoordinateMarkerDrag(coordinatePickerMarker);
    }
    coordinatePickerMap.setView([lat, lng], 10);
};

window.geocodeCoordinateAddress = async function() {
    const fields = readCoordinateAddressFields();
    if (!fields.address && !fields.city && !fields.postal_code && !fields.country) {
        alert(coordinateText('Please enter an address, city, postal code, or country first.'));
        return;
    }
    const request = beginCoordinateGeocodeRequest(fields);
    if (!request) return;
    syncCoordinateActionButtons();

    const btn = document.getElementById('coord-geocode-btn');
    const originalText = btn?.textContent || coordinateText('Find on map');
    if (btn) {
        btn.disabled = true;
        btn.textContent = coordinateText('Finding...');
        btn.dataset.coordinateRequestEpoch = String(request.requestEpoch);
    }
    setCoordinateGeocodeResult(coordinateText('Searching address...'));
    renderCoordinateCandidates([]);

    try {
        const result = await ApiClient.searchGeocode(fields, 5);
        if (!isCoordinateGeocodeRequestCurrent(request)) return;
        const candidates = (result.candidates || []).filter(candidate =>
            Number.isFinite(Number(candidate.lat)) && Number.isFinite(Number(candidate.lng))
        );
        coordinateEditState.geocodeProvider = result.provider || null;
        coordinateEditState.candidates = candidates;
        renderCoordinateCandidates(candidates);
        if (!candidates.length) {
            coordinateEditState.normalizedAddress = null;
            setCoordinateGeocodeResult(
                coordinateText('No matching address was found. Add a postal code/country or place the marker manually.'),
                'error'
            );
            return;
        }
        applyCoordinateCandidate(0);
        if (candidates.length > 1) {
            setCoordinateGeocodeResult(
                coordinateText('Found {count} matches via {provider}. The first is selected; choose another below if needed.', {
                    count: candidates.length,
                    provider: result.provider || coordinateText('External service')
                }),
                'success'
            );
        }
    } catch (err) {
        if (!isCoordinateGeocodeRequestCurrent(request)) return;
        console.error('Address geocode error:', err);
        coordinateEditState.normalizedAddress = null;
        coordinateEditState.geocodeProvider = null;
        coordinateEditState.candidates = [];
        renderCoordinateCandidates([]);
        const code = err?.details?.code || (err?.message === 'Failed to fetch' ? 'network_error' : 'unknown');
        const messages = {
            tls_error: coordinateText('Secure connection to the map service failed. Restart the updated app and retry.'),
            timeout: coordinateText('The map service timed out. Please retry.'),
            network_error: coordinateText('The map service could not be reached. Check the network and retry.'),
            provider_quota: coordinateText('The map service request limit was reached. Please try again later.'),
            provider_auth: coordinateText('The configured map service key or permission is invalid.'),
            provider_disabled: coordinateText('The selected map service is not configured on this device.'),
            invalid_request: coordinateText('Enter an address, city, postal code, or country.'),
            unknown: coordinateText('The address search service failed. You can retry or place the marker manually.')
        };
        const message = messages[code] || err?.message || messages.unknown;
        setCoordinateGeocodeResult(message, 'error');
    } finally {
        const isCurrent = isCoordinateGeocodeRequestCurrent(request);
        finishCoordinateGeocodeRequest(request);
        if (btn && isCurrent
            && btn.dataset.coordinateRequestEpoch === String(request.requestEpoch)) {
            btn.textContent = originalText;
            delete btn.dataset.coordinateRequestEpoch;
            syncCoordinateActionButtons();
        }
    }
};

window.closeCoordinateModal = function(force = false) {
    if (isCoordinateSaveInFlight() && !force) return;
    hideModal('coordinate-modal');
    invalidateCoordinateEdit();
    resetCoordinateEditorLocks();
    setCoordinateGeocodeResult('');
    renderCoordinateCandidates([]);
    resetCoordinateGeocodeButton();
    resetCoordinateSaveButton();
    if (coordinatePickerMap) {
        coordinatePickerMap.remove();
        coordinatePickerMap = null;
        coordinatePickerMarker = null;
    }
};
