// ===== Coordinate Review Module =====
let coordinateReviewData = null;
let coordinateReviewFilter = 'all';
let coordinateReviewSearch = '';

async function loadCoordinateReview() {
    try {
        // Reuse the map data API to get all coordinate information
        const mapData = await ApiClient.getMapData({});
        coordinateReviewData = mapData;
        updateCoordinateReviewBadge(mapData);

        // Calculate statistics
        const needsReview = (mapData.points || []).filter(p => p.needs_geocode);
        const missing = mapData.missing_locations || [];
        const verified = (mapData.points || []).filter(p =>
            !p.needs_geocode && (p.geocode_locked || p.geocode_source === 'manual')
        );

        setText('coord-needs-review', needsReview.length);
        setText('coord-missing', missing.length);
        setText('coord-verified', verified.length);
        // Render list
        renderCoordinateReviewList();
    } catch (err) {
        console.error('Load coordinate review error:', err);
        document.getElementById('coordinate-review-list').innerHTML =
            '<div class="empty-state">Error loading coordinate data</div>';
    }
}

