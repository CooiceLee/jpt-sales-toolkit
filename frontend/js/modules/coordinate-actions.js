window.updateCoordinateMarker = function() {
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
    const { address, city, country } = readCoordinateAddressFields();
    if (!address && !city && !country) {
        alert('Please enter an address, city, or country first.');
        return;
    }

    const btn = document.getElementById('coord-geocode-btn');
    const originalText = btn?.textContent || 'Find on map';
    if (btn) {
        btn.disabled = true;
        btn.textContent = 'Finding...';
    }
    setCoordinateGeocodeResult('Searching address...');

    try {
        const result = await ApiClient.geocode(address, city, country);
        const lat = Number(result.lat);
        const lng = Number(result.lng);
        if (!Number.isFinite(lat) || !Number.isFinite(lng)) {
            throw new Error('Address result did not include valid coordinates');
        }

        document.getElementById('coord-lat').value = lat.toFixed(6);
        document.getElementById('coord-lng').value = lng.toFixed(6);
        coordinateEditState.normalizedAddress = result.normalized_address || null;
        updateCoordinateMarker();

        const label = result.normalized_address || `${lat.toFixed(6)}, ${lng.toFixed(6)}`;
        setCoordinateGeocodeResult(`Found: ${label}`, 'success');
    } catch (err) {
        console.error('Address geocode error:', err);
        coordinateEditState.normalizedAddress = null;
        const message = 'Address not found. Check spelling, try English address text, add city/country, or place the marker manually.';
        setCoordinateGeocodeResult(message, 'error');
        alert(message);
    } finally {
        if (btn) {
            btn.disabled = false;
            btn.textContent = originalText;
        }
    }
};

window.saveCoordinates = async function() {
    const lat = parseFloat(document.getElementById('coord-lat').value);
    const lng = parseFloat(document.getElementById('coord-lng').value);
    const { address, city, country } = readCoordinateAddressFields();

    if (isNaN(lat) || isNaN(lng)) {
        alert('Please enter valid coordinates or click on the map');
        return;
    }

    if (lat < -90 || lat > 90 || lng < -180 || lng > 180) {
        alert('Coordinates out of range. Latitude: -90 to 90, Longitude: -180 to 180');
        return;
    }

    try {
        // Get current customer row_version
        const customer = await ApiClient.getCustomer(coordinateEditState.customerId);
        const payload = {
            lat: lat,
            lng: lng,
            geocode_source: 'manual',
            geocode_confidence: 'high',
            geocode_locked: true
        };

        if (address) payload.address = address;
        if (city) payload.city = city;
        const countryForSave = normalizeCoordinateCountryForSave(country);
        if (countryForSave) payload.country = countryForSave;
        if (coordinateEditState.normalizedAddress) {
            payload.normalized_address = coordinateEditState.normalizedAddress;
        }

        // Update with manual coordinates
        await ApiClient.updateCustomer(coordinateEditState.customerId, payload, customer.row_version);

        closeCoordinateModal();
        notify('Coordinates saved');

        // Refresh any coordinate views that may be visible.
        await loadReviewMap();
        if (document.getElementById('module-coordinate-review')?.classList.contains('active')) {
            await loadCoordinateReview();
        }
    } catch (err) {
        console.error('Save coordinates error:', err);
        if (err?.name === 'ConflictError') {
            alert('Coordinate save conflict: this customer was updated elsewhere. The latest data will be loaded; please retry.');
            closeCoordinateModal();
            await loadReviewMap();
            if (document.getElementById('module-coordinate-review')?.classList.contains('active')) {
                await loadCoordinateReview();
            }
        } else {
            alert('Error saving coordinates: ' + (err.message || 'Unknown error'));
        }
    }
};

window.closeCoordinateModal = function() {
    hideModal('coordinate-modal');
    coordinateEditState = { customerId: null, customerName: null, normalizedAddress: null };
    setCoordinateGeocodeResult('');
    if (coordinatePickerMap) {
        coordinatePickerMap.remove();
        coordinatePickerMap = null;
        coordinatePickerMarker = null;
    }
};

