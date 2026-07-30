// ===== Batch Geocode =====
function batchGeocodeText(text, params = {}) {
    return window.I18n?.t ? I18n.t(text, params) : Object.entries(params)
        .reduce((value, [key, item]) => value.replace(`{${key}}`, item), text);
}

window.syncBatchGeocodeAccess = function(mapData) {
    const records = [...(mapData?.points || []), ...(mapData?.missing_locations || [])];
    const canEdit = records.some(item => item.can_edit === true);
    const button = document.getElementById('batch-geocode-btn');
    if (!button) return;
    button.hidden = !canEdit;
    button.disabled = !canEdit;
};

window.batchGeocode = async function() {
    const mapData = State.mapData;
    if (!mapData) {
        alert(batchGeocodeText('No map data is loaded.'));
        return;
    }

    const { needsGeocode, missing, total, customers } = BatchGeocodeData.snapshot(mapData);
    if (total === 0) {
        notify(batchGeocodeText('All customers already have precise coordinates.'));
        return;
    }

    const confirmation = [
        batchGeocodeText('Found {count} customers needing geocoding.', { count: total }),
        '',
        batchGeocodeText('- {count} with country-level fallback', { count: needsGeocode.length }),
        batchGeocodeText('- {count} with no coordinates', { count: missing.length }),
        '',
        batchGeocodeText('Customer address fields will be sent to one or more configured external geocoding services. Use this only for data approved for external processing.'),
        '',
        batchGeocodeText('This may take about {seconds} seconds due to rate limiting.', {
            seconds: Math.ceil(total * 1.5)
        }),
        batchGeocodeText('Continue?')
    ].join('\n');
    if (!confirm(confirmation)) {
        return;
    }

    const btn = document.getElementById('batch-geocode-btn');
    const originalText = btn.textContent;
    btn.disabled = true;
    btn.textContent = batchGeocodeText('Processing...');

    let success = 0;
    let skipped = 0;
    let errors = 0;

    for (let i = 0; i < customers.length; i++) {
        const customer = customers[i];
        btn.textContent = batchGeocodeText('Processing {current}/{total}...', {
            current: i + 1,
            total
        });

        // Skip if no address info at all
        if (!customer.address && !customer.city && !customer.postal_code && !customer.country) {
            skipped++;
            continue;
        }

        try {
            // Call geocode API
            const search = await ApiClient.searchGeocode(customer, 1);
            const geocodeResult = search.candidates?.[0];

            if (geocodeResult && Number.isFinite(Number(geocodeResult.lat)) &&
                Number.isFinite(Number(geocodeResult.lng))) {
                // Map data carries the current version, avoiding one GET per customer.
                const rowVersion = customer.row_version ||
                    (await ApiClient.getCustomer(customer.id)).row_version;

                // Update customer with new coordinates
                await ApiClient.updateCustomer(customer.id, {
                    lat: geocodeResult.lat,
                    lng: geocodeResult.lng,
                    normalized_address: geocodeResult.normalized_address,
                    geocode_source: 'auto',
                    // Batch mode cannot confirm that the first search result is
                    // the intended customer. Keep every automatic pick in the
                    // review queue until a person opens and saves it.
                    geocode_confidence: 'medium',
                    geocode_locked: false
                }, rowVersion);

                success++;
            } else {
                skipped++;
            }
        } catch (err) {
            console.error(`Geocode error for ${customer.name}:`, err);
            errors++;
        }
    }

    btn.disabled = false;
    btn.textContent = originalText;

    // Show result
    alert([
        batchGeocodeText('Batch geocode complete.'),
        '',
        batchGeocodeText('- Updated: {count}', { count: success }),
        batchGeocodeText('- Skipped (no result): {count}', { count: skipped }),
        batchGeocodeText('- Errors: {count}', { count: errors })
    ].join('\n'));

    if (document.getElementById('module-coordinate-review')?.classList.contains('active')) {
        applyCoordinateReviewData(await ApiClient.getMapData({}));
    } else {
        await loadReviewMap();
    }
};
