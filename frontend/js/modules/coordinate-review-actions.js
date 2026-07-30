window.filterCoordinateReview = function(filter) {
    coordinateReviewFilter = filter;
    coordinateReviewPage = 1;

    // Update active tab
    document.querySelectorAll('[data-coord-filter]').forEach(btn => {
        btn.classList.toggle('active', btn.dataset.coordFilter === filter);
    });

    // Re-render list
    renderCoordinateReviewList();
};

window.searchCoordinateReview = function(value) {
    coordinateReviewSearch = value || '';
    coordinateReviewPage = 1;
    clearTimeout(window.coordinateReviewSearchTimer);
    window.coordinateReviewSearchTimer = setTimeout(renderCoordinateReviewList, 120);
};

window.changeCoordinateReviewPage = function(delta) {
    coordinateReviewPage = Math.max(1, coordinateReviewPage + Number(delta || 0));
    renderCoordinateReviewList();
    document.getElementById('coordinate-review-list')?.scrollIntoView({
        behavior: 'smooth', block: 'start'
    });
};

window.openCoordinateCorrectionFromReview = function(customerId) {
    const points = coordinateReviewData?.points || [];
    const missing = coordinateReviewData?.missing_locations || [];
    const item = [...points, ...missing].find(row => (row.customer_id || row.id) === customerId);
    if (!item) {
        alert(coordinateText('Customer coordinate data is no longer available. Please refresh the list.'));
        return;
    }
    if (!item.can_edit) return;

    const pair = MapSupport.coordinatePair(item.lat, item.lng);
    openCoordinateCorrection(
        item.customer_id || item.id,
        item.customer_name || item.name || 'Customer',
        pair ? pair[0] : null,
        pair ? pair[1] : null,
        {
            address: item.address,
            city: item.city,
            postal_code: item.postal_code,
            country: item.country,
            normalized_address: item.normalized_address,
            row_version: item.customer_row_version
        }
    );
};
