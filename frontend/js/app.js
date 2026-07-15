/**
 * JPT Sales Toolkit - v6.6 modular application entry
 * Global state, startup, navigation, dashboard and overview map only.
 */

// ===== Global State =====
const State = {
    user: null,
    config: {
        regions: null,
        fields: null,
        products: null
    },
    inquiries: [],
    currentInquiry: null,
    map: null,
    countryMarkers: {},
    mapLayer: null,
    mapData: null,
    tripMap: null,
    tripMapLayer: null,
    tripCandidates: [],
    tripCandidatePagination: {
        total: 0,
        limit: 25,
        offset: 0,
        hasMore: false
    },
    tripPlans: [],
    currentTripPlan: null,
    tripBusy: false,
    mapCustomerMarkers: {},
    currentFilter: 'all',
    stageUsers: {
        sales: [],
        tech: []
    },
    stageFilters: {
        search: '',
        ownerId: '',
        techId: '',
        customerId: ''
    },
    customerMerge: {
        source: null,
        target: null
    },
    currentFilters: {
        followup: 'all',
        sampling: 'all',
        deal: 'all',
        fulfillment: 'all',
        aftersales: 'all'
    }
};

const STAGE_MODULES = ['handler', 'followup', 'sampling', 'deal', 'fulfillment', 'aftersales'];

function deriveModuleCounts(stats) {
    const byStage = stats.stage_counts || {};
    return {
        total: stats.total_leads || 0,
        handler: byStage['New'] || 0,
        followup: (byStage['Assigned'] || 0) + (byStage['Following'] || 0),
        sampling: byStage['Following'] || 0,
        deal: (byStage['Quoted'] || 0) + (byStage['Lost'] || 0),
        fulfillment: byStage['Won'] || 0,
        aftersales: stats.service_open_count || 0,
    };
}

function applyNavigationCounts(stats) {
    const counts = deriveModuleCounts(stats);
    setText('nav-total', counts.total);
    setText('nav-handler-total', counts.handler);
    setText('nav-followup-total', counts.followup);
    setText('nav-sampling-total', counts.sampling);
    setText('nav-deal-total', counts.deal);
    setText('nav-fulfillment-total', counts.fulfillment);
    setText('nav-aftersales-total', counts.aftersales);
    return counts;
}

// ===== Initialization =====
document.addEventListener('DOMContentLoaded', init);

// Listen for logout events from ApiClient
window.addEventListener('auth:logout', () => {
    State.user = null;
    document.getElementById('app').style.display = 'none';
    showModal('login-modal');
});

async function init() {
    try {
        // Offline installations must complete device activation before login.
        if (typeof initAuthorizationActivation === 'function' && !(await initAuthorizationActivation())) {
            return;
        }
        // Check if already logged in
        if (ApiClient.isLoggedIn()) {
            try {
                // Verify token is still valid
                State.user = await ApiClient.getMe();
                await loadConfig();
                startApp();
                return;
            } catch (err) {
                // Token invalid, show login
                console.log('Token expired, showing login');
                ApiClient.clearAuth();
            }
        }
        // Show login modal
        showModal('login-modal');
    } catch (err) {
        console.error('Init error:', err);
        showModal('login-modal');
    }
}

async function loadConfig() {
    // Load UI definitions from the canonical root config directory via API.
    try {
        const [regions, fields, products] = await Promise.all([
            fetch('/api/config/regions').then(r => r.ok ? r.json() : {}),
            fetch('/api/config/fields').then(r => r.ok ? r.json() : {}),
            fetch('/api/config/products').then(r => r.ok ? r.json() : {})
        ]);
        State.config = { regions, fields, products };
    } catch (e) {
        // Use defaults if config files not available
        State.config = { regions: {}, fields: {}, products: {} };
    }
}

// ===== Login Handler =====
async function handleLogin() {
    const username = document.getElementById('login-username').value.trim();
    const password = document.getElementById('login-password').value;
    const errorEl = document.getElementById('login-error');

    if (!username || !password) {
        errorEl.textContent = 'Please enter username and password';
        errorEl.style.display = 'block';
        return;
    }

    try {
        errorEl.style.display = 'none';
        State.user = await ApiClient.login(username, password);
        await loadConfig();
        hideModal('login-modal');
        startApp();
    } catch (err) {
        errorEl.textContent = err.message || 'Login failed';
        errorEl.style.display = 'block';
    }
}

