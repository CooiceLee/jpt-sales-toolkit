/** Looking a visit's address up on the map, for the preparation editor.
 *
 * Split out of the actions module when the save lifecycle grew: searching for
 * a location and saving a briefing are different jobs with different rules
 * about what may still be touched when an answer arrives late.
 */
(function() {
    'use strict';

    let locationEpoch = 0;
    let candidates = [];
    const h = value => escapeHtml(value ?? '');

    function locationFields() {
        const values = {};
        document.querySelectorAll('[data-location-field]').forEach(input => {
            values[input.dataset.locationField] = input.value.trim();
        });
        return values;
    }

    async function searchLocation() {
        const fields = locationFields();
        if (![fields.address, fields.city, fields.postal_code, fields.country].some(Boolean)) {
            alert(I18n.t('Enter an address, city, postal code, or country first.')); return;
        }
        const epoch = ++locationEpoch;
        const planId = State.currentTripPlan?.id;
        const stopId = TripBriefingDraft.getStopId();
        const fingerprint = JSON.stringify(fields);
        const isCurrent = () => epoch === locationEpoch
            && planId === State.currentTripPlan?.id
            && stopId === TripBriefingDraft.getStopId()
            && fingerprint === JSON.stringify(locationFields());
        const status = document.getElementById('trip-briefing-location-status');
        const root = document.getElementById('trip-briefing-location-candidates');
        if (status) status.textContent = I18n.t('Searching location...');
        if (root) root.innerHTML = '';
        try {
            const result = await ApiClient.searchGeocode({
                address: fields.address, city: fields.city, postal_code: fields.postal_code, country: fields.country,
            }, 5);
            if (!isCurrent()) return;
            candidates = (result.candidates || []).filter(item => Number.isFinite(Number(item.lat)) && Number.isFinite(Number(item.lng)));
            if (root) root.innerHTML = candidates.map((item, index) => `<button type="button" class="btn btn-secondary btn-sm"
                onclick="TripBriefingActions.chooseLocation(${index})">${h(item.normalized_address || `${item.lat}, ${item.lng}`)}</button>`).join('');
            if (status) status.textContent = candidates.length
                ? I18n.t('Choose one result to confirm the custom visit coordinates.')
                : I18n.t('No matching location found. Refine the address or enter exact coordinates manually.');
        } catch (error) {
            if (!isCurrent()) return;
            console.error('Briefing location search error:', error);
            if (status) status.textContent = I18n.t('Location search failed. Check the network or enter coordinates manually.');
        }
    }

    function chooseLocation(index) {
        if (!candidates[index]) return;
        TripBriefingForm.setLocation(candidates[index]);
    }

    function cancelLocationSearch() {
        locationEpoch += 1;
        candidates = [];
        const root = document.getElementById('trip-briefing-location-candidates');
        if (root) root.innerHTML = '';
    }

    window.TripBriefingGeocode = Object.freeze({
        searchLocation, chooseLocation, cancelLocationSearch,
    });
})();
