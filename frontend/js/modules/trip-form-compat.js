/** Compatibility callable for modules that still use the former stop-stay name. */
function readTripStopStayPayload(options = {}) {
    return readTripStopDurationPayload(options);
}
