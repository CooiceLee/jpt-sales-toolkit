// ===== Coordinate Correction =====
let coordinatePickerMap = null;
let coordinatePickerMarker = null;
let coordinateEditGeneration = 0;
let coordinateGeocodeRequestEpoch = 0;
let coordinateSaveRequestEpoch = 0;
let coordinateGeocodeInFlightEpoch = null;
let coordinateSaveInFlightEpoch = null;
let coordinateEditState = {
    customerId: null,
    customerName: null,
    customerRowVersion: null,
    normalizedAddress: null,
    geocodeProvider: null,
    candidates: [],
    generation: 0
};
function beginCoordinateEdit(customerId, customerName, customerRowVersion = null) {
    coordinateEditGeneration += 1;
    coordinateGeocodeRequestEpoch += 1;
    coordinateSaveRequestEpoch += 1;
    coordinateGeocodeInFlightEpoch = null;
    coordinateSaveInFlightEpoch = null;
    coordinateEditState = {
        customerId,
        customerName,
        customerRowVersion: customerRowVersion != null
            && customerRowVersion !== ''
            && Number.isInteger(Number(customerRowVersion))
            && Number(customerRowVersion) >= 1
            ? Number(customerRowVersion) : null,
        normalizedAddress: null,
        geocodeProvider: null,
        candidates: [],
        generation: coordinateEditGeneration
    };
    return coordinateEditGeneration;
}
function invalidateCoordinateEdit() {
    coordinateEditGeneration += 1;
    coordinateGeocodeRequestEpoch += 1;
    coordinateSaveRequestEpoch += 1;
    coordinateGeocodeInFlightEpoch = null;
    coordinateSaveInFlightEpoch = null;
    coordinateEditState = {
        customerId: null,
        customerName: null,
        customerRowVersion: null,
        normalizedAddress: null,
        geocodeProvider: null,
        candidates: [],
        generation: coordinateEditGeneration
    };
}
function invalidateCoordinateGeocode() {
    coordinateGeocodeRequestEpoch += 1;
    coordinateGeocodeInFlightEpoch = null;
    return coordinateGeocodeRequestEpoch;
}
function beginCoordinateGeocodeRequest(fields) {
    if (isCoordinateSaveInFlight()) return null;
    const request = Object.freeze({
        customerId: coordinateEditState.customerId,
        generation: coordinateEditState.generation,
        requestEpoch: ++coordinateGeocodeRequestEpoch,
        fields: Object.freeze({ ...fields })
    });
    coordinateGeocodeInFlightEpoch = request.requestEpoch;
    return request;
}
function finishCoordinateGeocodeRequest(request) {
    if (coordinateGeocodeInFlightEpoch === request?.requestEpoch) {
        coordinateGeocodeInFlightEpoch = null;
    }
}
function isCoordinateGeocodeInFlight() {
    return coordinateGeocodeInFlightEpoch !== null;
}
function coordinateFieldsMatch(snapshot) {
    const current = readCoordinateAddressFields();
    return ['address', 'city', 'postal_code', 'country']
        .every(field => current[field] === snapshot[field]);
}
function isCoordinateGeocodeRequestCurrent(request) {
    return !!request
        && coordinateEditState.customerId === request.customerId
        && coordinateEditState.generation === request.generation
        && coordinateGeocodeRequestEpoch === request.requestEpoch
        && coordinateFieldsMatch(request.fields);
}
function beginCoordinateSaveRequest(snapshot) {
    if (isCoordinateGeocodeInFlight() || isCoordinateSaveInFlight()) return null;
    const request = Object.freeze({
        customerId: coordinateEditState.customerId,
        customerRowVersion: coordinateEditState.customerRowVersion,
        generation: coordinateEditState.generation,
        requestEpoch: ++coordinateSaveRequestEpoch,
        snapshot: Object.freeze({ ...snapshot })
    });
    coordinateSaveInFlightEpoch = request.requestEpoch;
    return request;
}

function finishCoordinateSaveRequest(request) {
    if (coordinateSaveInFlightEpoch === request?.requestEpoch) {
        coordinateSaveInFlightEpoch = null;
    }
}

function isCoordinateSaveInFlight() {
    return coordinateSaveInFlightEpoch !== null;
}

function isCoordinateSaveRequestCurrent(request) {
    return !!request
        && coordinateEditState.customerId === request.customerId
        && coordinateEditState.generation === request.generation
        && coordinateSaveRequestEpoch === request.requestEpoch
        && coordinateSaveInFlightEpoch === request.requestEpoch;
}

function coordinateText(text, params = {}) {
    return window.I18n?.t ? I18n.t(text, params) : Object.entries(params)
        .reduce((value, [key, item]) => value.replace(`{${key}}`, item), text);
}
