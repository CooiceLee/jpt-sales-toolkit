(() => {
    function customer(item) {
        return {
            id: item.customer_id,
            name: item.customer_name,
            address: item.address,
            city: item.city,
            postal_code: item.postal_code,
            country: item.country,
            row_version: item.customer_row_version
        };
    }

    function snapshot(mapData) {
        const needsGeocode = (mapData?.points || []).filter(
            item => item.needs_geocode && item.can_edit === true
        );
        const missing = (mapData?.missing_locations || []).filter(
            item => item.can_edit === true
        );
        return {
            needsGeocode,
            missing,
            total: needsGeocode.length + missing.length,
            customers: [...needsGeocode.map(customer), ...missing.map(customer)]
        };
    }

    window.BatchGeocodeData = Object.freeze({ snapshot });
})();
