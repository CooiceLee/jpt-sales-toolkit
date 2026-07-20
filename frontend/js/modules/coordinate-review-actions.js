window.filterCoordinateReview = function(filter) {
    coordinateReviewFilter = filter;

    // Update active tab
    document.querySelectorAll('[data-coord-filter]').forEach(btn => {
        btn.classList.toggle('active', btn.dataset.coordFilter === filter);
    });

    // Re-render list
    renderCoordinateReviewList();
};

window.searchCoordinateReview = function(value) {
    coordinateReviewSearch = value || '';
    renderCoordinateReviewList();
};

window.openCoordinateCorrectionFromReview = function(customerId) {
    const points = coordinateReviewData?.points || [];
    const missing = coordinateReviewData?.missing_locations || [];
    const item = [...points, ...missing].find(row => (row.customer_id || row.id) === customerId);
    if (!item) {
        alert('Customer coordinate data is no longer available. Please refresh the list.');
        return;
    }

    const pair = MapSupport.coordinatePair(item.lat, item.lng);
    openCoordinateCorrection(
        item.customer_id || item.id,
        item.customer_name || item.name || 'Customer',
        pair ? pair[0] : null,
        pair ? pair[1] : null,
        {
            address: item.address,
            city: item.city,
            country: item.country,
            normalized_address: item.normalized_address
        }
    );
};
