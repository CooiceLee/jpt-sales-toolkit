(() => {
    let reviewMapRequestEpoch = 0;

    function markerRadius(leadCount) {
        return Math.min(16, 7 + Math.sqrt(Math.max(1, Number(leadCount) || 1)) * 2);
    }

    function reviewMapText(text, params = {}) {
        return window.I18n?.t ? I18n.t(text, params) : Object.entries(params)
            .reduce((value, [key, item]) => value.replace(`{${key}}`, item), text);
    }

    window.initMap = function() {
        if (State.map || !document.getElementById('world-map')) return;
        State.map = L.map('world-map', { preferCanvas: true }).setView([35, 20], 2);
        MapSupport.addTileLayer(State.map, { containerId: 'world-map', style: 'light' });
        State.mapLayer = L.layerGroup().addTo(State.map);
    };

    window.getMapFilters = function() {
        return {
            sales_stage: document.getElementById('map-stage-filter')?.value || '',
            outcome: document.getElementById('map-outcome-filter')?.value || '',
            region: document.getElementById('map-region-filter')?.value || ''
        };
    };

    window.loadReviewMap = async function() {
        if (!State.map || !State.mapLayer) return;
        const requestEpoch = ++reviewMapRequestEpoch;
        try {
            const filters = getMapFilters();
            const mapData = await ApiClient.getMapData(filters);
            if (requestEpoch !== reviewMapRequestEpoch) return null;
            State.mapData = mapData;
            window.syncBatchGeocodeAccess?.(mapData);
            if (!filters.sales_stage && !filters.outcome && !filters.region) {
                updateCoordinateReviewBadge(mapData);
            }
            renderReviewMap(mapData);
            return mapData;
        } catch (err) {
            if (requestEpoch !== reviewMapRequestEpoch) return null;
            console.error('Review map error:', err);
            State.mapLayer.clearLayers();
            State.mapCustomerMarkers = {};
            State.mapData = null;
            window.syncBatchGeocodeAccess?.(null);
            const summary = document.getElementById('map-summary');
            if (summary) summary.textContent = reviewMapText('Map data unavailable. Try again.');
            return null;
        }
    };

    window.renderReviewMap = function(mapData) {
        State.mapLayer.clearLayers();
        State.mapCustomerMarkers = {};
        const quality = document.getElementById('map-quality-filter')?.value || '';
        const points = (mapData.points || []).filter(point => {
            if (!MapSupport.coordinatePair(point.lat, point.lng)) return false;
            if (quality === 'exact') return point.coordinate_quality === 'exact';
            if (quality === 'needs_geocode') return point.needs_geocode;
            return true;
        });
        const fallback = points.filter(point => point.coordinate_quality === 'country_fallback');
        const individual = points.filter(point => point.coordinate_quality !== 'country_fallback');
        const aggregates = ReviewMapView.aggregateCountryFallbacks(fallback);
        const bounds = [];

        individual.forEach(point => {
            const pair = MapSupport.coordinatePair(point.lat, point.lng);
            const exact = point.coordinate_quality === 'exact';
            const marker = L.circleMarker(pair, {
                radius: markerRadius(point.lead_count),
                color: exact ? '#ffffff' : '#6b4b12',
                weight: exact ? 2 : 1.5,
                fillColor: ReviewMapView.stageColor(point),
                fillOpacity: exact ? 0.88 : 0.58,
                dashArray: exact ? null : '4 3'
            });
            marker.bindTooltip(escapeHtml(`${point.customer_name || ''} · ${Number(point.lead_count) || 0}`));
            marker.bindPopup(ReviewMapView.pointPopup(point), { minWidth: 260 });
            marker.addTo(State.mapLayer);
            State.mapCustomerMarkers[point.customer_id] = marker;
            bounds.push(pair);
        });

        aggregates.forEach(group => {
            const pair = [group.lat, group.lng];
            const marker = L.circleMarker(pair, {
                radius: Math.min(22, 9 + Math.sqrt(group.points.length) * 2.5),
                color: '#80530d',
                weight: 2,
                fillColor: '#F0B75A',
                fillOpacity: 0.42,
                dashArray: '6 4'
            });
            marker.bindTooltip(escapeHtml(`${group.label || ''} · ${reviewMapText(
                '{count} customers · country aggregate', { count: group.points.length }
            )}`));
            marker.bindPopup(ReviewMapView.aggregatePopup(group), { minWidth: 290 });
            marker.addTo(State.mapLayer);
            group.points.forEach(point => { State.mapCustomerMarkers[point.customer_id] = marker; });
            bounds.push(pair);
        });

        State.map.invalidateSize({ pan: false });
        if (bounds.length) State.map.fitBounds(bounds, { padding: [28, 28], maxZoom: 6 });
        else State.map.setView([35, 20], 2);
        ReviewMapView.renderSummary(mapData, {
            markerCount: individual.length + aggregates.length
        });
    };

    window.updateCoordinateReviewBadge = function(mapData) {
        const summary = mapData?.summary || {};
        setText('nav-coordinate-review-total', (summary.approximate_points || 0) + (summary.missing_locations || 0));
    };
})();
