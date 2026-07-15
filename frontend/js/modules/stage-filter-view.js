function canFilterByOwner() {
    return State.user?.role === 'leader';
}

function canFilterByTech() {
    return ['leader', 'sales'].includes(State.user?.role);
}

function initStageFilterControls() {
    STAGE_MODULES.forEach(ensureStageFilterControls);
        const handlerSearch = document.getElementById('search-inquiry');
        if (handlerSearch && !handlerSearch.dataset.stageFilterBound) {
            handlerSearch.dataset.stageFilterBound = '1';
            handlerSearch.addEventListener('input', debounce(() => {
                State.stageFilters.search = handlerSearch.value.trim();
                State.stageFilters.customerId = '';
                syncStageFilterInputs();
                reloadActiveStageModule();
            }, 300));
        }
    loadStageFilterUsers();
    syncStageFilterInputs();
}

function ensureStageFilterControls(moduleKey) {
    const module = document.getElementById(`module-${moduleKey}`);
    const bar = module?.querySelector('.filters-bar');
    if (!bar || bar.querySelector(`[data-stage-controls="${moduleKey}"]`)) return;

    const wrapper = document.createElement('div');
    wrapper.className = 'stage-filter-controls';
    wrapper.dataset.stageControls = moduleKey;
    wrapper.innerHTML = buildStageFilterControls(moduleKey);

    const spacer = bar.querySelector('.filter-spacer');
    if (spacer) {
        bar.insertBefore(wrapper, spacer);
    } else {
        bar.appendChild(wrapper);
    }

    bindStageFilterEvents(moduleKey);
}

function buildStageFilterControls(moduleKey) {
    const searchControl = moduleKey === 'handler'
        ? ''
        : `<input type="search" class="form-input compact-search" id="stage-search-${moduleKey}" placeholder="Search customer, contact, country">`;
    const ownerControl = canFilterByOwner()
        ? `<select class="filter-select" id="stage-owner-${moduleKey}"><option value="">All sales</option></select>`
        : '';
    const techControl = canFilterByTech()
        ? `<select class="filter-select" id="stage-tech-${moduleKey}"><option value="">All tech</option></select>`
        : '';
    return `${searchControl}${ownerControl}${techControl}`;
}

function bindStageFilterEvents(moduleKey) {
    const searchInput = document.getElementById(`stage-search-${moduleKey}`);
    if (searchInput && !searchInput.dataset.bound) {
        searchInput.dataset.bound = '1';
        searchInput.addEventListener('input', debounce(() => {
            State.stageFilters.search = searchInput.value.trim();
            State.stageFilters.customerId = '';
            syncStageFilterInputs();
            reloadActiveStageModule();
        }, 300));
    }

    const ownerSelect = document.getElementById(`stage-owner-${moduleKey}`);
    if (ownerSelect && !ownerSelect.dataset.bound) {
        ownerSelect.dataset.bound = '1';
        ownerSelect.addEventListener('change', () => {
            State.stageFilters.ownerId = ownerSelect.value || '';
            syncStageFilterInputs();
            reloadActiveStageModule();
        });
    }

    const techSelect = document.getElementById(`stage-tech-${moduleKey}`);
    if (techSelect && !techSelect.dataset.bound) {
        techSelect.dataset.bound = '1';
        techSelect.addEventListener('change', () => {
            State.stageFilters.techId = techSelect.value || '';
            syncStageFilterInputs();
            reloadActiveStageModule();
        });
    }
}