// Allow Enter key to submit login
document.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && document.getElementById('login-modal').classList.contains('show')) {
        handleLogin();
    }
});

function startApp() {
    hideModal('init-modal');
    document.getElementById('app').style.display = 'flex';

    // Update user display
    updateUserDisplay();
    initAuthorizationCenter();
    applyAuthorizationSessionNotice();
    RoleCapabilities.applyNavigation();

    // Initialize all modules
    initNavigation();
    if (!RoleCapabilities.isTech()) {
        initMap();
        initParser();
        initCustomerMerge();
    }
    initFilters();
    initStageFilterControls();
    initUserMenu();

    // Load initial data
    switchModule(RoleCapabilities.initialModule());
}

// ===== API Helper (Legacy compatibility wrapper) =====
async function api(endpoint, options = {}) {
    const token = ApiClient.getToken();
    const headers = {
        'Content-Type': 'application/json',
        ...options.headers
    };
    if (token) {
        headers['Authorization'] = `Bearer ${token}`;
    }

    const response = await fetch('/api' + endpoint, {
        ...options,
        headers
    });

    if (response.status === 401) {
        ApiClient.clearAuth();
        window.dispatchEvent(new CustomEvent('auth:logout'));
        throw new Error('Session expired');
    }

    if (!response.ok) throw new Error(`API Error: ${response.status}`);
    return response.json();
}

// ===== Navigation =====
function initNavigation() {
    // Rail buttons
    document.querySelectorAll('.rail-btn[data-module]').forEach(btn => {
        btn.addEventListener('click', () => switchModule(btn.dataset.module));
    });

    // Sidebar nav items
    document.querySelectorAll('.nav-item[data-module]').forEach(item => {
        item.addEventListener('click', () => switchModule(item.dataset.module));
    });
}

function switchModule(module) {
    if (!module) return;
    if (!RoleCapabilities.canAccessModule(module)) {
        module = RoleCapabilities.initialModule();
    }
    const previousModule = document.querySelector('.module.active')?.id?.replace('module-', '');

    // Close panel
    closePanel();

    // Update rail
    document.querySelectorAll('.rail-btn').forEach(b => b.classList.remove('active'));
    document.querySelector(`.rail-btn[data-module="${module}"]`)?.classList.add('active');

    // Update sidebar
    document.querySelectorAll('.nav-item').forEach(i => i.classList.remove('active'));
    document.querySelector(`.nav-item[data-module="${module}"]`)?.classList.add('active');

    // Show module
    document.querySelectorAll('.module').forEach(m => m.classList.remove('active'));
    document.getElementById(`module-${module}`)?.classList.add('active');
    syncStageFilterInputs();

    // Update breadcrumb
    const titles = {
        dashboard: 'Dashboard',
        parser: 'Inquiry Parser',
        handler: 'Inquiry Handler',
        followup: 'Follow-up Tracker',
        sampling: 'Sample Manager',
        deal: 'Deal Closer',
        fulfillment: 'Order Fulfillment',
        aftersales: 'After-sales',
        'data-review': 'Data Review',
        'trip-planner': 'Trip Planner',
        'coordinate-review': 'Coordinate Review',
        authorization: 'Team & Authorization',
        export: 'Export / Import'
    };
    document.getElementById('breadcrumb-current').textContent = titles[module] || module;

    // Refresh map if dashboard
    if (module === 'dashboard' && State.map) {
        setTimeout(() => State.map.invalidateSize(), 100);
    }
    if (module === 'trip-planner' && State.tripMap) {
        setTimeout(() => State.tripMap.invalidateSize(), 100);
    }
    if (previousModule === 'trip-planner' && module !== 'trip-planner') {
        destroyTripPlannerMap();
    }

    // Load module data
    loadModuleData(module);
}

