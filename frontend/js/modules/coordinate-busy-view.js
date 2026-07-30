/** Keep geocoding and coordinate persistence mutually exclusive in one editor. */
function syncCoordinateActionButtons() {
    const busy = isCoordinateGeocodeInFlight() || isCoordinateSaveInFlight();
    const geocode = document.getElementById('coord-geocode-btn');
    const save = coordinateSaveButton();
    if (geocode) geocode.disabled = busy;
    if (save) save.disabled = busy;
}

function setCoordinateEditorSaving(request, saving) {
    const controls = document.querySelectorAll?.('#coordinate-modal input, #coordinate-modal button') || [];
    controls.forEach(control => {
        if (saving && !control.disabled) {
            control.disabled = true;
            control.dataset.coordinateSaveLock = String(request.requestEpoch);
        } else if (!saving
            && control.dataset.coordinateSaveLock === String(request.requestEpoch)) {
            control.disabled = false;
            delete control.dataset.coordinateSaveLock;
        }
    });
    syncCoordinateActionButtons();
}

function resetCoordinateEditorLocks() {
    const controls = document.querySelectorAll?.('#coordinate-modal input, #coordinate-modal button') || [];
    controls.forEach(control => {
        if (control.dataset.coordinateSaveLock) {
            control.disabled = false;
            delete control.dataset.coordinateSaveLock;
        }
    });
    syncCoordinateActionButtons();
}
