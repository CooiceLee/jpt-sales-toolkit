function renderCoordinateReviewList() {
    const container = document.getElementById('coordinate-review-list');
    if (!coordinateReviewData) {
        container.innerHTML = `<div class="empty-state">${escapeHtml(coordinateText('No data available'))}</div>`;
        return;
    }

    const points = coordinateReviewData.points || [];
    const missing = coordinateReviewData.missing_locations || [];

    const pointItems = points.map(p => {
        const isVerified = !p.needs_geocode && (p.geocode_locked || p.geocode_source === 'manual');
        return {
            ...p,
            status: p.needs_geocode ? 'needs_review' : (isVerified ? 'verified' : 'auto'),
            hasCoordinates: Number.isFinite(Number(p.lat)) && Number.isFinite(Number(p.lng)),
            statusLabel: p.needs_geocode ?
                coordinateText(p.coordinate_quality === 'country_fallback' ? 'Country Fallback' : 'Auto Approximate') :
                coordinateText(isVerified ? 'Verified' : 'Auto Exact')
        };
    });
    const missingItems = missing.map(m => ({
        ...m,
        status: 'missing',
        statusLabel: coordinateText('Missing'),
        hasCoordinates: false,
        lat: null,
        lng: null
    }));

    let items = [];
    if (coordinateReviewFilter === 'all') {
        items = [...pointItems, ...missingItems];
    } else if (coordinateReviewFilter === 'needs_review') {
        items = points.filter(p => p.needs_geocode).map(p => ({
            ...p,
            status: 'needs_review',
            hasCoordinates: Number.isFinite(Number(p.lat)) && Number.isFinite(Number(p.lng)),
            statusLabel: coordinateText(p.coordinate_quality === 'country_fallback' ? 'Country Fallback' : 'Auto Approximate')
        }));
    } else if (coordinateReviewFilter === 'missing') {
        items = missingItems;
    } else if (coordinateReviewFilter === 'verified') {
        items = pointItems.filter(item => item.status === 'verified');
    }

    const query = coordinateReviewSearch.trim().toLowerCase();
    if (query) {
        items = items.filter(item => [
            item.customer_name,
            item.name,
            item.city,
            item.country,
            item.address,
            item.region
        ].some(value => String(value || '').toLowerCase().includes(query)));
    }

    if (items.length === 0) {
        const emptyMessage = query
            ? coordinateText('No matches for "{query}"', { query: coordinateReviewSearch.trim() })
            : coordinateText('No customers match this filter');
        container.innerHTML = `<div class="empty-state">${escapeHtml(emptyMessage)}</div>`;
        return;
    }

    // Sort by lead count (most important first)
    items.sort((a, b) => (b.lead_count || 0) - (a.lead_count || 0));
    const totalPages = Math.max(1, Math.ceil(items.length / COORDINATE_REVIEW_PAGE_SIZE));
    coordinateReviewPage = Math.min(Math.max(1, coordinateReviewPage), totalPages);
    const start = (coordinateReviewPage - 1) * COORDINATE_REVIEW_PAGE_SIZE;
    const pageItems = items.slice(start, start + COORDINATE_REVIEW_PAGE_SIZE);
    const shownFrom = items.length ? start + 1 : 0;
    const shownTo = items.length ? Math.min(start + pageItems.length, items.length) : 0;

    container.innerHTML = CoordinateReviewTable.table(pageItems) +
        CoordinateReviewTable.pagination({
            page: coordinateReviewPage,
            totalPages,
            shownFrom,
            shownTo,
            total: items.length
        });
}