async function loadModuleData(module) {
    switch (module) {
        case 'dashboard': await loadDashboard(); break;
        case 'handler': await loadHandler(); break;
        case 'followup': await loadFollowup(); break;
        case 'sampling': await loadSampling(); break;
        case 'deal': await loadDeal(); break;
        case 'fulfillment': await loadFulfillment(); break;
        case 'aftersales': await loadAftersales(); break;
        case 'data-review': await loadDataReview(); break;
        case 'trip-planner': await loadTripPlanner(); break;
        case 'coordinate-review': await loadCoordinateReview(); break;
        case 'authorization': await loadAuthorizationCenter(); break;
    }
}

// ===== Dashboard =====
async function loadDashboard() {
    try {
        const stats = await ApiClient.getDashboard();

        // Map backend stages: New, Assigned, Following, Quoted, Won, Lost
        const byStage = stats.stage_counts || {};
        const counts = deriveModuleCounts(stats);
        const wonCount = byStage['Won'] || 0;

        // Update KPIs
        setText('kpi-total', stats.total_leads || 0);
        setText('kpi-recent', stats.recent_7_days || 0);
        setText('kpi-following', counts.followup);
        setText('kpi-won', wonCount);
        setText('kpi-pipeline', Math.round((stats.won_value || 0) / 1000).toLocaleString());

        applyNavigationCounts(stats);

        // Update funnel
        renderFunnel(byStage);

        // Update review map with current filters.
        await loadReviewMap();
    } catch (err) {
        console.error('Dashboard error:', err);
    }
}

function renderFunnel(byStage) {
    // Map to new backend stages: New, Assigned, Following, Quoted, Won, Lost
    const stages = [
        { key: 'New', label: 'New', step: '01' },
        { key: 'Assigned', label: 'Assigned', step: '02' },
        { key: 'Following', label: 'Following', step: '03' },
        { key: 'Quoted', label: 'Quoted', step: '04' },
        { key: 'Won', label: 'Won', step: '05' },
        { key: 'Lost', label: 'Lost', step: '06' }
    ];

    // 计算总数作为基准
    const total = Object.values(byStage).reduce((s, v) => s + v, 0) || 1;

    const container = document.getElementById('pipeline-funnel');
    if (!container) return;

    container.innerHTML = stages.map(s => {
        const count = byStage[s.key] || 0;
        // 百分比基于总数
        const pct = Math.round((count / total) * 100);
        return `
            <div class="funnel-row">
                <div class="funnel-step">${s.step}</div>
                <div class="funnel-label">${s.label}</div>
                <div class="funnel-bar">
                    <div class="funnel-bar-fill" style="width:${Math.max(pct, count > 0 ? 8 : 0)}%"></div>
                </div>
                <div class="funnel-count">${count}</div>
                <div class="funnel-pct">${pct}%</div>
            </div>
        `;
    }).join('');
}

// ===== Map =====
function initMap() {
    State.map = L.map('world-map').setView([48, 10], 4);
    L.tileLayer('https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png', {
        attribution: '&copy; OpenStreetMap, CARTO'
    }).addTo(State.map);

    State.mapLayer = L.layerGroup().addTo(State.map);
}

function getMapFilters() {
    return {
        sales_stage: document.getElementById('map-stage-filter')?.value || '',
        outcome: document.getElementById('map-outcome-filter')?.value || '',
        region: document.getElementById('map-region-filter')?.value || ''
    };
}

async function loadReviewMap() {
    if (!State.map || !State.mapLayer) return;

    try {
        const filters = getMapFilters();
        const mapData = await ApiClient.getMapData(filters);
        State.mapData = mapData;
        if (!filters.sales_stage && !filters.outcome && !filters.region) {
            updateCoordinateReviewBadge(mapData);
        }
        renderReviewMap(mapData);
    } catch (err) {
        console.error('Review map error:', err);
        setText('map-summary', 'Map data unavailable');
    }
}

