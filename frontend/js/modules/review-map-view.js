(() => {
    function t(text, params = {}) {
        return window.I18n?.t ? I18n.t(text, params) : Object.entries(params)
            .reduce((value, [key, item]) => value.replace(`{${key}}`, item), text);
    }

    function stageColor(point) {
        if (point.coordinate_quality !== 'exact') return '#D98C24';
        if (point.latest_stage === 'Won') return '#2f855a';
        if (point.latest_stage === 'Lost') return '#8a3d3d';
        return '#8B1E3F';
    }

    function qualityLabel(point) {
        const confidenceKey = { high: 'High', medium: 'Medium', low: 'Low' }[
            String(point.geocode_confidence || '').toLowerCase()
        ];
        if (point.coordinate_quality === 'exact') {
            return `${t('Precise customer location')}${point.geocode_source ? ` · ${escapeHtml(t(point.geocode_source))}` : ''}`;
        }
        return `${t('Auto approximate location')}${confidenceKey ? ` · ${escapeHtml(t(confidenceKey))}` : ''} · ${t('verify')}`;
    }

    function pointPopup(point) {
        const leadLines = (point.leads || []).slice(0, 4).map(lead => `
            <div class="map-popup-lead">
                <strong>${escapeHtml(lead.display_id || '')}</strong>
                <span>${escapeHtml(t(lead.sales_stage || ''))}</span>
            </div>
        `).join('');
        const locked = point.geocode_locked
            ? `<span class="map-popup-locked">${t('Locked')}</span>`
            : '';
        const fixAction = point.can_edit
            ? `<button type="button" class="btn btn-secondary btn-sm" onclick="openCoordinateCorrectionFromMap('${escapeHtml(point.customer_id)}')">${t('Fix Location')}</button>`
            : '';
        return `
            <div class="map-popup">
                <div class="map-popup-title">${escapeHtml(point.customer_name)}</div>
                <div class="map-popup-meta">${escapeHtml([point.city, point.country_name || point.country].filter(Boolean).join(', '))}</div>
                <div class="map-popup-quality ${point.coordinate_quality === 'exact' ? 'exact' : 'fallback'}">${qualityLabel(point)}${locked}</div>
                <div class="map-popup-stats"><span>${t('{count} leads', { count: point.lead_count })}</span><span>${t('{count} won', { count: point.won_count })}</span><span>${t('{count} open', { count: point.open_count })}</span></div>
                <div class="map-popup-leads">${leadLines}</div>
                <div class="map-popup-actions">
                    <button type="button" class="btn btn-primary btn-sm" onclick="openInquiryPanel('${escapeHtml(point.latest_lead_id)}')">${t('Open Lead')}</button>
                    ${fixAction}
                </div>
            </div>
        `;
    }

    function aggregateCountryFallbacks(points) {
        const groups = new Map();
        points.forEach(point => {
            const key = point.country_code || point.country_name || point.country || 'unknown';
            const pair = MapSupport.coordinatePair(point.lat, point.lng);
            if (!pair) return;
            const group = groups.get(key) || {
                key,
                label: point.country_name || point.country || t('Unknown country'),
                lat: pair[0],
                lng: pair[1],
                points: [],
                leadCount: 0
            };
            group.lat = Math.min(group.lat, pair[0]);
            group.lng = Math.min(group.lng, pair[1]);
            group.points.push(point);
            group.leadCount += Number(point.lead_count) || 0;
            groups.set(key, group);
        });
        return [...groups.values()];
    }

    function aggregatePopup(group) {
        const rows = group.points.slice(0, 4).map(point => `
            <div class="map-popup-lead">
                <strong>${escapeHtml(point.customer_name)}</strong>
                ${point.can_edit ? `<button type="button" class="btn btn-secondary btn-sm" onclick="openCoordinateCorrectionFromMap('${escapeHtml(point.customer_id)}')">${t('Fix')}</button>` : ''}
            </div>
        `).join('');
        return `
            <div class="map-popup map-popup-aggregate">
                <div class="map-popup-title">${escapeHtml(group.label)}</div>
                <div class="map-popup-quality fallback">${t('Country aggregate — not a precise customer location')}</div>
                <div class="map-popup-meta">${t('{count} customers are grouped at the country center until precise coordinates are added.', { count: group.points.length })}</div>
                <div class="map-popup-leads">${rows}</div>
                <div class="map-popup-actions"><button type="button" class="btn btn-primary btn-sm" onclick="switchModule('coordinate-review')">${t('Open Coordinate Review')}</button></div>
            </div>
        `;
    }

    function renderSummary(mapData, display) {
        const summary = mapData.summary || {};
        const container = document.getElementById('map-summary');
        if (!container) return;
        container.innerHTML = `
            <div class="map-summary-line">${t('{customers} customers · {markers} visible markers · {exact} precise · {approximate} approximate · {missing} missing', {
                customers: summary.customers || 0,
                markers: display.markerCount,
                exact: summary.exact_points || 0,
                approximate: summary.approximate_points || 0,
                missing: summary.missing_locations || 0
            })}</div>
            <div class="map-quality-legend" aria-label="${t('Coordinate quality legend')}">
                <span><i class="map-legend-dot exact"></i>${t('Precise')}</span>
                <span><i class="map-legend-dot approximate"></i>${t('Auto approximate')}</span>
                <span><i class="map-legend-dot aggregate"></i>${t('Country aggregate')}</span>
                <span><i class="map-legend-dot missing"></i>${t('Missing — not mapped')}</span>
            </div>
        `;
    }

    window.ReviewMapView = Object.freeze({
        aggregateCountryFallbacks,
        aggregatePopup,
        pointPopup,
        renderSummary,
        stageColor
    });
})();
