/** Transport preferences and the travel list, drawn from one row model. */
(function() {
    let shown = [];
    const modeLabels = {
        flight: 'Flight', drive: 'Drive', ground_public: 'Ground public', other: 'Other',
    };
    const h = value => escapeHtml(value ?? '');
    const t = (key, params = {}) => I18n.t(key, params);

    function renderPriority(draft) {
        const root = document.getElementById('trip-transport-priority');
        if (!root) return;
        if (!draft) {
            root.innerHTML = `<div class="empty-state compact">${h(t('Create or select a plan'))}</div>`;
            return;
        }
        const enabled = draft.transportModePriority;
        const ordered = [...enabled, ...TripPlanningDraft.MODES.filter(mode => !enabled.includes(mode))];
        root.innerHTML = ordered.map(mode => {
            const index = enabled.indexOf(mode);
            const checked = index >= 0;
            return `<div class="trip-mode-row ${checked ? 'enabled' : ''}">
                <label><input type="checkbox" ${checked ? 'checked' : ''} onchange="TripTransportActions.toggleMode('${mode}', this.checked)"> <span>${h(t(modeLabels[mode]))}</span></label>
                <span class="trip-mode-rank">${checked ? h(t('Priority {count}', { count: index + 1 })) : h(t('Disabled'))}</span>
                <button type="button" class="btn btn-secondary btn-sm" onclick="TripTransportActions.moveMode('${mode}', -1)" ${!checked || index === 0 ? 'disabled' : ''} aria-label="${h(t('Move up'))}">↑</button>
                <button type="button" class="btn btn-secondary btn-sm" onclick="TripTransportActions.moveMode('${mode}', 1)" ${!checked || index === enabled.length - 1 ? 'disabled' : ''} aria-label="${h(t('Move down'))}">↓</button>
            </div>`;
        }).join('');
    }

    function renderLegs(plan, draft) {
        // One row is one journey - see trip-leg-rows.js. A row number is what
        // every action on a row is given, and the travel options are drawn into
        // these same rows, so both have to count in this list and no other.
        // Worked out before anything is drawn: the journeys are now read on the
        // timeline and edited one at a time, so there may be no list on the
        // page at all - and a row number still has to resolve.
        const rows = window.TripLegRows?.rows?.(plan, draft)
            || (plan?.legs || []).map(leg => ({ leg, legs: [leg], members: [] }));
        shown = rows;
        const root = document.getElementById('trip-leg-list');
        const count = document.getElementById('trip-leg-count');
        if (!root) return;
        if (count) count.textContent = t('{count} legs', { count: rows.length });
        root.innerHTML = rows.length
            ? rows.map((row, index) => window.TripLegCard?.render?.(row, index, draft) || '').join('')
            : `<div class="empty-state compact">${h(t('Preview the route to calculate transport legs.'))}</div>`;
        window.TripSuggestionView?.render?.(plan);
    }

    // The status moved to the bar the four zones share: this card could only
    // be read in one of them, and it judged "saved" from the local draft alone
    // while the server had already marked the route out of date.
    function renderStatus() {
        window.TripRouteBar?.render?.();
    }

    /** The leg a rendered row stands for, and the rows that are on screen. */
    function legAt(index) { return shown[index]?.leg || null; }
    function rows() { return shown; }

    window.TripTransportView = Object.freeze({ legAt, rows,
        render(plan, draft) { renderPriority(draft); renderLegs(plan, draft); renderStatus(draft); },
    });
})();
