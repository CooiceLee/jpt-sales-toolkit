// ===== Coordinate Review Module =====
let coordinateReviewData = null;
let coordinateReviewFilter = 'all';
let coordinateReviewSearch = '';
let coordinateReviewPage = 1;
const COORDINATE_REVIEW_PAGE_SIZE = 40;
let coordinateReviewRequestEpoch = 0;

window.applyCoordinateReviewData = function(mapData) {
    coordinateReviewData = mapData;
    coordinateReviewPage = 1;
    State.mapData = mapData;
    updateCoordinateReviewBadge(mapData);

    const needsReview = (mapData.points || []).filter(p => p.needs_geocode);
    const missing = mapData.missing_locations || [];
    const verified = (mapData.points || []).filter(p =>
        !p.needs_geocode && (p.geocode_locked || p.geocode_source === 'manual')
    );
    setText('coord-needs-review', needsReview.length);
    setText('coord-missing', missing.length);
    setText('coord-verified', verified.length);
    renderCoordinateReviewList();
};

async function loadCoordinateReview() {
    const requestEpoch = ++coordinateReviewRequestEpoch;
    try {
        // Reuse the map data API to get all coordinate information
        const mapData = await ApiClient.getMapData({});
        if (requestEpoch !== coordinateReviewRequestEpoch) return;
        applyCoordinateReviewData(mapData);
    } catch (err) {
        if (requestEpoch !== coordinateReviewRequestEpoch) return;
        console.error('Load coordinate review error:', err);
        const container = document.getElementById('coordinate-review-list');
        if (container) {
            container.innerHTML = `<div class="empty-state">${escapeHtml(
                coordinateText('Error loading coordinate data')
            )}</div>`;
        }
    }
}