function renderReviewMap(mapData) {
    State.mapLayer.clearLayers();
    State.mapCustomerMarkers = {};

    const qualityFilter = document.getElementById('map-quality-filter')?.value || '';
    const points = (mapData.points || []).filter(point => {
        if (qualityFilter === 'exact') return point.coordinate_quality === 'exact';
        if (qualityFilter === 'needs_geocode') return point.needs_geocode;
        return true;
    });

    const bounds = [];
    points.forEach(point => {
        const isExact = point.coordinate_quality === 'exact';
        const color = point.latest_stage === 'Won' ? '#2f855a' :
            point.latest_stage === 'Lost' ? '#8a3d3d' :
            isExact ? '#8B1E3F' : '#D98C24';
        const marker = L.circleMarker([point.lat, point.lng], {
            radius: Math.min(22, 8 + point.lead_count * 3),
            color: isExact ? '#ffffff' : '#6b4b12',
            weight: isExact ? 2 : 1,
            fillColor: color,
            fillOpacity: isExact ? 0.88 : 0.62,
            dashArray: isExact ? null : '4 3'
        });

        marker.bindTooltip(`${point.customer_name} · ${point.lead_count}`);
        marker.bindPopup(renderMapPopup(point), { minWidth: 260 });
        marker.addTo(State.mapLayer);
        State.mapCustomerMarkers[point.customer_id] = marker;
        bounds.push([point.lat, point.lng]);
    });

    if (bounds.length) {
        State.map.fitBounds(bounds, { padding: [28, 28], maxZoom: 6 });
    } else {
        State.map.setView([35, 20], 2);
    }

    renderMapSummary(mapData, points.length);
}

function renderMapPopup(point) {
    const leadLines = (point.leads || []).slice(0, 4).map(lead => `
        <div class="map-popup-lead">
            <strong>${escapeHtml(lead.display_id || '')}</strong>
            <span>${escapeHtml(lead.sales_stage || '')}</span>
        </div>
    `).join('');
    const qualityLabel = point.coordinate_quality === 'exact'
        ? `Exact ${point.geocode_source ? `· ${escapeHtml(point.geocode_source)}` : ''}`
        : point.coordinate_quality === 'auto_approximate'
            ? `Auto candidate ${point.geocode_confidence ? `· ${escapeHtml(point.geocode_confidence)}` : ''} · verify`
            : 'Country-level fallback · needs address fix';
    const lockedBadge = point.geocode_locked ? '<span class="map-popup-locked">Locked</span>' : '';
    return `
        <div class="map-popup">
            <div class="map-popup-title">${escapeHtml(point.customer_name)}</div>
            <div class="map-popup-meta">${escapeHtml([point.city, point.country_name || point.country].filter(Boolean).join(', '))}</div>
            <div class="map-popup-quality ${point.coordinate_quality === 'exact' ? 'exact' : 'fallback'}">${qualityLabel}${lockedBadge}</div>
            <div class="map-popup-stats">
                <span>${point.lead_count} leads</span>
                <span>${point.won_count} won</span>
                <span>${point.open_count} open</span>
            </div>
            <div class="map-popup-leads">${leadLines}</div>
            <div style="display:flex;gap:8px;margin-top:8px;">
                <button type="button" class="btn btn-primary btn-sm" onclick="openInquiryPanel('${point.latest_lead_id}')">Open Lead</button>
                <button type="button" class="btn btn-secondary btn-sm" onclick="jumpToCustomerStageCards('${point.latest_lead_id}', '${point.latest_stage}', '${point.customer_id || ''}')">View Cards</button>
                <button type="button" class="btn btn-secondary btn-sm" onclick="openCoordinateCorrectionFromMap('${escapeHtml(point.customer_id)}')">Fix Location</button>
            </div>
        </div>
    `;
}

function renderMapSummary(mapData, visiblePoints) {
    const summary = mapData.summary || {};
    const text = [
        `${visiblePoints} shown`,
        `${summary.exact_points || 0} exact`,
        `${summary.approximate_points || 0} need review`,
        `${summary.missing_locations || 0} missing`
    ].join(' · ');
    setText('map-summary', text);
}

function updateCoordinateReviewBadge(mapData) {
    const summary = mapData?.summary || {};
    const count = (summary.approximate_points || 0) + (summary.missing_locations || 0);
    setText('nav-coordinate-review-total', count);
}

