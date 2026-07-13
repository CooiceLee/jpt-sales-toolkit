function renderCoordinateReviewList() {
    const container = document.getElementById('coordinate-review-list');
    if (!coordinateReviewData) {
        container.innerHTML = '<div class="empty-state">No data available</div>';
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
                (p.coordinate_quality === 'country_fallback' ? 'Country Fallback' : 'Auto Approximate') :
                (isVerified ? 'Verified' : 'Auto Exact')
        };
    });
    const missingItems = missing.map(m => ({
        ...m,
        status: 'missing',
        statusLabel: 'Missing',
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
            statusLabel: p.coordinate_quality === 'country_fallback' ? 'Country Fallback' : 'Auto Approximate'
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
        container.innerHTML = `<div class="empty-state">${
            query ? `No matches for "${escapeHtml(coordinateReviewSearch.trim())}"` : 'No customers match this filter'
        }</div>`;
        return;
    }

    // Sort by lead count (most important first)
    items.sort((a, b) => (b.lead_count || 0) - (a.lead_count || 0));

    container.innerHTML = `
        <table class="data-table">
            <thead>
                <tr>
                    <th>Customer</th>
                    <th>Location</th>
                    <th>Status</th>
                    <th style="text-align:center;">Leads</th>
                    <th>Coordinates</th>
                    <th style="width:120px;">Actions</th>
                </tr>
            </thead>
            <tbody>
                ${items.map(item => `
                    <tr>
                        <td>
                            <div style="font-weight:500;">${escapeHtml(item.customer_name || item.name)}</div>
                            ${item.region ? `<div style="font-size:12px;color:var(--ink-500);">${escapeHtml(item.region)}</div>` : ''}
                        </td>
                        <td>
                            <div>${escapeHtml([item.city, item.country].filter(Boolean).join(', '))}</div>
                            ${item.address ? `<div style="font-size:12px;color:var(--ink-500);">${escapeHtml(item.address)}</div>` : ''}
                        </td>
                        <td>
                            <span class="coord-status-badge status-${item.status}">${escapeHtml(item.statusLabel)}</span>
                        </td>
                        <td style="text-align:center;">${item.lead_count || 0}</td>
                        <td style="font-family:var(--mono-font);font-size:12px;">
                            ${item.hasCoordinates ?
                                `${item.lat.toFixed(4)}, ${item.lng.toFixed(4)}` :
                                '<span style="color:var(--ink-400);">—</span>'
                            }
                        </td>
                        <td>
                            <button type="button" class="btn btn-secondary btn-sm"
                                onclick="openCoordinateCorrectionFromReview('${item.customer_id || item.id}')">
                                ${item.status === 'missing' ? 'Add' : 'Fix'}
                            </button>
                        </td>
                    </tr>
                `).join('')}
            </tbody>
        </table>
    `;
}

