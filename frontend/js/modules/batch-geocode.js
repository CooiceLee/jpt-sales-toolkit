// ===== Batch Geocode =====
window.batchGeocode = async function() {
    const mapData = State.mapData;
    if (!mapData) {
        alert('No map data loaded');
        return;
    }

    // Find customers that need geocoding (country_fallback or missing coordinates)
    const needsGeocode = (mapData.points || []).filter(p => p.needs_geocode);
    const missing = mapData.missing_locations || [];

    const total = needsGeocode.length + missing.length;
    if (total === 0) {
        notify('All customers already have precise coordinates');
        return;
    }

    if (!confirm(`Found ${total} customers needing geocoding.\n\n` +
                 `- ${needsGeocode.length} with country-level fallback\n` +
                 `- ${missing.length} with no coordinates\n\n` +
                 `This may take ${Math.ceil(total * 1.5)} seconds due to rate limiting.\n` +
                 `Continue?`)) {
        return;
    }

    const btn = document.getElementById('batch-geocode-btn');
    const originalText = btn.textContent;
    btn.disabled = true;
    btn.textContent = 'Processing...';

    let success = 0;
    let skipped = 0;
    let errors = 0;

    // Combine both lists
    const allCustomers = [
        ...needsGeocode.map(p => ({
            id: p.customer_id,
            name: p.customer_name,
            address: p.address,
            city: p.city,
            country: p.country
        })),
        ...missing.map(m => ({
            id: m.customer_id,
            name: m.customer_name,
            address: m.address,
            city: m.city,
            country: m.country
        }))
    ];

    for (let i = 0; i < allCustomers.length; i++) {
        const customer = allCustomers[i];
        btn.textContent = `Processing ${i + 1}/${total}...`;

        // Skip if no address info at all
        if (!customer.address && !customer.city && !customer.country) {
            skipped++;
            continue;
        }

        try {
            // Call geocode API
            const geocodeResult = await ApiClient.geocode(
                customer.address,
                customer.city,
                customer.country
            );

            if (geocodeResult && geocodeResult.lat && geocodeResult.lng) {
                // Get current customer to get row_version
                const current = await ApiClient.getCustomer(customer.id);

                // Update customer with new coordinates
                await ApiClient.updateCustomer(customer.id, {
                    lat: geocodeResult.lat,
                    lng: geocodeResult.lng,
                    normalized_address: geocodeResult.normalized_address,
                    geocode_source: 'auto',
                    geocode_confidence: geocodeResult.confidence || 'medium'
                }, current.row_version);

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
    alert(`Batch geocode complete:\n\n` +
          `- Updated: ${success}\n` +
          `- Skipped (no result): ${skipped}\n` +
          `- Errors: ${errors}`);

    // Refresh map and coordinate review list.
    await loadReviewMap();
    if (document.getElementById('module-coordinate-review')?.classList.contains('active')) {
        await loadCoordinateReview();
    }
};

