window.saveCoordinates = async function() {
    if (isCoordinateGeocodeInFlight()) {
        alert(coordinateText('Wait for address search to finish or cancel it before saving.'));
        return;
    }
    const lat = parseFloat(document.getElementById('coord-lat').value);
    const lng = parseFloat(document.getElementById('coord-lng').value);
    const { address, city, postal_code, country } = readCoordinateAddressFields();
    if (isNaN(lat) || isNaN(lng)) {
        alert(coordinateText('Please enter valid coordinates or click on the map.'));
        return;
    }
    if (lat < -90 || lat > 90 || lng < -180 || lng > 180) {
        alert(coordinateText('Coordinates out of range. Latitude: -90 to 90, longitude: -180 to 180.'));
        return;
    }

    if (!coordinateEditState.customerRowVersion) {
        alert(coordinateText('Coordinate data version is unavailable. Close this window and reopen it before saving.'));
        return;
    }
    if (!coordinateEditState.customerId) return;
    const snapshot = {
        lat, lng, address, city, postal_code, country,
        normalized_address: coordinateEditState.normalizedAddress || ''
    };
    const request = beginCoordinateSaveRequest(snapshot);
    if (!request) return;
    const payload = {
        lat, lng,
        address,
        city,
        postal_code,
        country: normalizeCoordinateCountryForSave(country),
        normalized_address: snapshot.normalized_address,
        geocode_source: 'manual',
        geocode_confidence: 'high',
        geocode_locked: true
    };

    const button = coordinateSaveButton();
    if (button) {
        button.disabled = true;
        button.dataset.coordinateSaveEpoch = String(request.requestEpoch);
    }
    setCoordinateEditorSaving(request, true);
    try {
        await ApiClient.updateCustomer(
            request.customerId, payload, request.customerRowVersion
        );
        if (!isCoordinateSaveRequestCurrent(request)) return;
        closeCoordinateModal(true);
        notify(coordinateText('Coordinates saved.'));
        if (document.getElementById('module-coordinate-review')?.classList.contains('active')) {
            applyCoordinateReviewData(await ApiClient.getMapData({}));
        } else if (document.getElementById('module-dashboard')?.classList.contains('active')) {
            await loadReviewMap();
        }
    } catch (err) {
        console.error('Save coordinates error:', err);
        if (!isCoordinateSaveRequestCurrent(request)) return;
        if (err?.name === 'ConflictError') {
            alert(coordinateText('Coordinate save conflict: this customer was updated elsewhere. The latest data will be loaded; please retry.'));
            closeCoordinateModal(true);
            await loadReviewMap();
            if (document.getElementById('module-coordinate-review')?.classList.contains('active')) {
                await loadCoordinateReview();
            }
        } else {
            alert(coordinateText('Error saving coordinates: {error}', {
                error: coordinateText(err?.message || 'Unknown error')
            }));
        }
    } finally {
        const isCurrent = isCoordinateSaveRequestCurrent(request);
        finishCoordinateSaveRequest(request);
        if (isCurrent) {
            setCoordinateEditorSaving(request, false);
            if (button?.dataset.coordinateSaveEpoch === String(request.requestEpoch)) {
                delete button.dataset.coordinateSaveEpoch;
            }
            syncCoordinateActionButtons();
        }
    }
};
