async function loadStageFilterUsers() {
    try {
        const requests = [];
        if (canFilterByOwner()) requests.push(ApiClient.listUsers('sales'));
        else requests.push(Promise.resolve([]));
        if (canFilterByTech()) requests.push(ApiClient.listUsers('tech'));
        else requests.push(Promise.resolve([]));

        const [salesUsers, techUsers] = await Promise.all(requests);
        State.stageUsers.sales = salesUsers || [];
        State.stageUsers.tech = techUsers || [];
        renderStageFilterOptions();
    } catch (err) {
        console.error('Stage filter user load error:', err);
    }
}

function renderStageFilterOptions() {
    STAGE_MODULES.forEach(moduleKey => {
        const ownerSelect = document.getElementById(`stage-owner-${moduleKey}`);
        if (ownerSelect) {
            ownerSelect.innerHTML = '<option value="">All sales</option>' +
                State.stageUsers.sales.map(user =>
                    `<option value="${user.id}">${escapeHtml(user.display_name)}</option>`
                ).join('');
        }

        const techSelect = document.getElementById(`stage-tech-${moduleKey}`);
        if (techSelect) {
            techSelect.innerHTML = '<option value="">All tech</option>' +
                State.stageUsers.tech.map(user =>
                    `<option value="${user.id}">${escapeHtml(user.display_name)}</option>`
                ).join('');
        }
    });
    syncStageFilterInputs();
}

function syncStageFilterInputs() {
    const handlerSearch = document.getElementById('search-inquiry');
    if (handlerSearch && handlerSearch.value !== State.stageFilters.search) {
        handlerSearch.value = State.stageFilters.search;
    }

    STAGE_MODULES.forEach(moduleKey => {
        const searchInput = document.getElementById(`stage-search-${moduleKey}`);
        if (searchInput && searchInput.value !== State.stageFilters.search) {
            searchInput.value = State.stageFilters.search;
        }
        const ownerSelect = document.getElementById(`stage-owner-${moduleKey}`);
        if (ownerSelect && ownerSelect.value !== State.stageFilters.ownerId) {
            ownerSelect.value = State.stageFilters.ownerId;
        }
        const techSelect = document.getElementById(`stage-tech-${moduleKey}`);
        if (techSelect && techSelect.value !== State.stageFilters.techId) {
            techSelect.value = State.stageFilters.techId;
        }
    });
}

function getSharedLeadFilters() {
    const filters = {};
    if (State.stageFilters.search) filters.search = State.stageFilters.search;
    if (State.stageFilters.ownerId) filters.owner_id = State.stageFilters.ownerId;
    if (State.stageFilters.techId) filters.tech_id = State.stageFilters.techId;
    if (State.stageFilters.customerId) filters.customer_id = State.stageFilters.customerId;
    return filters;
}

function reloadActiveStageModule() {
    const activeModule = document.querySelector('.module.active')?.id?.replace('module-', '');
    if (STAGE_MODULES.includes(activeModule)) {
        loadModuleData(activeModule);
    }
}

