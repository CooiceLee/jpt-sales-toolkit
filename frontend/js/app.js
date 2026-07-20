/**
 * JPT Sales Toolkit - v6.8 modular application entry
 * Global state, startup, navigation and dashboard shell.
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
        customerId: '',
        businessRegion: ''
    },
    customerMerge: {
        source: null,
        target: null,
        preview: null
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
        sampling: stats.pre_sales_active_lead_count || 0,
        deal: (byStage['Quoted'] || 0) + (byStage['Lost'] || 0),
        fulfillment: byStage['Won'] || 0,
        aftersales: stats.service_open_count || 0,
    };
}

function applyNavigationCounts(stats) {
    const counts = deriveModuleCounts(stats);
    setText('nav-total', counts.total);
    setText('nav-parser-total', counts.total);
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
        sampling: 'Pre-sales / Sampling',
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
        case 'export': window.DataTransferWorkspace?.ensureAccessible?.(); break;
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

